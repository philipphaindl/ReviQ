"""The language a document declares about itself.

`language` was null for all 358 usable documents of the pilot corpus, because
trafilatura fills that field only when a language-detection package is
installed and this project does not depend on one. Language is a standard
inclusion criterion in a multivocal review, so an always-empty column is a
silent hole in the protocol.
"""

import pytest

from glr.extract import declared_language


def page(head: str, html_attrs: str = "") -> bytes:
    return (f"<!DOCTYPE html><html{html_attrs}><head>{head}</head>"
            f"<body><p>Text.</p></body></html>").encode("utf-8")


def test_the_lang_attribute_is_read():
    assert declared_language(page("", ' lang="de"')) == "de"


def test_a_region_is_kept_and_lowercased():
    """`de-AT` and `de` are both German; a consumer filtering on language takes
    the part before the hyphen, and the region stays available for one that
    wants it."""
    assert declared_language(page("", ' lang="de-AT"')) == "de-at"


def test_og_locale_underscores_become_hyphens():
    assert declared_language(page('<meta property="og:locale" content="de_AT">')) == "de-at"


def test_content_language_header_equivalent():
    assert declared_language(
        page('<meta http-equiv="Content-Language" content="fr">')
    ) == "fr"


def test_xml_lang_is_accepted():
    assert declared_language(page("", ' xml:lang="nl"')) == "nl"


def test_the_html_attribute_wins_over_og_locale():
    """og:locale describes the page as shared on a platform and is the most
    likely of the three to be a site-wide default rather than this document."""
    content = page('<meta property="og:locale" content="en_US">', ' lang="de"')
    assert declared_language(content) == "de"


def test_content_language_wins_over_og_locale():
    content = page('<meta property="og:locale" content="en_US">'
                   '<meta http-equiv="content-language" content="sv">')
    assert declared_language(content) == "sv"


def test_a_document_declaring_nothing_returns_none():
    assert declared_language(page("")) is None


@pytest.mark.parametrize("value", ["", " ", "x-default", "unknown-language",
                                   "{{ page.lang }}", "12", "e"])
def test_junk_declarations_are_rejected(value):
    """A junk value would silently pass a 'documents in English only' filter.
    An absent value at least shows up as unknown."""
    assert declared_language(page("", f' lang="{value}"')) is None


def test_a_list_of_languages_takes_the_first():
    assert declared_language(
        page('<meta http-equiv="content-language" content="en, de, fr">')
    ) == "en"


def test_declarations_after_the_head_are_ignored():
    """Scanning the whole body would make this cost grow with document size for
    no gain — nothing that declares a document's language lives down there."""
    content = (b'<!DOCTYPE html><html><head><title>x</title></head><body>'
               b'<div lang="zz"><html lang="de"></div></body></html>')
    assert declared_language(content) is None


def test_malformed_markup_does_not_raise():
    assert declared_language(b'<html lang="de"><head><meta charset=</head') == "de"


def test_non_utf8_bytes_do_not_raise():
    assert declared_language(b'<html lang="de"><head>\xff\xfe</head></html>') == "de"


def test_empty_input():
    assert declared_language(b"") is None


def test_a_pdf_declares_nothing_here():
    """PDFs carry a /Lang entry in the catalog that this does not read. They
    stay unknown rather than being guessed at — 71 of 424 documents in the
    pilot corpus."""
    assert declared_language(b"%PDF-1.7\n%\xc3\xa4\xc3\xbc") is None


def test_uppercase_tag_and_attribute_names():
    assert declared_language(b'<HTML LANG="DE"><HEAD></HEAD></HTML>') == "de"
