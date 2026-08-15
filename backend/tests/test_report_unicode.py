"""What the PDF can and cannot set.

The report used to run on fpdf2's core fonts, which are latin-1. `_s` therefore
forced every string into that range, and anything outside it became a run of
question marks. For a review of peer-reviewed literature that was survivable;
for a multivocal one it is not, because grey literature comes off the open web.
A Cyrillic or Greek title reached the published PDF as `??????`.

The report now embeds DejaVu Serif. These tests pin both halves of the result:
what renders as itself, and where the limit still is. The second half matters as
much as the first — the old replacement table grew by whack-a-mole, and `‐`
(U+2010, an ordinary hyphen variant) was still missing from it years in.
"""
from __future__ import annotations

import pytest

from app.routers.report import (
    _FONT, _FONT_DIR, _FONT_FILES, _RL_STYLES, _Report,
    _register_reportlab_fonts, _s,
)


def render(text: str) -> bytes:
    """Set one line and produce the PDF. Raises if the engine refuses the text."""
    pdf = _Report("Title")
    pdf._is_cover = False
    pdf.add_page()
    pdf.set_font(_FONT, "", 11)
    pdf.cell(0, 8, _s(text))
    return bytes(pdf.output())


# --- the font is actually there -------------------------------------------


def test_every_declared_style_ships_with_the_repo():
    """A missing style would only surface when some heading first used it."""
    for style, filename in _FONT_FILES.items():
        assert (_FONT_DIR / filename).is_file(), f"missing {filename} for style {style!r}"


def test_the_family_is_not_named_after_a_core_font():
    """fpdf2 answers `add_font("Times", …)` with a warning and keeps its own
    latin-1 builtin, so a family named after a core font is silently ignored and
    every non-latin-1 character starts raising again."""
    assert _FONT.lower() not in {"times", "helvetica", "courier", "symbol", "zapfdingbats"}


# --- what now renders as itself -------------------------------------------


@pytest.mark.parametrize("label,text", [
    ("cyrillic", "Модель зрелости искусственного интеллекта"),
    ("greek", "Μοντέλο ωρίμανσης"),
    ("latin-extended", "Yapay Zekâ Olgunluk Modeli — Üniversite"),
    ("curly quotes", "We’ve just launched the “AI Maturity” tool"),
    ("hyphen U+2010", "AI‐Maturity Assessment"),
    ("dashes and ellipsis", "AI — maturity … models"),
    ("maths", "κ ≥ 0.61, p ≤ 0.05, n × 2"),
])
def test_it_renders(label, text):
    assert render(text)


def test_the_text_is_no_longer_flattened_to_ascii():
    """`_s` used to replace curly quotes, dashes and kappa with ASCII stand-ins
    before encoding. With a Unicode font that loss is unnecessary."""
    assert _s("We’ve — κ ≥ 0.61") == "We’ve — κ ≥ 0.61"


def test_a_real_grey_title_survives():
    """From the pilot corpus. Its apostrophe is U+2019, which the old table
    happened to cover — the point is that it now needs no special case."""
    title = "We’ve just launched the AI Maturity Self Assessment tool"
    assert _s(title) == title
    assert render(title)


# --- where the limit still is ---------------------------------------------


@pytest.mark.parametrize("label,text", [
    ("cjk", "AI成熟度モデル"),
    ("emoji", "AI Maturity 🚀"),
])
def test_a_script_the_font_does_not_carry_degrades_rather_than_raising(label, text):
    """DejaVu Serif has no CJK and no emoji. fpdf2 warns and drops the glyph.

    A report that renders with a few characters missing is worth more to a user
    than an exception at download time, and the record stays reachable through
    the dataset view where the title is shown in the browser's own fonts.
    Covering these means embedding a second, far larger font — a separate
    decision, recorded here as a known limit rather than left to be discovered.
    """
    assert render(text)


