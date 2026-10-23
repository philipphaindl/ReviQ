"""Translation of a canonical string into each source's query syntax.

One function per executed source (PLAN.md, E3). Each states what the source
cannot express and what it does instead, because a translation that quietly
loses a constraint is a different search than the one the protocol describes.

Proximity is the main loss. None of the four sources here can express "any
term of block A within n words of any term of block B": OpenAlex supports
proximity only inside one quoted phrase and only in unstemmed search, and the
others not at all as far as checked. A proximity clause therefore becomes a
plain AND of its two blocks, which can only widen the result — the safe
direction for recall. The local evaluation (`boolean.py`) keeps the proximity,
so the protocol reports both.

The syntax below follows the providers' documentation as far as it could be
read from search excerpts on 2026-10-23 (PLAN.md, section 8); it is checked
against the original pages before G1, and the golden files change with it.
"""

from __future__ import annotations

from urllib.parse import quote

from .concepts import Clause, SearchString

YEARS = (2018, 2026)


def _quoted(term: str) -> str:
    return f'"{term}"' if " " in term or "-" in term else term


def _or_group(terms: tuple[str, ...], separator: str = " OR ") -> str:
    return "(" + separator.join(_quoted(t) for t in terms) + ")"


def _clause_groups(string: SearchString, clause: Clause) -> list[tuple[str, ...]]:
    """The blocks a clause turns into once proximity is dropped."""
    return [string.terms(block) for block in clause.blocks]


def _groups(string: SearchString) -> list[tuple[str, ...]]:
    return [group for clause in string.clauses for group in _clause_groups(string, clause)]


# --- OpenAlex ---------------------------------------------------------------

def openalex(string: SearchString) -> str:
    """Value for the `title_and_abstract.search` filter. Stemmed search, so the
    explicit plural forms are redundant there but harmless. Commas separate
    filters in OpenAlex and must not occur inside the value; no term has one,
    and this asserts it."""

    value = " AND ".join(_or_group(group) for group in _groups(string))
    if "," in value:
        raise ValueError("OpenAlex filter values cannot contain commas")
    return value


def openalex_url(string: SearchString, *, mailto: str | None = None) -> str:
    filters = (f"title_and_abstract.search:{openalex(string)},"
               f"publication_year:{YEARS[0]}-{YEARS[1]}")
    url = (f"https://api.openalex.org/works?filter={quote(filters, safe=':,()')}"
           "&per-page=200&cursor=*")
    if mailto:
        url += f"&mailto={quote(mailto)}"
    return url


# --- Semantic Scholar bulk search ---------------------------------------------

def semantic_scholar(string: SearchString) -> str:
    """Bulk search syntax: `|` for OR, `+` for AND, quotes for phrases,
    parentheses for grouping. Only `|` was confirmed from an excerpt; the rest
    is checked before G1. The caller URL-encodes the value (`+` in particular)."""

    return " + ".join(_or_group(group, " | ") for group in _groups(string))


# --- arXiv ----------------------------------------------------------------------

def arxiv(string: SearchString) -> str:
    """`search_query` for the arXiv API over title and abstract. arXiv has no
    combined field for both, so each term is asked in `ti:` and `abs:`."""

    def group(terms: tuple[str, ...]) -> str:
        parts = []
        for term in terms:
            q = _quoted(term)
            parts.append(f"ti:{q} OR abs:{q}")
        return "(" + " OR ".join(parts) + ")"

    return " AND ".join(group(g) for g in _groups(string))


# --- Google Scholar (through creel) -------------------------------------------

# Google Scholar ignores queries beyond a length limit; 256 characters is the
# figure commonly given and is checked before G1.
SCHOLAR_MAX_CHARS = 256
SCHOLAR_HEAD_TERMS = 2


def _singular_terms(terms: tuple[str, ...]) -> tuple[str, ...]:
    lowered = {t.lower() for t in terms}
    return tuple(t for t in terms if not (t.lower().endswith("s") and t.lower()[:-1] in lowered))


def google_scholar(string: SearchString) -> list[str]:
    """Short queries rather than one exhaustive Boolean string. Scholar ranks by
    relevance and is read to a fixed depth (protocol 5.1), so what matters is
    that each query names the concept precisely, not that one query covers
    every combination; split to the length limit, the full string would become
    dozens of queries and cost as many times the credits.

    Rule: one query per term of the string's last block (the most specific
    concept: M for S1, E for S2), singular forms only, each together with the
    first two terms of the first block (the AI concept) and the first term of
    every block in between (the context, e.g. adoption and organization for S2).
    Deterministic, and every anchor term is asked once."""

    blocks = [b for c in string.clauses for b in c.blocks]
    head = string.terms(blocks[0])[:SCHOLAR_HEAD_TERMS]
    context = " ".join(_quoted(string.terms(b)[0]) for b in blocks[1:-1])
    prefix = f"{_or_group(head)} {context}".strip()
    queries = [f"{prefix} {_quoted(term)}" for term in _singular_terms(string.terms(blocks[-1]))]
    too_long = [q for q in queries if len(q) > SCHOLAR_MAX_CHARS]
    if too_long:
        raise ValueError(f"Scholar query over {SCHOLAR_MAX_CHARS} characters: {too_long[0]}")
    return queries


SOURCES = {
    "openalex": lambda s: [openalex(s)],
    "semantic_scholar": lambda s: [semantic_scholar(s)],
    "arxiv": lambda s: [arxiv(s)],
    "google_scholar": google_scholar,
}
