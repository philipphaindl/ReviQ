"""Candidate strings and the selection rule (C.4)."""

from dataclasses import dataclass

from app.judging.search import candidates, concepts

STRINGS = concepts.load()


@dataclass
class Record:
    title: str
    abstract: str = ""
    keywords: str = ""


def test_variants_cover_ablation_proximities_relaxation_and_widening():
    out = candidates.variants(STRINGS["S1"], {"M": ("maturity model", "maturity index")})
    labels = [c.variant for c in out]
    assert labels[0] == "base"
    assert "without (M)" in labels and "without (A W/5 O)" in labels
    assert "A W/5 O -> W/3" in labels and "A W/5 O -> W/10" in labels
    assert "A W/5 O -> AND" in labels
    # Only terms not already in the block widen it.
    assert "M + maturity index" in labels
    assert len({c.string.name for c in out}) == len(out)


def test_measure_counts_dev_records_the_string_finds():
    dev = [Record("Artificial intelligence adoption: a maturity model for SMEs"),
           Record("Deep learning for image segmentation")]
    m = candidates.measure(candidates.Candidate(STRINGS["S1"], "S1", "base"), dev)
    assert (m.dev_matched, m.dev_total, m.sensitivity) == (1, 2, 0.5)


def _m(name, sensitivity, hits, precision, terms_from="S1"):
    string = STRINGS[terms_from].with_clauses(name, STRINGS[terms_from].clauses)
    return candidates.Measurement(candidates.Candidate(string, "S1", name),
                                  round(sensitivity * 100), 100, hits, precision)


def test_selection_maximises_precision_under_sensitivity_and_budget():
    ms = [_m("a", 0.95, 900, 0.30), _m("b", 0.92, 800, 0.45),
          _m("c", 0.85, 300, 0.90), _m("d", 0.97, 5000, 0.80)]
    chosen = candidates.select(ms, budget=1000)
    assert chosen.chosen.candidate.variant == "b"


def test_a_tie_on_precision_goes_to_the_shorter_string():
    short = candidates.Measurement(
        candidates.Candidate(candidates.variants(STRINGS["S1"])[1].string, "S1", "short"),
        95, 100, 500, 0.5)
    long = _m("long", 0.95, 500, 0.5)
    assert candidates.select([long, short], budget=1000).chosen.candidate.variant == "short"


def test_no_selection_without_precision_estimates():
    result = candidates.select([_m("a", 0.95, 500, None)], budget=1000)
    assert result.chosen is None and "no precision" in result.reason
