"""Cost estimates for --dry-run (A.3.6)."""

from app.judging import costs
from app.judging.config import Rung


def test_cost_follows_tokens_and_prices_and_batch_halves_it():
    rung = Rung(model="m", price_in=2.0, price_out=10.0, batch_discount=0.5)
    profile = costs.CallProfile("t", tokens_in=1_000, tokens_out=200)
    est = costs.estimate(1_000, profile, rung)
    assert (est.tokens_in, est.tokens_out) == (1_000_000, 200_000)
    assert est.usd_standard == 4.0 and est.usd_batch == 2.0


def test_adaptive_votes_count_the_anchor_sample_for_every_judge():
    # 100 anchor records x 4 judges + 900 records x 2 judges + 25 % of 900 extra votes
    assert costs.adaptive_votes(1_000, 4, 100, 0.25) == 400 + 1_800 + 225


def test_an_anchor_larger_than_the_corpus_is_capped():
    assert costs.adaptive_votes(50, 3, 100, 0.0) == 150
