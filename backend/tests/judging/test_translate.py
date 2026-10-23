"""Translation per source, held to golden files.

Set UPDATE_GOLDEN=1 to rewrite the files after a deliberate change, then review
the diff: a changed golden file is a changed search."""

import os
from pathlib import Path

import pytest

from app.judging.search import concepts, translate

GOLDEN = Path(__file__).with_name("golden")
STRINGS = concepts.load()


@pytest.mark.parametrize("name", sorted(STRINGS))
@pytest.mark.parametrize("source", sorted(translate.SOURCES))
def test_translation_matches_its_golden_file(name, source):
    rendered = "\n".join(translate.SOURCES[source](STRINGS[name])) + "\n"
    path = GOLDEN / f"{name}.{source}.txt"
    if os.environ.get("UPDATE_GOLDEN"):
        path.write_text(rendered, encoding="utf-8")
    assert path.read_text(encoding="utf-8") == rendered


def test_proximity_becomes_and_in_every_source():
    s1 = STRINGS["S1"]
    assert "W/" not in translate.openalex(s1) and "~" not in translate.openalex(s1)
    assert translate.openalex(s1).count(" AND ") == 2


def test_openalex_url_carries_the_period_and_cursor_paging():
    url = translate.openalex_url(STRINGS["S1"], mailto="a@b.example")
    assert "publication_year:2018-2026" in url
    assert "cursor=*" in url and "per-page=200" in url and "mailto=a%40b.example" in url


def test_scholar_asks_every_singular_anchor_term_once_within_the_length_limit():
    queries = translate.google_scholar(STRINGS["S2"])
    anchors = [q.rsplit(" ", 1)[-1].strip('"') for q in queries]
    assert "barrier" in anchors and "barriers" not in anchors
    assert len(set(queries)) == len(queries)
    assert all(len(q) <= translate.SCHOLAR_MAX_CHARS for q in queries)
