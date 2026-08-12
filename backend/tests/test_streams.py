"""Stream and discovery classification.

Deliberately free of FastAPI and SQLModel: `app.services.streams` is pure
logic, and the frontend mirror in `src/components/streams.ts` must agree with
it case for case. Keep the two test files in step.
"""
from types import SimpleNamespace

from app.services.streams import (
    FORMAL, GREY, SEARCH, SNOWBALL,
    by_stream, discovery_of, is_reserved_source, partition, stream_of,
)


def paper(**kwargs):
    """A stand-in for a Paper row. Absent attributes model a pre-migration row."""
    return SimpleNamespace(**kwargs)


class TestExplicitColumns:
    def test_formal_search(self):
        p = paper(stream="formal", discovery="search", source="ieee")
        assert (stream_of(p), discovery_of(p)) == (FORMAL, SEARCH)

    def test_grey_search(self):
        p = paper(stream="grey", discovery="search", source="grey:google")
        assert (stream_of(p), discovery_of(p)) == (GREY, SEARCH)

    def test_grey_snowball(self):
        """Grey literature has its own snowballing — the case a single
        four-valued enum would have made awkward and a `source` prefix test
        would have missed entirely."""
        p = paper(stream="grey", discovery="snowball", source="grey:google")
        assert (stream_of(p), discovery_of(p)) == (GREY, SNOWBALL)

    def test_columns_win_over_the_source_string(self):
        """`source` is a display label. If the two ever disagree, the columns
        are authoritative — otherwise the fallback would quietly override an
        explicitly recorded classification."""
        p = paper(stream="grey", discovery="search", source="snowballing:2")
        assert (stream_of(p), discovery_of(p)) == (GREY, SEARCH)


class TestLegacyRows:
    """Rows written before the migration have NULL in both columns."""

    def test_legacy_database_paper(self):
        p = paper(stream=None, discovery=None, source="scopus")
        assert (stream_of(p), discovery_of(p)) == (FORMAL, SEARCH)

    def test_legacy_snowballed_paper(self):
        p = paper(stream=None, discovery=None, source="snowballing:2")
        assert (stream_of(p), discovery_of(p)) == (FORMAL, SNOWBALL)

    def test_attributes_missing_entirely(self):
        p = paper(source="snowballing:1")
        assert (stream_of(p), discovery_of(p)) == (FORMAL, SNOWBALL)

    def test_empty_source_is_a_formal_search_hit(self):
        assert (stream_of(paper(source="")), discovery_of(paper(source=""))) == (FORMAL, SEARCH)


class TestReservedSources:
    """`snowballing.delete_iteration` deletes papers by `source ==
    "snowballing:{n}"` together with their decisions. A user-typed database
    name that collides with a reserved prefix would arm that delete."""

    def test_reserved_prefixes_are_rejected(self):
        assert is_reserved_source("snowballing:1")
        assert is_reserved_source("grey:google")
        assert is_reserved_source("grey-snowball:google")

    def test_case_and_padding_do_not_evade_the_check(self):
        assert is_reserved_source("  Snowballing:1  ")
        assert is_reserved_source("GREY:bing")

    def test_ordinary_database_names_are_fine(self):
        assert not is_reserved_source("scopus")
        assert not is_reserved_source("greynet")   # not a prefix match
        assert not is_reserved_source("")


class TestGrouping:
    def test_partition_covers_all_four_combinations(self):
        papers = [
            paper(stream="formal", discovery="search", source="ieee"),
            paper(stream="formal", discovery="snowball", source="snowballing:1"),
            paper(stream="grey", discovery="search", source="grey:google"),
            paper(stream="grey", discovery="snowball", source="grey:google"),
        ]
        grouped = partition(papers)
        assert set(grouped) == {
            (FORMAL, SEARCH), (FORMAL, SNOWBALL), (GREY, SEARCH), (GREY, SNOWBALL),
        }
        assert all(len(v) == 1 for v in grouped.values())

    def test_by_stream_always_has_both_keys(self):
        """PRISMA renders a grey column only when it has content, but the
        caller must not have to guard the lookup."""
        grouped = by_stream([paper(stream="formal", discovery="search", source="ieee")])
        assert set(grouped) == {FORMAL, GREY}
        assert grouped[GREY] == []

    def test_streams_are_disjoint_and_total(self):
        papers = [
            paper(stream="formal", discovery="search", source="ieee"),
            paper(stream="grey", discovery="search", source="grey:google"),
            paper(stream=None, discovery=None, source="snowballing:3"),
        ]
        grouped = by_stream(papers)
        assert len(grouped[FORMAL]) + len(grouped[GREY]) == len(papers)
