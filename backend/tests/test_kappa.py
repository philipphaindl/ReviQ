"""Tests for Cohen's κ calculation (SX5 requirement)."""
import pytest
from app.services.kappa_service import calculate_kappa, interpret_kappa


class TestKappaCalculation:
    def test_perfect_agreement_include(self):
        r1 = {'p1': 'I', 'p2': 'I', 'p3': 'E', 'p4': 'E'}
        r2 = {'p1': 'I', 'p2': 'I', 'p3': 'E', 'p4': 'E'}
        result = calculate_kappa(r1, r2)
        assert result is not None
        assert result.kappa == pytest.approx(1.0, abs=0.01)
        assert result.observed_agreement == pytest.approx(1.0, abs=0.01)
        assert result.n_disagree == 0

    def test_zero_agreement(self):
        r1 = {'p1': 'I', 'p2': 'I'}
        r2 = {'p1': 'E', 'p2': 'E'}
        result = calculate_kappa(r1, r2)
        assert result is not None
        assert result.observed_agreement == pytest.approx(0.0, abs=0.01)
        assert result.n_disagree == 2

    def test_partial_agreement(self):
        r1 = {'p1': 'I', 'p2': 'I', 'p3': 'E', 'p4': 'E'}
        r2 = {'p1': 'I', 'p2': 'E', 'p3': 'E', 'p4': 'I'}
        result = calculate_kappa(r1, r2)
        assert result is not None
        assert result.n_papers == 4
        # 2 agreements (p1, p3) out of 4
        assert result.observed_agreement == pytest.approx(0.5, abs=0.01)

    def test_uncertain_counts_as_disagreement(self):
        """U must not be treated as abstention."""
        r1 = {'p1': 'I', 'p2': 'U'}
        r2 = {'p1': 'I', 'p2': 'E'}
        result = calculate_kappa(r1, r2)
        assert result is not None
        assert result.n_disagree == 1

    def test_only_common_papers_included(self):
        r1 = {'p1': 'I', 'p2': 'E', 'p3': 'I'}
        r2 = {'p1': 'I', 'p2': 'E'}  # p3 not reviewed by R2
        result = calculate_kappa(r1, r2)
        assert result is not None
        assert result.n_papers == 2  # only p1 and p2

    def test_no_common_papers_returns_none(self):
        r1 = {'p1': 'I'}
        r2 = {'p2': 'E'}
        result = calculate_kappa(r1, r2)
        assert result is None

    def test_empty_decisions_returns_none(self):
        result = calculate_kappa({}, {})
        assert result is None

    def test_kappa_range(self):
        """κ is always in [-1, 1]."""
        r1 = {'p1': 'I', 'p2': 'E', 'p3': 'U', 'p4': 'I', 'p5': 'E'}
        r2 = {'p1': 'E', 'p2': 'I', 'p3': 'I', 'p4': 'E', 'p5': 'U'}
        result = calculate_kappa(r1, r2)
        assert result is not None
        assert -1.0 <= result.kappa <= 1.0

    def test_pabak_formula(self):
        """PABAK = 2*Po - 1."""
        r1 = {'p1': 'I', 'p2': 'I', 'p3': 'E', 'p4': 'E', 'p5': 'I'}
        r2 = {'p1': 'I', 'p2': 'E', 'p3': 'E', 'p4': 'I', 'p5': 'I'}
        result = calculate_kappa(r1, r2)
        assert result is not None
        expected_pabak = 2 * result.observed_agreement - 1
        assert result.pabak == pytest.approx(expected_pabak, abs=0.001)

    def test_ci_lower_le_upper(self):
        r1 = {'p1': 'I', 'p2': 'E', 'p3': 'I', 'p4': 'E', 'p5': 'I', 'p6': 'E'}
        r2 = {'p1': 'I', 'p2': 'E', 'p3': 'E', 'p4': 'I', 'p5': 'I', 'p6': 'E'}
        result = calculate_kappa(r1, r2)
        assert result is not None
        assert result.kappa_ci_lower <= result.kappa
        assert result.kappa <= result.kappa_ci_upper

    def test_known_jvmti_value(self):
        """
        The JVMTI SLR had κ = 0.453 for the DB stream.
        We can't reproduce exact data, but we verify the function returns
        a reasonable value for a moderate-agreement scenario.
        """
        r1 = {str(i): ('I' if i % 3 == 0 else 'E') for i in range(20)}
        r2 = {str(i): ('I' if i % 3 <= 1 else 'E') for i in range(20)}
        result = calculate_kappa(r1, r2)
        assert result is not None
        assert 0.0 <= result.kappa <= 1.0


class TestKappaInterpretation:
    def test_perfect(self):
        assert interpret_kappa(1.0) == "Perfect agreement"

    def test_almost_perfect(self):
        assert interpret_kappa(0.85) == "Almost perfect agreement"

    def test_substantial(self):
        assert interpret_kappa(0.65) == "Substantial agreement"

    def test_moderate(self):
        assert interpret_kappa(0.50) == "Moderate agreement"

    def test_fair(self):
        assert interpret_kappa(0.30) == "Fair agreement"

    def test_slight(self):
        assert interpret_kappa(0.10) == "Slight agreement"

    def test_poor(self):
        assert interpret_kappa(-0.10) == "Poor agreement (less than chance)"
