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

from app.routers.report import _FONT, _FONT_DIR, _FONT_FILES, _Report, _s


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
