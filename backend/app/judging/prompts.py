"""Versioned prompt files and the freeze that makes them immutable (A.3.2).

A prompt is a Markdown file in `prompts/` with a small front matter:

    ---
    name: screening
    version: 0.3
    ---
    You screen one record ...

The hash covers the whole file, front matter included, so a changed text under
an unchanged version number is caught rather than trusted. `freeze` writes the
hashes of the named prompts to `prompts/freeze.json`; from then on loading a
frozen prompt whose file no longer matches is an error, not a warning. A later
change is a protocol deviation, made deliberately by editing the freeze record
in a reviewed commit — never by the code quietly accepting a new text.

Prompts that have not been frozen yet load freely. The freeze is per prompt
because the phases reach it at different times: screening at G2, extraction
and abstraction later.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

PROMPT_DIR = Path(__file__).with_name("prompts")
FREEZE_FILE = "freeze.json"


class PromptError(ValueError):
    pass


class PromptFrozen(PromptError):
    """A frozen prompt's file has changed since the freeze."""


@dataclass(frozen=True)
class Prompt:
    name: str
    version: str
    text: str
    sha256: str
    path: Path


def _front_matter(raw: str, path: Path) -> tuple[dict[str, str], str]:
    lines = raw.splitlines()
    if not lines or lines[0].strip() != "---":
        raise PromptError(f"{path.name}: missing front matter")
    try:
        end = next(i for i, line in enumerate(lines[1:], start=1) if line.strip() == "---")
    except StopIteration:
        raise PromptError(f"{path.name}: front matter is not closed") from None
    meta: dict[str, str] = {}
    for line in lines[1:end]:
        key, sep, value = line.partition(":")
        if not sep:
            raise PromptError(f"{path.name}: cannot read front matter line {line!r}")
        meta[key.strip()] = value.strip()
    for required in ("name", "version"):
        if not meta.get(required):
            raise PromptError(f"{path.name}: front matter needs {required!r}")
    return meta, "\n".join(lines[end + 1:]).strip() + "\n"


def _freeze_record(directory: Path) -> dict:
    path = directory / FREEZE_FILE
    if not path.is_file():
        return {"prompts": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def load(name: str, directory: Path = PROMPT_DIR) -> Prompt:
    path = directory / f"{name}.md"
    if not path.is_file():
        raise PromptError(f"no prompt named {name!r} in {directory}")
    raw = path.read_text(encoding="utf-8")
    meta, text = _front_matter(raw, path)
    if meta["name"] != name:
        raise PromptError(f"{path.name}: front matter names {meta['name']!r}")
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    frozen = _freeze_record(directory)["prompts"].get(name)
    if frozen and (frozen["sha256"] != digest or frozen["version"] != meta["version"]):
        raise PromptFrozen(
            f"{name}: changed after the freeze (frozen v{frozen['version']} "
            f"{frozen['sha256'][:12]}, file v{meta['version']} {digest[:12]}). "
            "A change now is a protocol deviation and needs a reviewed edit of "
            f"{FREEZE_FILE}.")
    return Prompt(name=name, version=meta["version"], text=text, sha256=digest, path=path)


def available(directory: Path = PROMPT_DIR) -> list[str]:
    return sorted(p.stem for p in directory.glob("*.md"))


def frozen_names(directory: Path = PROMPT_DIR) -> set[str]:
    return set(_freeze_record(directory)["prompts"])


def freeze(names: list[str], directory: Path = PROMPT_DIR, *,
           now: datetime | None = None) -> dict:
    """Record the current hash of each named prompt. Freezing a prompt twice
    is allowed only while its file is unchanged."""

    record = _freeze_record(directory)
    stamp = (now or datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ")
    for name in names:
        prompt = load(name, directory)   # raises if a frozen prompt has changed
        record["prompts"].setdefault(name, {
            "version": prompt.version, "sha256": prompt.sha256, "frozen_at_utc": stamp,
        })
    (directory / FREEZE_FILE).write_text(
        json.dumps(record, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return record
