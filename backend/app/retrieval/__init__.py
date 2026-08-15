"""Retrieval of grey literature — SERP query, snapshot, extraction, provenance.

Formerly the standalone tool `glr`. It kept its own repository while a second,
non-review use was planned; that plan was dropped, so it lives here now and is
GPL-3.0 like the rest of ReviQ. The commit history that justifies this code
stays in the archived `philipphaindl/glr` repository — `git log --follow` does
not reach across repositories — while the decisions themselves are in
`docs/retrieval/decisions.md` as D1-D31.

**This package knows nothing about reviews.** No `study`, no `screening`, no
`inclusion criterion`, no `citekey`. The boundary is real rather than a
leftover of the split: what this package produces is a URL with bytes and a
retrieval timestamp, and what a review works with is a unit of evidence. The
`GreySource` table in `app/models.py` is where the two meet.

Runs as a subprocess rather than inside the API process, deliberately:

    python -m app.retrieval.cli run "AI maturity model" --pages 5

An lxml segfault or a 300 MB PDF would otherwise take the API down with it, and
a retrieval batch runs for tens of minutes.
"""

__version__ = "0.1.0"
