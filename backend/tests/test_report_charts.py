"""Tests for the pure synthesis-chart helpers in app.routers.report.

These mirror the TypeScript helpers tested in
frontend/src/utils/charts.test.ts — keeping them in lock-step matters because
the web charts and the PDF report must show identical numbers.
"""
from types import SimpleNamespace

import pytest

from app.routers.report import (
    aggregate_extraction_field,
    aggregate_taxonomy,
    aggregate_venue_types,
    categorize_venue,
    compute_qa_bins,
    compute_qa_stats,
    pick_first_select_field,
)


class TestComputeQaBins:
    def test_returns_ten_bins(self):
        bins = compute_qa_bins([], 50, 75)
        assert len(bins) == 10
        assert [b["lower"] for b in bins] == list(range(0, 100, 10))
        for b in bins:
            assert b["low"] == b["medium"] == b["high"] == 0

    def test_splits_threshold_straddling_bin_by_per_paper_band(self):
        # Bin [70, 80) with default thresholds — 70/74 are medium, 75/79 are high.
        bins = compute_qa_bins([70, 74, 75, 79], 50, 75)
        assert bins[7]["count"] == 4
        assert bins[7]["medium"] == 2
        assert bins[7]["high"] == 2
        # The dominant-band annotation tracks the per-bin majority (tie → higher).
        assert bins[7]["band"] == "high"

    def test_per_band_split_sums_to_count(self):
        bins = compute_qa_bins([5, 55, 80], 50, 75)
        for b in bins:
            assert b["low"] + b["medium"] + b["high"] == b["count"]

    def test_assigns_scores_to_correct_bin(self):
        bins = compute_qa_bins([0, 49.9, 50, 80], 50, 75)
        assert bins[0]["count"] == 1
        assert bins[4]["count"] == 1
        assert bins[5]["count"] == 1
        assert bins[8]["count"] == 1

    def test_100_lands_in_top_bin(self):
        bins = compute_qa_bins([100], 50, 75)
        assert bins[9]["count"] == 1

    def test_out_of_range_scores_are_clamped(self):
        bins = compute_qa_bins([-5, 250], 50, 75)
        assert bins[0]["count"] == 1
        assert bins[9]["count"] == 1

    def test_skips_none_and_nan(self):
        bins = compute_qa_bins([None, float("nan")], 50, 75)
        assert all(b["count"] == 0 for b in bins)

    def test_band_assignment_with_default_thresholds(self):
        bins = compute_qa_bins([], 50, 75)
        bands = [b["band"] for b in bins]
        assert bands == [
            "low", "low", "low", "low", "low",
            "medium", "medium", "medium",
            "high", "high",
        ]

    def test_band_assignment_with_custom_thresholds(self):
        bins = compute_qa_bins([], 30, 60)
        bands = [b["band"] for b in bins]
        assert bands == [
            "low", "low", "low",
            "medium", "medium", "medium",
            "high", "high", "high", "high",
        ]


class TestComputeQaStats:
    def test_zero_for_empty_input(self):
        assert compute_qa_stats([]) == {"n": 0, "mean": 0.0, "median": 0.0}

    def test_odd_length_median_is_middle(self):
        s = compute_qa_stats([10, 30, 80])
        assert s["n"] == 3
        assert s["mean"] == pytest.approx(40)
        assert s["median"] == 30

    def test_even_length_median_is_average(self):
        s = compute_qa_stats([20, 40, 60, 100])
        assert s["mean"] == 55
        assert s["median"] == 50


class TestAggregateTaxonomy:
    PAPERS = [
        {"values": {"contribution_type": "Tool", "research_type": "Validation"}},
        {"values": {"contribution_type": "Tool", "research_type": "Evaluation"}},
        {"values": {"contribution_type": "Framework", "research_type": "Validation"}},
        {"values": {}},
    ]

    def test_sorts_by_count_descending_then_alphabetically(self):
        rows = aggregate_taxonomy(self.PAPERS, "contribution_type",
                                  ["Framework", "Method", "Theory", "Tool"])
        assert [r["value"] for r in rows] == ["Tool", "Framework", "Method", "Theory"]
        assert [r["count"] for r in rows] == [2, 1, 0, 0]

    def test_unseen_schema_categories_render_with_zero(self):
        rows = aggregate_taxonomy([], "contribution_type", ["Framework", "Tool"])
        assert len(rows) == 2
        assert all(r["count"] == 0 for r in rows)

    def test_values_outside_schema_are_appended(self):
        rows = aggregate_taxonomy(
            [{"values": {"contribution_type": "Pattern"}}],
            "contribution_type", ["Tool"],
        )
        assert any(r["value"] == "Pattern" for r in rows)

    def test_percentages_are_share_of_total_paper_count(self):
        rows = aggregate_taxonomy(self.PAPERS, "contribution_type",
                                  ["Framework", "Tool"])
        # 4 papers total, 2 are "Tool" → 50%.
        tool = next(r for r in rows if r["value"] == "Tool")
        assert tool["percentage"] == pytest.approx(50.0)


