"""Candidate strings, their measurement and the selection rule (C.4).

The selection is a measured optimisation, not a judgement: candidates come
from systematic variation of the base strings (block ablation, proximity
3/5/10, blocks widened by harvested terms) plus at most ten jury suggestions,
each is measured the same way, and a fixed rule picks one. Wang et al. (2023)
found LLM-written Boolean queries to favour precision at the cost of recall,
which is why the jury may propose but never choose.
"""

from __future__ import annotations

from dataclasses import dataclass

from .boolean import matches, record_text
from .concepts import Clause, SearchString

PROXIMITIES = (3, 5, 10)
MAX_JURY_SUGGESTIONS = 10


@dataclass(frozen=True)
class Candidate:
    string: SearchString
    base: str
    variant: str


@dataclass(frozen=True)
class Measurement:
    candidate: Candidate
    dev_matched: int
    dev_total: int
    hits: int | None = None
    precision: float | None = None

    @property
    def sensitivity(self) -> float:
        return self.dev_matched / self.dev_total if self.dev_total else 0.0


def variants(base: SearchString, harvested: dict[str, tuple[str, ...]] | None = None
             ) -> list[Candidate]:
    """The base itself, every clause dropped in turn, every proximity at each
    tested distance, a proximity clause relaxed to its two blocks, and each
    block widened by the harvested terms for it."""

    out = [Candidate(base, base.name, "base")]
    clauses = base.clauses
    for i, clause in enumerate(clauses):
        if len(clauses) > 1:
            rest = clauses[:i] + clauses[i + 1:]
            out.append(Candidate(base.with_clauses(f"{base.name}-drop{i + 1}", rest),
                                 base.name, f"without ({clause.label()})"))
        if clause.is_near:
            for distance in PROXIMITIES:
                if distance != clause.distance:
                    changed = clauses[:i] + (Clause(clause.blocks, distance),) + clauses[i + 1:]
                    out.append(Candidate(
                        base.with_clauses(f"{base.name}-w{distance}-{i + 1}", changed),
                        base.name, f"{clause.label()} -> W/{distance}"))
            relaxed = clauses[:i] + tuple(Clause((b,)) for b in clause.blocks) + clauses[i + 1:]
            out.append(Candidate(base.with_clauses(f"{base.name}-and-{i + 1}", relaxed),
                                 base.name, f"{clause.label()} -> AND"))
    for block, extra in (harvested or {}).items():
        new = tuple(t for t in extra if t.lower() not in {x.lower() for x in base.terms(block)})
        if new and any(block in c.blocks for c in clauses):
            out.append(Candidate(base.with_block(f"{base.name}-wide-{block}", block,
                                                 base.terms(block) + new),
                                 base.name, f"{block} + {', '.join(new)}"))
    return out


def measure(candidate: Candidate, dev: list) -> Measurement:
    """Quasi-sensitivity on QGS-dev by local Boolean evaluation. `dev` holds
    records with `title`, `abstract` and `keywords`."""

    matched = sum(1 for r in dev
                  if matches(candidate.string, record_text(r.title, r.abstract, r.keywords)))
    return Measurement(candidate, matched, len(dev))


@dataclass(frozen=True)
class Selection:
    chosen: Measurement | None
    reason: str


def select(measurements: list[Measurement], *, min_sensitivity: float = 0.90,
           budget: int) -> Selection:
    """C.4, rule 4: maximum estimated precision subject to dev sensitivity
    >= `min_sensitivity` and hits <= `budget`; on a tie the shorter string."""

    eligible = [m for m in measurements
                if m.sensitivity >= min_sensitivity and m.hits is not None and m.hits <= budget]
    if not eligible:
        return Selection(None, "no candidate reaches the sensitivity within the budget")
    missing = [m for m in eligible if m.precision is None]
    if missing:
        return Selection(None, f"{len(missing)} eligible candidate(s) have no precision "
                               "estimate yet")
    best = max(eligible, key=lambda m: (m.precision, -m.candidate.string.term_count(),
                                        -len(m.candidate.string.label())))
    return Selection(best, "maximum precision among eligible candidates")
