"""Figure selection and the source/model-output boundary.

The selection rules matter for cost; the boundary matters for integrity. A
generated description is evidence *about* a figure, never text the source
wrote — the schema enforces that by keeping them in different tables, and
these tests pin the selection that decides what gets described at all.
"""

from glr.figures import Figure, media_type_of, looks_describable, select_figures
from glr.vision import DEFAULT_PROMPT, NO_CONTENT, Description

BASE = "https://example.org/reports/ai-maturity"

PAGE = b"""<!DOCTYPE html><html><body>
  <header><img src="/assets/logo.png" width="180" height="60" alt="Example Institute"></header>
  <img src="/img/icon-search.png" alt="search">
  <img src="/static/avatar-jane.jpg" alt="Jane Doe">
  <img src="/px/tracking.gif" width="1" height="1">
  <figure>
    <img src="/figures/maturity-levels.png" alt="Five levels of AI maturity">
    <figcaption>Figure 2. The five maturity levels and their dimensions.</figcaption>
  </figure>
  <img src="/figures/dimension-matrix.png" alt="Dimension matrix">
  <img src="/figures/undocumented-chart.png">
  <img src="/figures/thumbnail-small.png" width="120" height="90" alt="small">
  <img src="/diagrams/architecture.svg" alt="Vector diagram">
</body></html>"""


def _urls(selected):
    return [f.resolved_url for f in selected]


def test_captioned_figure_is_selected_with_its_caption():
    selected = select_figures(PAGE, BASE)
    match = [f for f in selected if "maturity-levels" in f.resolved_url]
    assert len(match) == 1
    assert match[0].caption == "Figure 2. The five maturity levels and their dimensions."
    assert match[0].alt_text == "Five levels of AI maturity"


def test_captioned_figures_come_first():
    """An author who captioned an image thought it mattered — the cap must not
    displace those in favour of undocumented ones."""
    selected = select_figures(PAGE, BASE, max_figures=1)
    assert len(selected) == 1
    assert selected[0].has_caption


def test_furniture_is_dropped():
    urls = _urls(select_figures(PAGE, BASE))
    for noise in ("logo", "icon-", "avatar", "tracking.gif"):
        assert not any(noise in url for url in urls), noise


def test_declared_small_images_are_dropped():
    urls = _urls(select_figures(PAGE, BASE))
    assert not any("thumbnail-small" in url for url in urls)


def test_vector_graphics_are_dropped():
    """A vision model reads pixels; an SVG would need rasterising first."""
    urls = _urls(select_figures(PAGE, BASE))
    assert not any(url.endswith(".svg") for url in urls)


def test_uncaptioned_content_images_are_still_eligible():
    urls = _urls(select_figures(PAGE, BASE))
    assert any("undocumented-chart" in url for url in urls)


def test_relative_sources_resolve_against_the_base():
    selected = select_figures(b'<img src="../fig/a-chart.png" alt="x">', BASE)
    assert selected[0].resolved_url == "https://example.org/fig/a-chart.png"


def test_data_uris_are_skipped():
    assert select_figures(b'<img src="data:image/png;base64,iVBORw0K" alt="x">', BASE) == []


def test_the_cap_is_honoured():
    html = b"".join(
        f'<img src="/figures/chart{i}.png" alt="Chart {i}">'.encode() for i in range(30)
    )
    assert len(select_figures(html, BASE, max_figures=5)) == 5


def test_malformed_markup_does_not_raise():
    assert isinstance(select_figures(b"<img src=/figures/x.png alt=<<<", BASE), list)


def test_media_type_is_sniffed_not_trusted():
    assert media_type_of(b"\x89PNG\r\n\x1a\n" + b"0" * 100) == "image/png"
    assert media_type_of(b"\xff\xd8\xff\xe0" + b"0" * 100) == "image/jpeg"
    assert media_type_of(b"RIFF0000WEBPVP8 ") == "image/webp"
    assert media_type_of(b"not an image at all") is None


def test_tiny_payloads_are_not_describable():
    """Spacers and 1x1 pixels survive selection when the markup declares no
    dimensions; the byte check is the second line of defence."""
    assert not looks_describable(b"\x89PNG\r\n\x1a\n" + b"0" * 50, "image/png")


def test_a_real_image_is_describable():
    assert looks_describable(b"\x89PNG\r\n\x1a\n" + b"0" * 20_000, "image/png")


def test_non_image_payload_is_not_describable():
    assert not looks_describable(b"<html>" + b"0" * 20_000, "text/html")


# --- the source/model-output boundary -----------------------------------


def test_the_sentinel_marks_a_non_substantive_description():
    """The prompt asks for this exact string so non-figures are filterable in
    SQL rather than by guessing at prose."""
    assert NO_CONTENT in DEFAULT_PROMPT
    result = Description(model="m", prompt="p", description=NO_CONTENT)
    assert not result.is_substantive


def test_a_real_description_is_substantive():
    result = Description(
        model="m", prompt="p",
        description="A pyramid with five levels labelled Initial, Managed, Defined...",
    )
    assert result.is_substantive


def test_a_failed_description_is_not_substantive():
    assert not Description(model="m", prompt="p", error="boom").is_substantive


def test_the_prompt_constrains_the_model_to_the_observable():
    """A review cannot cite interpretation as evidence. The prompt is stored
    verbatim with every description so this constraint is auditable."""
    lowered = DEFAULT_PROMPT.lower()
    assert "do not interpret" in lowered
    assert "only what is visible" in lowered