class TestAggregateExtractionField:
    def test_counts_and_sorts(self):
        rows = aggregate_extraction_field(
            [
                {"values": {"usage": "Direct"}},
                {"values": {"usage": "Indirect"}},
                {"values": {"usage": "Direct"}},
                {"values": {"usage": ""}},
                {"values": {}},
            ],
            "usage",
        )
        assert [r["value"] for r in rows] == ["Direct", "Indirect"]
        assert [r["count"] for r in rows] == [2, 1]

    def test_empty_when_no_paper_has_field(self):
        assert aggregate_extraction_field([{"values": {}}], "usage") == []


class TestCategorizeVenue:
    """Pin the categorize_venue table so web and PDF stay in lock-step."""

    def test_article_returns_journal(self):
        assert categorize_venue("article", "IEEE TSE") == "Journal"

    def test_inproceedings_returns_conference(self):
        assert categorize_venue("inproceedings", "ICSE 2024") == "Conference"

    def test_inproceedings_with_workshop_venue_returns_workshop(self):
        assert categorize_venue("inproceedings", "Workshop on SE") == "Workshop"

    def test_incollection_returns_book_chapter(self):
        assert categorize_venue("incollection", "Handbook of SE") == "Book chapter"

    def test_techreport_returns_technical_report(self):
        assert categorize_venue("techreport", "TR-2023-1") == "Technical report"

    def test_phdthesis_returns_thesis(self):
        assert categorize_venue("phdthesis", None) == "Thesis"

    def test_mastersthesis_returns_thesis(self):
        assert categorize_venue("mastersthesis", None) == "Thesis"

    # ── Keyword fallback when entry_type is null ──────────────────────────────

    def test_null_entry_conference_venue(self):
        assert categorize_venue(None, "Proceedings of ICSE 2024") == "Conference"
        assert categorize_venue(None, "International Symposium on SE") == "Conference"

    def test_null_entry_workshop_venue_takes_priority_over_conference(self):
        assert categorize_venue(None, "Proceedings of the Workshop on SE") == "Workshop"

    def test_null_entry_journal_venue(self):
        assert categorize_venue(None, "IEEE Transactions on Software Engineering") == "Journal"
        assert categorize_venue(None, "Journal of Systems and Software") == "Journal"

    def test_null_entry_thesis_venue(self):
        assert categorize_venue(None, "PhD thesis, TU Wien") == "Thesis"

    def test_null_entry_technical_report_venue(self):
        assert categorize_venue(None, "Technical report TR-2023-1") == "Technical report"

    def test_null_entry_null_venue_returns_other(self):
        assert categorize_venue(None, None) == "Other"
        assert categorize_venue("", "") == "Other"

    def test_regression_all_null_entry_types_categorise_correctly(self):
        """Bug regression: legacy imports with entry_type=None must not all be 'Other'."""
        papers = [
            type("P", (), {"entry_type": None, "venue": "IEEE Transactions on Software Engineering"})(),
            type("P", (), {"entry_type": None, "venue": "Proceedings of ICSE 2024"})(),
            type("P", (), {"entry_type": None, "venue": "Workshop on Empirical SE"})(),
            type("P", (), {"entry_type": None, "venue": "Some obscure venue"})(),
        ]
        rows = aggregate_venue_types(papers)
        by = {r["value"]: r["count"] for r in rows}
        assert by.get("Journal") == 1
        assert by.get("Conference") == 1
        assert by.get("Workshop") == 1
        assert by.get("Other") == 1
        # Key regression guard: total must NOT be all "Other"
        assert by.get("Other") != 4


class TestPickFirstSelectField:
    @staticmethod
    def _field(id_, name, type_, order):
        return SimpleNamespace(
            id=id_, field_name=name, field_label=name.title(),
            field_type=type_, sort_order=order,
        )

    def test_skips_text_and_taxonomy_dimensions(self):
        fields = [
            self._field(1, "contribution_type", "dropdown", 0),
            self._field(2, "notes", "text", 1),
            self._field(3, "usage", "dropdown", 2),
        ]
        picked = pick_first_select_field(fields, ["contribution_type"])
        assert picked.field_name == "usage"

    def test_returns_none_when_no_select_field(self):
        fields = [self._field(1, "notes", "text", 0)]
        assert pick_first_select_field(fields, []) is None

    def test_returns_none_when_all_selects_are_taxonomies(self):
        fields = [
            self._field(1, "contribution_type", "dropdown", 0),
            self._field(2, "research_type", "dropdown", 1),
        ]
        assert pick_first_select_field(fields, ["contribution_type", "research_type"]) is None
