"""
Inter-rater agreement calculations.

Implements Cohen's κ, PABAK, and 95% CI following:
- Cohen (1960) for κ
- Byrt, Bishop & Carlin (1993) for PABAK
- Landis & Koch (1977) for interpretation thresholds
"""
import math
from dataclasses import dataclass


@dataclass
class KappaResult:
    kappa: float
    kappa_ci_lower: float
    kappa_ci_upper: float
    pabak: float
    observed_agreement: float
    n_papers: int
    n_agree_include: int
    n_agree_exclude: int
    n_disagree: int
    interpretation: str


LANDIS_KOCH = [
    (1.00, "Perfect agreement"),
    (0.81, "Almost perfect agreement"),
    (0.61, "Substantial agreement"),
    (0.41, "Moderate agreement"),
    (0.21, "Fair agreement"),
    (0.00, "Slight agreement"),
    (float("-inf"), "Poor agreement (less than chance)"),
]


def interpret_kappa(kappa: float) -> str:
    for threshold, label in LANDIS_KOCH:
        if kappa >= threshold:
            return label
    return "Poor agreement"


def calculate_kappa(
    r1_decisions: dict[str, str],
    r2_decisions: dict[str, str],
) -> KappaResult | None:
    """
    Calculate Cohen's κ between two reviewers.

    r1_decisions and r2_decisions are dicts mapping paper_id (or citekey) → decision ("I", "E", "U").
    Only papers present in both dicts are included.
    U (Uncertain) counts as a distinct category — not as agreement or abstention.
    """
    common_keys = set(r1_decisions.keys()) & set(r2_decisions.keys())
    n = len(common_keys)
    if n == 0:
        return None

    # Build 3×3 confusion matrix: rows = R1, cols = R2, categories = I, E, U
    categories = ["I", "E", "U"]
    matrix = {r: {c: 0 for c in categories} for r in categories}

    for key in common_keys:
        d1 = r1_decisions[key]
        d2 = r2_decisions[key]
        if d1 not in categories:
            d1 = "U"
        if d2 not in categories:
            d2 = "U"
        matrix[d1][d2] += 1

    # Observed agreement (Po)
    po = sum(matrix[c][c] for c in categories) / n

    # Expected agreement (Pe)
    row_totals = {r: sum(matrix[r][c] for c in categories) for r in categories}
    col_totals = {c: sum(matrix[r][c] for r in categories) for c in categories}
    pe = sum((row_totals[c] / n) * (col_totals[c] / n) for c in categories)

    if abs(1 - pe) < 1e-10:
        kappa = 1.0 if po >= 1.0 else 0.0
    else:
        kappa = (po - pe) / (1 - pe)

    # PABAK (Prevalence- and Bias-Adjusted Kappa)
    pabak = 2 * po - 1

    # Asymptotic 95% CI for kappa (Fleiss et al.)
    se = _kappa_se(matrix, n, po, pe, categories)
    z = 1.96
    ci_lower = kappa - z * se
    ci_upper = kappa + z * se

    n_agree_include = matrix["I"]["I"]
    n_agree_exclude = matrix["E"]["E"]
    n_disagree = n - sum(matrix[c][c] for c in categories)

    return KappaResult(
        kappa=round(kappa, 4),
        kappa_ci_lower=round(ci_lower, 4),
        kappa_ci_upper=round(ci_upper, 4),
        pabak=round(pabak, 4),
        observed_agreement=round(po, 4),
        n_papers=n,
        n_agree_include=n_agree_include,
        n_agree_exclude=n_agree_exclude,
        n_disagree=n_disagree,
        interpretation=interpret_kappa(kappa),
    )


def _kappa_se(
    matrix: dict,
    n: int,
    po: float,
    pe: float,
    categories: list[str],
) -> float:
    """Compute the standard error of κ using the formula from Fleiss (1981)."""
    if n <= 1 or abs(1 - pe) < 1e-10:
        return 0.0

    row_totals = {r: sum(matrix[r][c] for c in categories) for r in categories}
    col_totals = {c: sum(matrix[r][c] for r in categories) for c in categories}

    term1 = po * (1 - po)
    term2 = 2 * (1 - po) * (
        2 * po * pe - sum(
            (row_totals[c] / n + col_totals[c] / n) * (matrix[c][c] / n)
            for c in categories
        )
    )
    term3 = (1 - po) ** 2 * (
        sum(
            (row_totals[r] / n) * (col_totals[c] / n) * ((row_totals[r] / n) + (col_totals[c] / n)) ** 2
            for r in categories
            for c in categories
        )
        - 4 * pe ** 2
    )

    variance_num = term1 + term2 + term3
    if variance_num < 0:
        variance_num = 0.0
    variance = variance_num / (n * (1 - pe) ** 2)
    return math.sqrt(variance)
