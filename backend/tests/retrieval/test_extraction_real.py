"""Text extraction against the real trafilatura.

Boilerplate removal is the claim that has to hold for a review to be usable:
if navigation, cookie banners and footers end up in the extracted text, every
downstream reading of that text is polluted. It is also the one behaviour that
cannot be verified by reading the code, since it lives entirely inside
trafilatura.

No network, no API keys.
"""

from app.retrieval.extract import extract, extract_html

ARTICLE = b"""<!DOCTYPE html>
<html lang="en">
<head><title>An AI Maturity Model for Public Sector Organisations</title></head>
<body>
  <nav>Home | About | Publications | Contact | Subscribe to our newsletter</nav>
  <div class="cookie-banner">We value your privacy. Accept all cookies?</div>
  <article>
    <h1>An AI Maturity Model for Public Sector Organisations</h1>
    <p>Organisations adopting artificial intelligence progress through five
    distinguishable levels of maturity. At the first level, activity is ad hoc:
    individual teams experiment with models without shared infrastructure,
    documented data provenance, or any agreed evaluation criteria. Results are
    rarely reproducible and almost never transferred between departments.</p>
    <p>The second and third levels introduce repeatable processes. Data
    pipelines become versioned, model training is documented, and evaluation
    moves from anecdote to measurement. Governance remains reactive, however,
    and accountability for deployed systems is often unclear across the
    organisation.</p>
    <p>At the fourth and fifth levels, governance becomes systematic. Model
    inventories are maintained, risk classification is applied before
    deployment rather than after incidents, and monitoring covers both
    technical drift and downstream effects on the people the systems act upon.</p>
    <p>The model presented here was validated through twelve case studies
    conducted across municipal administrations and national agencies between
    2023 and 2025.</p>
  </article>
  <footer>Copyright 2026 Example Institute. All rights reserved.
  Follow us on social media. Privacy policy. Terms of use.</footer>
</body>
</html>"""


def test_main_content_is_extracted():
    result = extract_html(ARTICLE, url="https://example.org/ai-maturity-model")
    assert result.error is None, f"extraction failed: {result.error}"
    assert result.text
    assert "five distinguishable levels of maturity" in result.text
    assert "twelve case studies" in result.text
    assert result.word_count > 100


def test_boilerplate_is_removed():
    """Navigation, cookie banner and footer must not survive into the text."""
    result = extract_html(ARTICLE, url="https://example.org/ai-maturity-model")
    assert result.error is None
    text = result.text.lower()
    for noise in ("subscribe to our newsletter", "accept all cookies",
                  "all rights reserved", "follow us on social media",
                  "privacy policy"):
        assert noise not in text, f"boilerplate leaked into extracted text: {noise!r}"


def test_metadata_is_captured():
    result = extract_html(ARTICLE, url="https://example.org/ai-maturity-model")
    assert result.error is None
    assert result.title and "Maturity Model" in result.title
    assert result.extractor.startswith("trafilatura-")


def test_the_declared_language_reaches_the_extraction():
    """The wiring `test_language.py` cannot check: that field used to come back
    empty for every document, because trafilatura only fills it when a
    detection package is installed."""
    result = extract_html(ARTICLE, url="https://example.org/ai-maturity-model")
    assert result.language == "en"


def test_dispatch_routes_html_to_trafilatura():
    result = extract(ARTICLE, "html", url="https://example.org/ai-maturity-model")
    assert result.extractor.startswith("trafilatura-")
    assert result.word_count > 100


def test_contentless_page_reports_an_error_not_empty_text():
    """A page with nothing to extract must be distinguishable from a page that
    was never fetched — otherwise the CSV cannot be triaged."""
    result = extract_html(b"<!DOCTYPE html><html><body></body></html>",
                          url="https://example.org/empty")
    assert result.word_count == 0
    assert result.error is not None
