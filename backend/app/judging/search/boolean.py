"""Local Boolean evaluation of a canonical string over title, abstract and
keywords (C.4: quasi-sensitivity on the QGS, deterministic and free).

Matching is exact on word sequences after lowercasing, accent folding and
splitting at anything that is not a letter or a digit ("AI-based" is "ai
based"). No stemming: the concept file spells out the forms it means, so the
local result is the same whatever a source's stemmer would have done. Against
a stemming source the local count is therefore a lower bound, which is the
safe side for a sensitivity that has to clear a threshold.

Proximity follows Scopus' W/n: the two terms, in either order, with at most n
words between them.
"""

from __future__ import annotations

import re
import unicodedata
from functools import lru_cache

from .concepts import Clause, SearchString

_WORD = re.compile(r"[a-z0-9]+")


def tokens(text: str) -> list[str]:
    folded = unicodedata.normalize("NFKD", text.lower())
    folded = "".join(c for c in folded if not unicodedata.combining(c))
    return _WORD.findall(folded)


@lru_cache(maxsize=4096)
def _term_tokens(term: str) -> tuple[str, ...]:
    return tuple(tokens(term))


def occurrences(words: list[str], term: str) -> list[tuple[int, int]]:
    """(start, end) word positions of every occurrence of `term`, end exclusive."""
    needle = _term_tokens(term)
    n = len(needle)
    if not n:
        return []
    return [(i, i + n) for i in range(len(words) - n + 1) if tuple(words[i:i + n]) == needle]


def _block_spans(words: list[str], terms: tuple[str, ...]) -> list[tuple[int, int]]:
    return [span for term in terms for span in occurrences(words, term)]


def _clause_matches(words: list[str], string: SearchString, clause: Clause) -> bool:
    if not clause.is_near:
        return bool(_block_spans(words, string.terms(clause.blocks[0])))
    left = _block_spans(words, string.terms(clause.blocks[0]))
    right = _block_spans(words, string.terms(clause.blocks[1]))
    for a_start, a_end in left:
        for b_start, b_end in right:
            gap = b_start - a_end if b_start >= a_end else a_start - b_end
            if 0 <= gap <= clause.distance:
                return True
    return False


def matches(string: SearchString, text: str) -> bool:
    words = tokens(text)
    return all(_clause_matches(words, string, clause) for clause in string.clauses)


# Between two fields: enough filler words that neither a phrase nor a proximity
# clause can reach from the end of the title into the abstract. Punctuation would
# not do, since tokenising drops it.
FIELD_BREAK = " " + " ".join(["fieldbreak"] * 25) + " "


def record_text(title: str | None, abstract: str | None, keywords: str | None) -> str:
    return FIELD_BREAK.join(part for part in (title, abstract, keywords) if part)
