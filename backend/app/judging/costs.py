"""Cost estimates for `--dry-run` (A.3.6).

An estimate, not a bill: token counts are assumptions per call type until a
calibration run has measured them, and prices come from the study
configuration, which records where they were taken from. What the estimate
must get right is the shape — how many calls, on which rung, with and without
batch — because that is what decides whether a run is started at all.
"""

from __future__ import annotations

from dataclasses import dataclass

from .config import Rung


@dataclass(frozen=True)
class CallProfile:
    """Tokens per call for one kind of call."""

    name: str
    tokens_in: int
    tokens_out: int


# Starting assumptions (PLAN.md, section 6); replaced by measured medians once
# the calibration has run.
SCREENING = CallProfile("screening", 1_200, 600)
FULL_TEXT = CallProfile("full-text", 12_000, 800)
EXTRACTION = CallProfile("extraction", 15_000, 2_000)


@dataclass(frozen=True)
class Estimate:
    calls: int
    tokens_in: int
    tokens_out: int
    usd_standard: float
    usd_batch: float


def estimate(calls: int, profile: CallProfile, rung: Rung) -> Estimate:
    tokens_in = calls * profile.tokens_in
    tokens_out = calls * profile.tokens_out
    standard = (tokens_in * rung.price_in + tokens_out * rung.price_out) / 1_000_000
    return Estimate(calls=calls, tokens_in=tokens_in, tokens_out=tokens_out,
                    usd_standard=round(standard, 2),
                    usd_batch=round(standard * rung.batch_discount, 2))


def adaptive_votes(records: int, judges: int, anchor: int, extra_share: float,
                   first_round: int = 2) -> int:
    """Expected number of votes for an adaptive jury (PLAN.md, E1): every judge
    on the anchor sample, `first_round` judges on every other record, one more
    vote on the share of records that stays between the thresholds."""

    anchor = min(anchor, records)
    return anchor * judges + (records - anchor) * first_round + round(
        (records - anchor) * extra_share)
