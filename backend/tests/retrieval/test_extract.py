"""Media type sniffing and extraction dispatch.

detect_media_type is tested exhaustively because it is the cheapest place to
prevent a silent mis-extraction: trusting Content-Type instead would turn a
PDF served as text/html into an empty document rather than an error.
"""

from glr.extract import Extraction, detect_media_type


def test_pdf_is_detected_by_magic_bytes():
    assert detect_media_type(b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n") == "pdf"


def test_html_is_detected_in_several_shapes():
    assert detect_media_type(b"<!DOCTYPE html><html><body>hi</body></html>") == "html"
    assert detect_media_type(b"<html lang='de'><head></head></html>") == "html"
    assert detect_media_type(b"\n\n  <!doctype HTML>\n<html>") == "html"


def test_html_with_a_leading_comment_or_bom():
    assert detect_media_type(b"<!-- generated -->\n<html><body>x</body></html>") == "html"


def test_unknown_payloads_are_other():
    assert detect_media_type(b"\x89PNG\r\n\x1a\n") == "other"
    assert detect_media_type(b'{"key": "value"}') == "other"
    assert detect_media_type(b"") == "other"


def test_pdf_wins_over_an_html_looking_content_type():
    """The exact real-world case: a CMS serving a PDF as text/html. The
    payload decides, not the header."""
    assert detect_media_type(b"%PDF-1.4 <html>not really html</html>") == "pdf"


def test_word_count_is_derived_not_stored():
    assert Extraction(extractor="x", text="one two three").word_count == 3
    assert Extraction(extractor="x", text=None).word_count == 0
    assert Extraction(extractor="x", text="   ").word_count == 0


def test_unsupported_media_type_reports_an_error():
    from glr.extract import extract

    result = extract(b"\x89PNG", "other")
    assert result.text is None
    assert result.error is not None


# --- soft block detection ------------------------------------------------
#
# A WAF page served with HTTP 200 is the most dangerous retrieval failure in a
# review: status, content, text and hash all report success, and a firewall
# notice enters the corpus as a source. Found in the first real run.

F5_BLOCK = (
    b"<html><head><title>Request Rejected</title></head><body>"
    b"<p>The requested URL was rejected. Please consult with your administrator.</p>"
    b"<p>Your support ID is: 12345678901234567890</p></body></html>"
)
CLOUDFLARE_BLOCK = (
    b"<html><head><title>Attention Required! | Cloudflare</title></head>"
    b"<body>Checking your browser before accessing example.org</body></html>"
)


def test_f5_block_page_is_detected():
    from glr.extract import detect_block_page

    text = "The requested URL was rejected. Please consult with your administrator."
    reason = detect_block_page(F5_BLOCK, text)
    assert reason is not None
    assert "F5" in reason


def test_cloudflare_challenge_is_detected():
    from glr.extract import detect_block_page

    assert detect_block_page(CLOUDFLARE_BLOCK, "Checking your browser") is not None


def test_block_marker_only_in_raw_bytes_is_still_caught():
    """Boilerplate removal can strip a <title> that carries the only marker."""
    from glr.extract import detect_block_page

    assert detect_block_page(CLOUDFLARE_BLOCK, "") is not None


def test_a_real_document_is_not_flagged():
    """The length ceiling protects genuine sources. Missing a block page costs
    one flagged row next run; discarding a real source costs a source."""
    from glr.extract import detect_block_page

    text = " ".join(["Organisations progress through five levels of AI maturity."] * 60)
    assert detect_block_page(b"<html><body>...</body></html>", text) is None


def test_a_long_article_mentioning_access_denied_is_not_flagged():
    from glr.extract import detect_block_page

    text = ("Access denied errors are a common symptom of misconfigured "
            "permissions in enterprise deployments. ") * 30
    assert detect_block_page(b"<html><body>", text) is None


def test_ordinary_short_page_is_not_flagged():
    from glr.extract import detect_block_page

    assert detect_block_page(b"<html><body>Short note.</body></html>", "Short note.") is None
