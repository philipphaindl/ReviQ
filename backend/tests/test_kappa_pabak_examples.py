"""Verification tests against published κ / PABAK examples.

These pin the calculations against the literature the manuscript cites so a
future refactor cannot silently change the published κ numbers.
"""
import pytest

from app.services.kappa_service import calculate_kappa, interpret_kappa


class TestByrtPABAKExample:
    """Byrt, Bishop & Carlin (1993), Table I.

    Their illustrative 2×2 table has 80% observed agreement, from which
    PABAK = 2 * 0.80 - 1 = 0.60. Reproduce that here.
    """

    def test_pabak_matches_byrt_example(self):
        # 80 papers, 80% observed agreement, balanced disagreement.
        agree_include = 30
        agree_exclude = 50
        disagree = 20
        r1 = {}
        r2 = {}
        idx = 0
        for _ in range(agree_include): r1[f"p{idx}"] = "I"; r2[f"p{idx}"] = "I"; idx += 1
        for _ in range(agree_exclude): r1[f"p{idx}"] = "E"; r2[f"p{idx}"] = "E"; idx += 1
        for i in range(disagree):
            d1, d2 = ("I", "E") if i % 2 == 0 else ("E", "I")
            r1[f"p{idx}"] = d1; r2[f"p{idx}"] = d2; idx += 1

        result = calculate_kappa(r1, r2)
        assert result is not None
        assert result.n_papers == 100
        assert result.observed_agreement == pytest.approx(0.80, abs=1e-4)
        assert result.pabak == pytest.approx(0.60, abs=1e-4)

    def test_pabak_equals_2po_minus_1_invariant(self):
        # PABAK is defined as 2*Po - 1 regardless of category distribution.
        r1 = {f"p{i}": ("I" if i < 70 else "E") for i in range(100)}
        r2 = {f"p{i}": ("I" if i < 60 else "E") for i in range(100)}
        result = calculate_kappa(r1, r2)
        assert result is not None
        assert result.pabak == pytest.approx(2 * result.observed_agreement - 1, abs=1e-4)


class TestLandisKochThresholds:
    """Landis & Koch (1977) interpretation cut-points."""

    @pytest.mark.parametrize("kappa,expected", [
        (1.0,   "Perfect agreement"),
        (0.81,  "Almost perfect agreement"),
        (0.80,  "Substantial agreement"),
        (0.61,  "Substantial agreement"),
        (0.60,  "Moderate agreement"),
        (0.41,  "Moderate agreement"),
        (0.40,  "Fair agreement"),
        (0.21,  "Fair agreement"),
        (0.20,  "Slight agreement"),
        (0.0,   "Slight agreement"),
        (-0.01, "Poor agreement (less than chance)"),
    ])
    def test_thresholds(self, kappa, expected):
        assert interpret_kappa(kappa) == expected


class TestKappaSyntheticEdgeCases:
    def test_all_agree_returns_unit_kappa(self):
        r1 = {f"p{i}": "I" for i in range(20)}
        r2 = {f"p{i}": "I" for i in range(20)}
        result = calculate_kappa(r1, r2)
        assert result is not None
        # With pe = 1 and po = 1, kappa is reported as 1.0 by definition.
        assert result.kappa == pytest.approx(1.0, abs=1e-6)
        assert result.observed_agreement == 1.0
        assert result.n_disagree == 0

    def test_all_disagree_yields_zero_observed_agreement(self):
        r1 = {f"p{i}": "I" for i in range(10)}
        r2 = {f"p{i}": "E" for i in range(10)}
        result = calculate_kappa(r1, r2)
        assert result is not None
        assert result.observed_agreement == 0.0
        assert result.n_disagree == 10
        # PABAK = 2*0 - 1 = -1 for total disagreement.
        assert result.pabak == pytest.approx(-1.0, abs=1e-4)

    def test_single_category_collapses_to_unit_kappa(self):
        # Both reviewers only ever say "Include" → no variation in either marginal.
        r1 = {f"p{i}": "I" for i in range(5)}
        r2 = {f"p{i}": "I" for i in range(5)}
        result = calculate_kappa(r1, r2)
        assert result is not None
        assert result.kappa == pytest.approx(1.0, abs=1e-6)

    def test_kappa_confidence_interval_brackets_point_estimate(self):
        # Synthetic, somewhat-noisy data — assert CI ordering.
        r1 = {f"p{i}": ("I" if i % 3 == 0 else "E") for i in range(30)}
        r2 = {f"p{i}": ("I" if i % 4 == 0 else "E") for i in range(30)}
        result = calculate_kappa(r1, r2)
        assert result is not None
        assert result.kappa_ci_lower <= result.kappa <= result.kappa_ci_upper

    def test_uncertain_counts_as_distinct_category(self):
        # U must not be silently merged with E or I.
        r1 = {f"p{i}": "U" for i in range(5)}
        r2 = {f"p{i}": "E" for i in range(5)}
        result = calculate_kappa(r1, r2)
        assert result is not None
        # All disagree because U ≠ E.
        assert result.n_disagree == 5
