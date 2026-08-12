"""How a paper entered the review.

Two independent axes:

  * `stream`    — formal (peer-reviewed databases) vs. grey (web sources).
    A multivocal literature review (Garousi, Felizardo & Mäntylä 2019) covers
    both and must report them separately.
  * `discovery` — search (a database or engine query) vs. snowball (reached
    from another included source, Wohlin 2014).

They are orthogonal: grey literature has its own snowballing, and a formal
paper can arrive either way. That is why `Paper` carries two columns rather
than one compound label.

Every stream test in the backend goes through this module. Before it existed
the test was `source.startswith("snowballing:")`, repeated at three sites here
and fifteen in the frontend — with no third case, so a grey paper silently
counted as a database hit and inflated the PRISMA "records identified" box.
Adding a stream must mean editing one file, not twenty.
"""
from collections import defaultdict

FORMAL = "formal"
GREY = "grey"
SEARCH = "search"
SNOWBALL = "snowball"

# Reserved `source` prefixes. A user-supplied database name must not collide
# with these: `snowballing.delete_iteration` deletes papers by `source ==
# "snowballing:{n}"` together with their decisions, so a typed source name
# that matches would arm a delete.
RESERVED_SOURCE_PREFIXES = ("snowballing:", "grey:", "grey-snowball:")


def stream_of(paper) -> str:
    """FORMAL or GREY. Falls back to the source prefix for pre-migration rows."""
    value = getattr(paper, "stream", None)
    if value:
        return value
    source = getattr(paper, "source", "") or ""
    return GREY if source.startswith(("grey:", "grey-snowball:")) else FORMAL


def discovery_of(paper) -> str:
    """SEARCH or SNOWBALL. Falls back to the source prefix for pre-migration rows."""
    value = getattr(paper, "discovery", None)
    if value:
        return value
    source = getattr(paper, "source", "") or ""
    return SNOWBALL if source.startswith(("snowballing:", "grey-snowball:")) else SEARCH


def is_reserved_source(name: str) -> bool:
    """True if a user-supplied database name would collide with a reserved prefix."""
    return (name or "").strip().lower().startswith(RESERVED_SOURCE_PREFIXES)


def partition(papers) -> dict[tuple[str, str], list]:
    """Group papers by (stream, discovery). Empty groups are absent, not empty."""
    grouped: dict[tuple[str, str], list] = defaultdict(list)
    for paper in papers:
        grouped[(stream_of(paper), discovery_of(paper))].append(paper)
    return dict(grouped)


def by_stream(papers) -> dict[str, list]:
    """Group papers by stream alone — the PRISMA top-level split."""
    grouped: dict[str, list] = {FORMAL: [], GREY: []}
    for paper in papers:
        grouped[stream_of(paper)].append(paper)
    return grouped
