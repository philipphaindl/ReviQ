"""The snowballing filter.

These tests encode the four rules from links.py. They matter more than most,
because the filter decides what enters the corpus: too permissive and a review
drowns in navigation links, too strict and real sources are never seen.
"""

from glr.links import extract_anchors, select_snowball_links

BASE = "https://example.org/reports/ai-maturity"

PAGE = b"""<!DOCTYPE html><html><body>
  <nav>
    <a href="/about">About us</a>
    <a href="/reports">All reports</a>
  </nav>
  <article>
    <a href="/downloads/ai-maturity-2026.pdf">Download the full report (PDF)</a>
    <a href="https://oecd.org/ai/policy-observatory">OECD AI Policy Observatory</a>
    <a href="https://standards.example.net/iso-42001">ISO/IEC 42001</a>
    <a href="https://twitter.com/example">Follow us on Twitter</a>
    <a href="https://example.org/privacy">Privacy policy</a>
    <a href="https://partner.example.com/terms">Terms of use</a>
    <a href="#section-2">Jump to section 2</a>
    <a href="mailto:info@example.org">Email us</a>
    <a href="javascript:void(0)">Toggle</a>
  </article>
  <footer><a href="https://linkedin.com/company/example">LinkedIn</a></footer>
</body></html>"""


def _urls(links):
    return [link.resolved_url for link in links]


def test_anchors_are_extracted_with_their_text():
    anchors = extract_anchors(PAGE)
    hrefs = [href for href, _ in anchors]
    assert "/downloads/ai-maturity-2026.pdf" in hrefs
    text = dict(anchors)["/downloads/ai-maturity-2026.pdf"]
    assert text == "Download the full report (PDF)"


def test_pdf_links_are_kept_even_on_the_same_host():
    """Rule 1: in grey literature a linked PDF is usually the document itself.
    The off-host rule must not discard it."""
    links = select_snowball_links(PAGE, BASE)
    pdfs = [link for link in links if link.is_pdf]
    assert len(pdfs) == 1
    assert pdfs[0].resolved_url == "https://example.org/downloads/ai-maturity-2026.pdf"


def test_pdfs_come_first_so_the_cap_never_displaces_them():
    links = select_snowball_links(PAGE, BASE, max_links=1)
    assert len(links) == 1
    assert links[0].is_pdf


def test_off_host_content_links_are_kept():
    urls = _urls(select_snowball_links(PAGE, BASE))
    assert "https://oecd.org/ai/policy-observatory" in urls
    assert "https://standards.example.net/iso-42001" in urls


def test_same_host_navigation_is_dropped():
    """Rule 2: /about and /reports are navigation, not citations."""
    urls = _urls(select_snowball_links(PAGE, BASE))
    assert "https://example.org/about" not in urls
    assert "https://example.org/reports" not in urls


def test_social_and_shortener_hosts_are_dropped():
    urls = _urls(select_snowball_links(PAGE, BASE))
    assert not any("twitter.com" in url for url in urls)
    assert not any("linkedin.com" in url for url in urls)


def test_site_furniture_paths_are_dropped():
    """Rule 3: even off-host, /terms and /privacy are never sources."""
    urls = _urls(select_snowball_links(PAGE, BASE))
    assert not any("/terms" in url for url in urls)
    assert not any("/privacy" in url for url in urls)


def test_non_http_schemes_are_dropped():
    urls = _urls(select_snowball_links(PAGE, BASE))
    assert not any(url.startswith(("mailto:", "javascript:")) for url in urls)
    assert not any("#section-2" in url for url in urls)


def test_relative_links_resolve_against_the_base():
    links = select_snowball_links(b'<a href="../data/report.pdf">x</a>', BASE)
    assert links[0].resolved_url == "https://example.org/data/report.pdf"


def test_subdomains_of_noise_hosts_are_dropped():
    html = b'<a href="https://www.facebook.com/sharer/sharer.php?u=x">Share</a>'
    assert select_snowball_links(html, BASE) == []


def test_duplicate_targets_are_collapsed_by_canonical_url():
    html = (b'<a href="https://oecd.org/ai/">A</a>'
            b'<a href="https://www.oecd.org/ai?utm_source=x">B</a>')
    assert len(select_snowball_links(html, BASE)) == 1


def test_the_cap_is_honoured():
    html = b"".join(
        f'<a href="https://site{i}.example.net/doc">Doc {i}</a>'.encode()
        for i in range(50)
    )
    assert len(select_snowball_links(html, BASE, max_links=20)) == 20


def test_malformed_markup_does_not_raise():
    links = select_snowball_links(b"<a href=https://oecd.org/x>unquoted<<<", BASE)
    assert isinstance(links, list)


def test_a_page_with_no_links_yields_nothing():
    assert select_snowball_links(b"<html><body>text only</body></html>", BASE) == []
