"""Query sets: run a whole search protocol from one file.

A review is not one query. Once there are twenty search strings, invoking the
CLI per query stops being practical and — more importantly — stops being
reproducible: the protocol lives in shell history instead of in a file someone
can read, cite and re-run.

TOML via the standard library's `tomllib`, so this costs no dependency. The
file is the artefact you attach to a paper.

    # queries.toml
    [defaults]
    pages = 10
    gl = "at"
    hl = "en"

    [[query]]
    q = "AI maturity assessment model"

    [[query]]
    q = "artificial intelligence maturity framework"
    pages = 5              # overrides the default for this query only
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

# Only these may appear in [defaults] or a [[query]] block. Anything else is a
# typo, and a silently ignored typo in a search protocol is a silently wrong
# review — so it is an error, not a warning.
ALLOWED_KEYS: frozenset[str] = frozenset({
    "q", "pages", "engine", "gl", "hl", "location",
    "render_js", "premium_proxy", "stealth_proxy", "wait_ms",
    "snowball_depth", "snowball_max_links",
})

DEFAULTS: dict[str, object] = {
    "pages": 5,
    "engine": "google",
    "gl": None,
    "hl": None,
    "location": None,
    "render_js": False,
    "premium_proxy": False,
    "stealth_proxy": False,
    "wait_ms": None,
    "snowball_depth": 0,
    "snowball_max_links": 20,
}


@dataclass
class QuerySpec:
    q: str
    params: dict = field(default_factory=dict)


class ConfigError(ValueError):
    pass


def _check_keys(keys, where: str) -> None:
    unknown = set(keys) - ALLOWED_KEYS
    if unknown:
        raise ConfigError(
            f"unknown key(s) in {where}: {', '.join(sorted(unknown))}. "
            f"Allowed: {', '.join(sorted(ALLOWED_KEYS))}"
        )


def parse_config(raw: dict) -> list[QuerySpec]:
    """Turn a parsed TOML document into one fully-resolved spec per query."""
    unknown_sections = set(raw) - {"defaults", "query"}
    if unknown_sections:
        raise ConfigError(
            f"unknown section(s): {', '.join(sorted(unknown_sections))}. "
            f"Expected [defaults] and [[query]]"
        )

    defaults = raw.get("defaults") or {}
    if not isinstance(defaults, dict):
        raise ConfigError("[defaults] must be a table")
    _check_keys(defaults.keys() - {"q"}, "[defaults]")
    if "q" in defaults:
        raise ConfigError("[defaults] must not set q; put queries in [[query]] blocks")

    entries = raw.get("query") or []
    if not isinstance(entries, list) or not entries:
        raise ConfigError("at least one [[query]] block is required")

    specs: list[QuerySpec] = []
    seen: set[str] = set()
    for index, entry in enumerate(entries, start=1):
        if not isinstance(entry, dict):
            raise ConfigError(f"[[query]] #{index} must be a table")
        _check_keys(entry.keys(), f"[[query]] #{index}")
        query = entry.get("q")
        if not query or not isinstance(query, str) or not query.strip():
            raise ConfigError(f"[[query]] #{index} is missing a non-empty q")
        query = query.strip()
        if query in seen:
            # Two identical queries in one batch would produce two runs of the
            # same search, which is never intended and quietly doubles cost.
            raise ConfigError(f"duplicate query: {query!r}")
        seen.add(query)

        params = dict(DEFAULTS)
        params.update({k: v for k, v in defaults.items()})
        params.update({k: v for k, v in entry.items() if k != "q"})
        specs.append(QuerySpec(q=query, params=params))

    return specs


def load_config(path: Path) -> list[QuerySpec]:
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{path}: {exc}") from exc
    return parse_config(raw)


EXAMPLE = '''\
# glr query set — the search protocol for one review, in one file.
#
#   uv run glr batch queries.toml --out results.csv
#
# Every key in [defaults] can be overridden per query.

[defaults]
pages = 10          # 10 results per page, so 10 pages = 100 hits
gl = "at"           # country; changes the results, so report it
hl = "en"           # interface language
render_js = false   # 1 ScrapingBee credit instead of 5

# Snowballing: follow selected outgoing links one level deep.
# 0 disables it. Start at 0, measure relevance, then decide.
snowball_depth = 0
snowball_max_links = 20

[[query]]
q = "AI maturity assessment model"

[[query]]
q = "artificial intelligence maturity framework"

[[query]]
q = "AI readiness assessment organisation"
pages = 5
'''
