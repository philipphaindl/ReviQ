"""Local Boolean evaluation of canonical strings (C.4, quasi-sensitivity)."""

from app.judging.search import concepts
from app.judging.search.boolean import matches, occurrences, record_text, tokens

STRINGS = concepts.load()


def test_tokens_fold_case_accents_and_hyphens():
    assert tokens("AI-based Governance, Ärger!") == ["ai", "based", "governance", "arger"]


def test_a_phrase_matches_only_as_a_word_sequence():
    words = tokens("large language models in practice")
    assert occurrences(words, "large language models") == [(0, 3)]
    assert occurrences(words, "language large") == []


def test_s1_needs_ai_near_adoption_and_a_model_artefact():
    hit = "Artificial intelligence adoption in firms: a maturity model"
    assert matches(STRINGS["S1"], hit)
    no_model = "Artificial intelligence adoption in firms: an interview study"
    assert not matches(STRINGS["S1"], no_model)


def test_proximity_counts_the_words_between_in_either_order():
    s1 = STRINGS["S1"]
    near = "A maturity model. We study governance of machine learning in banks."
    assert matches(s1, near)                       # 'governance of machine learning'
    far = ("Machine learning teams were observed with care and with many words in between "
           "before the text finally mentions governance; it proposes a quality model.")
    assert not matches(s1, far)


def test_a_phrase_cannot_reach_across_two_fields():
    text = record_text("Readiness", "model of AI systems adoption", None)
    assert not matches(STRINGS["S1"], text)        # 'readiness model' spans the field break


def test_s2_needs_context_and_evidence_terms():
    s2 = STRINGS["S2"]
    assert matches(s2, "Barriers to the adoption of artificial intelligence in SMEs")
    assert not matches(s2, "Adoption of artificial intelligence in SMEs")
