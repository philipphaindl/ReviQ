"""Term harvest for widening blocks (C.4, step 1)."""

from app.judging.search.harvest import occurs_in_dev, tfidf_terms

DEV = ["AI readiness index for SMEs", "An AI readiness index and its validation",
       "Readiness index of public agencies"]
BACKGROUND = ["Protein folding with deep networks", "AI for weather forecasting",
              "Graph neural networks for chemistry"]


def test_terms_frequent_in_dev_and_rare_in_the_field_rank_first():
    terms = [t for t, _ in tfidf_terms(DEV, BACKGROUND, top=5)]
    assert "readiness index" in terms[:3]
    assert "networks" not in terms


def test_a_jury_suggestion_counts_only_if_it_occurs_in_dev():
    assert occurs_in_dev("readiness index", DEV)
    assert not occurs_in_dev("maturity grid", DEV)
