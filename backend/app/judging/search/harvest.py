"""Term harvest for widening a block (C.4, step 1).

Objective first: which words and two-word phrases are frequent in the titles,
abstracts and keywords of QGS-dev but rare in a random sample of the field
(TF-IDF with the sample as background). Jury suggestions are added later and
count only if they occur at least once in QGS-dev — `occurs_in_dev` is that
check. TF-IDF is written out here because it is four lines; the formula is the
usual smoothed one (idf = ln((1 + N) / (1 + df)) + 1).
"""

from __future__ import annotations

import math
from collections import Counter

from .boolean import occurrences, tokens

STOPWORDS = frozenset("""
a an and are as at be by for from has have in into is it its of on or that the
their this to was were which with we our these those using use based study paper
""".split())


def _ngrams(text: str) -> list[str]:
    words = [w for w in tokens(text)]
    grams = [w for w in words if w not in STOPWORDS and len(w) > 2 and not w.isdigit()]
    grams += [f"{a} {b}" for a, b in zip(words, words[1:])
              if a not in STOPWORDS and b not in STOPWORDS]
    return grams


def tfidf_terms(dev_texts: list[str], background_texts: list[str], top: int = 30
                ) -> list[tuple[str, float]]:
    documents = dev_texts + background_texts
    df: Counter[str] = Counter()
    for text in documents:
        df.update(set(_ngrams(text)))
    tf: Counter[str] = Counter()
    for text in dev_texts:
        tf.update(_ngrams(text))
    n = len(documents)
    scores = {term: count * (math.log((1 + n) / (1 + df[term])) + 1)
              for term, count in tf.items()}
    return sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))[:top]


def occurs_in_dev(term: str, dev_texts: list[str]) -> bool:
    return any(occurrences(tokens(text), term) for text in dev_texts)