def test_the_pipe_is_still_replaced():
    """Not a glyph problem: `|` separates table cells in this report."""
    assert "|" not in _s("Model | Framework")


# --- the truncation contract ----------------------------------------------


def test_maxlen_still_truncates_with_an_ellipsis():
    assert _s("x" * 100, 20) == "x" * 17 + "..."


def test_maxlen_counts_characters_not_bytes():
    """Cyrillic is two bytes per character in UTF-8. Truncating on bytes would
    cut a title mid-character and could split a surrogate pair."""
    assert len(_s("Модель зрелости искусственного интеллекта", 20)) == 20


def test_none_is_still_a_dash():
    assert _s(None) == "-"


# --- the other half of the report -----------------------------------------
#
# Section 10, the included studies, is built with Platypus rather than fpdf2:
# it needs wrapping table cells. It does not inherit the family fpdf2 embedded,
# and its default Times is latin-1 — so the section that prints every included
# title verbatim, at full length, was the one section that could not set them.
# A Cyrillic title came out as a row of .notdef boxes: not question marks, which
# at least read as "something is missing", but solid black squares that read as
# a corrupted file.

CYRILLIC = "Уровни зрелости искусственного интеллекта в промышленности"
GREEK = "Διαστάσεις ωριμότητας μηχανικής μάθησης"


def section10(title: str, review_title: str = "A review") -> bytes:
    """Build the included-studies section around one paper."""
    from app.models import Paper
    from app.routers.report import _build_section10_pdf

    paper = Paper(id=1, project_id=1, citekey="dimitrova2024levels", title=title,
                  authors="Dimitrova, Ana", venue="Empirical Software Engineering",
                  year=2024, source="ieee", doi="10.1000/emse.2024.001")
    return _build_section10_pdf(
        included_pap=[paper], avg_qa={}, project=None, all_fns=[], fl={},
        rec_map={}, section_num=10, slr_title=review_title,
    )


def text_of(pdf_bytes: bytes) -> str:
    import io
    from pypdf import PdfReader
    return "\n".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(pdf_bytes)).pages)


def unspaced(text: str) -> str:
    """Text with every space and line break dropped.

    A title longer than the column wraps, and the wrap lands wherever the
    measured width says — comparing against the whole string would fail for a
    reason that has nothing to do with the script it is set in.
    """
    return "".join(text.split())


def test_the_platypus_section_has_the_family_too():
    """Registered under its own names, not the core Times ones."""
    assert _register_reportlab_fonts() is True
    from reportlab.pdfbase import pdfmetrics
    registered = pdfmetrics.getRegisteredFontNames()
    for name in _RL_STYLES.values():
        assert name in registered, name


def test_registering_twice_is_harmless():
    """ReportLab's registry is process-wide and the report is built per request."""
    assert _register_reportlab_fonts() is True
    assert _register_reportlab_fonts() is True


@pytest.mark.parametrize("label,text", [("Cyrillic", CYRILLIC), ("Greek", GREEK)])
def test_an_included_title_is_set_in_its_own_script(label, text):
    """The check that found this: not that the PDF builds, but that the title
    is in it. `.notdef` renders as a box and extracts as one, so a PDF full of
    boxes passes any assertion that only looks for the absence of an exception.
    """
    extracted = unspaced(text_of(section10(text)))
    assert unspaced(text) in extracted, f"{label} title did not reach the PDF"


@pytest.mark.parametrize("label,text", [("Cyrillic", CYRILLIC), ("Greek", GREEK)])
def test_no_title_becomes_a_row_of_boxes(label, text):
    assert "\u25a0" not in text_of(section10(text))


def test_the_running_header_sets_the_review_title_too():
    """The header repeats the review's own title on every page of the section,
    and a multivocal review may well be titled in the script it studies."""
    extracted = unspaced(text_of(section10("A Latin title", review_title=CYRILLIC[:40])))
    assert unspaced(CYRILLIC[:40]) in extracted
