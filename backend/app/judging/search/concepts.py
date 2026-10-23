"""The canonical form of a search string (protocol.md, section 5.2).

A string is a conjunction of clauses; a clause is one concept block (an OR
group of terms) or two blocks within a word distance of each other. That is
all the brief's strings need, and keeping the form this small is what lets one
canonical string be translated faithfully into every source and evaluated
locally against the quasi-gold standard without any source at all.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, replace
from pathlib import Path

CONCEPTS_PATH = Path(__file__).with_name("concepts.toml")


class ConceptError(ValueError):
    pass


@dataclass(frozen=True)
class Clause:
    blocks: tuple[str, ...]          # one block, or two for a proximity clause
    distance: int | None = None      # words between the two blocks; None = plain block

    @property
    def is_near(self) -> bool:
        return self.distance is not None

    def label(self) -> str:
        if self.is_near:
            return f"{self.blocks[0]} W/{self.distance} {self.blocks[1]}"
        return self.blocks[0]


@dataclass(frozen=True)
class SearchString:
    name: str
    clauses: tuple[Clause, ...]
    blocks: dict[str, tuple[str, ...]]

    def terms(self, block: str) -> tuple[str, ...]:
        return self.blocks[block]

    def label(self) -> str:
        return " AND ".join(f"({c.label()})" for c in self.clauses)

    def with_clauses(self, name: str, clauses: tuple[Clause, ...]) -> "SearchString":
        return replace(self, name=name, clauses=clauses)

    def with_block(self, name: str, block: str, terms: tuple[str, ...]) -> "SearchString":
        return replace(self, name=name, blocks={**self.blocks, block: terms})

    def term_count(self) -> int:
        return sum(len(self.blocks[b]) for c in self.clauses for b in c.blocks)


def load(path: Path = CONCEPTS_PATH) -> dict[str, SearchString]:
    raw = tomllib.loads(path.read_text(encoding="utf-8"))
    blocks = {name: tuple(terms) for name, terms in raw["blocks"].items()}
    for name, terms in blocks.items():
        if not terms:
            raise ConceptError(f"block {name} is empty")
        if len(set(t.lower() for t in terms)) != len(terms):
            raise ConceptError(f"block {name} lists a term twice")
    strings: dict[str, SearchString] = {}
    for entry in raw["string"]:
        clauses = []
        for clause in entry["clauses"]:
            if "near" in clause:
                pair = tuple(clause["near"])
                if len(pair) != 2:
                    raise ConceptError(f"{entry['name']}: near needs two blocks")
                clauses.append(Clause(pair, int(clause["distance"])))
            else:
                clauses.append(Clause((clause["block"],)))
        for clause in clauses:
            for block in clause.blocks:
                if block not in blocks:
                    raise ConceptError(f"{entry['name']}: unknown block {block}")
        strings[entry["name"]] = SearchString(entry["name"], tuple(clauses), blocks)
    return strings
