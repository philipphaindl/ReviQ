"""The study configuration, read from one TOML file.

Strict on purpose, like `retrieval.batch`: an unknown key is a typo, and a
silently ignored typo in a threshold is a silently different study. Every
section and key is listed here, and anything else is an error.

Model ids are validated in two steps. Loading accepts "TBD" for a rung that is
not chosen yet, because the configuration has to exist before calibration
decides which rung a judge uses. `require_pinned` is what `freeze` calls: from
then on every rung in use must name an exact model, never an alias. Aliases
are refused outright, because "latest" is a different model next month and a
cache keyed on it would replay one model's answers as another's.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_PATH = Path(__file__).with_name("study.toml")

UNPINNED = "TBD"
MODES = ("studie", "review")
FAMILIES = ("anthropic", "openai", "google", "open-weight")

# Substrings that mark a moving target rather than a model.
ALIAS_MARKERS = ("latest", "default", "stable", "preview")


class ConfigError(ValueError):
    pass


@dataclass(frozen=True)
class Rung:
    model: str
    price_in: float
    price_out: float
    batch_discount: float
    digest: str | None = None

    @property
    def pinned(self) -> bool:
        if self.model == UNPINNED:
            return False
        return self.digest != UNPINNED


@dataclass(frozen=True)
class Judge:
    key: str
    family: str
    role: str
    ladder: tuple[Rung, ...]
    local: bool = False


@dataclass(frozen=True)
class Study:
    name: str
    mode: str
    seed: int
    main_project: str
    calibration_project: str
    validation_project: str
    jury: dict[str, float]
    audit: dict[str, float]
    abstraction: dict[str, float]
    ladder_tolerance: float
    judges: tuple[Judge, ...] = field(default_factory=tuple)

    def judge(self, key: str) -> Judge:
        for judge in self.judges:
            if judge.key == key:
                return judge
        raise KeyError(key)

    @property
    def audit_eps(self) -> float:
        return self.audit["eps_" + self.mode]


_SECTIONS = {
    "study": {"name", "mode", "seed", "main_project", "calibration_project",
              "validation_project"},
    "jury": {"anchor_sample", "tau_exclude", "tau_include", "max_rounds",
             "alpha_min", "recall_min", "bootstrap_resamples"},
    "audit": {"eps_studie", "eps_review"},
    "abstraction": {"ari_median_min", "ari_lower_min"},
    "ladder": {"tolerance"},
    "judge": {"key", "family", "role", "ladder", "local"},
}
_RUNG_KEYS = {"model", "price_in", "price_out", "batch_discount", "digest"}


def _check_keys(found, allowed: set[str], where: str) -> None:
    unknown = set(found) - allowed
    if unknown:
        raise ConfigError(f"{where}: unknown key(s) {', '.join(sorted(unknown))}")
    missing = allowed - set(found) - {"local", "digest"}
    if missing:
        raise ConfigError(f"{where}: missing key(s) {', '.join(sorted(missing))}")


def _check_model(model: str, where: str) -> None:
    if model == UNPINNED:
        return
    lowered = model.lower()
    for marker in ALIAS_MARKERS:
        if marker in lowered:
            raise ConfigError(f"{where}: {model!r} looks like an alias ({marker!r}); "
                              "pin an exact model id")


def parse(raw: dict) -> Study:
    _check_keys(raw, set(_SECTIONS), "top level")
    for section in ("study", "jury", "audit", "abstraction", "ladder"):
        _check_keys(raw[section], _SECTIONS[section], f"[{section}]")

    study = raw["study"]
    if study["mode"] not in MODES:
        raise ConfigError(f"[study] mode must be one of {MODES}, got {study['mode']!r}")

    jury = raw["jury"]
    if not 0 < jury["tau_exclude"] < jury["tau_include"] < 1:
        raise ConfigError("[jury] needs 0 < tau_exclude < tau_include < 1")
    if jury["max_rounds"] < 1 or jury["anchor_sample"] < 1:
        raise ConfigError("[jury] max_rounds and anchor_sample must be positive")
    for key, value in raw["audit"].items():
        if not 0 < value < 1:
            raise ConfigError(f"[audit] {key} must lie between 0 and 1")

    judges: list[Judge] = []
    roles: set[str] = set()
    for index, entry in enumerate(raw["judge"], start=1):
        where = f"[[judge]] #{index}"
        _check_keys(entry, _SECTIONS["judge"], where)
        if entry["family"] not in FAMILIES:
            raise ConfigError(f"{where}: family must be one of {FAMILIES}")
        if entry["role"] in roles:
            raise ConfigError(f"{where}: role {entry['role']} is used twice")
        roles.add(entry["role"])
        rungs: list[Rung] = []
        for position, rung in enumerate(entry["ladder"], start=1):
            rung_where = f"{where} ladder #{position}"
            _check_keys(rung, _RUNG_KEYS, rung_where)
            _check_model(rung["model"], rung_where)
            rungs.append(Rung(**rung))
        if not rungs:
            raise ConfigError(f"{where}: ladder is empty")
        judges.append(Judge(key=entry["key"], family=entry["family"], role=entry["role"],
                            ladder=tuple(rungs), local=bool(entry.get("local", False))))

    families = {j.family for j in judges}
    if len(families) < 3:
        raise ConfigError("at least three model families are required (A.3.3)")

    return Study(
        name=study["name"], mode=study["mode"], seed=int(study["seed"]),
        main_project=study["main_project"],
        calibration_project=study["calibration_project"],
        validation_project=study["validation_project"],
        jury=dict(jury), audit=dict(raw["audit"]), abstraction=dict(raw["abstraction"]),
        ladder_tolerance=float(raw["ladder"]["tolerance"]), judges=tuple(judges),
    )


def load(path: Path = DEFAULT_PATH) -> Study:
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{path}: {exc}") from exc
    return parse(raw)


def require_pinned(study: Study, rungs: dict[str, int]) -> None:
    """Every judge's chosen rung must name an exact model. `rungs` maps a judge
    key to the ladder position calibration settled on (0 = mid-tier)."""

    for judge in study.judges:
        rung = judge.ladder[rungs.get(judge.key, 0)]
        if not rung.pinned:
            raise ConfigError(f"{judge.key} ({judge.family}): model not pinned yet")
