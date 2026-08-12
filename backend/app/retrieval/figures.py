"""Figure selection.

In a review of maturity models the substance is often *in the diagram* — a
five-level pyramid, a dimension matrix, a radar chart — and none of it reaches
the extracted text. Describing those figures makes them searchable and
quotable.

But a page carries far more images than figures: logos, icons, avatars,
sharing buttons, tracking pixels, stock photography. Describing all of them
wastes credits and fills the corpus with "a blue logo". So this module
*selects*, on the same principle as the snowballing filter in links.py:

  1. **Drop known furniture** — paths containing logo/icon/avatar/sprite/badge,
     and the tracking-pixel dimensions.
  2. **Drop anything declared small.** A figure carrying a maturity model is not
     120px wide. Declared dimensions are a hint, not a guarantee, so this only
     applies when the markup states them.
  3. **Prefer images that carry text about themselves** — alt text or a
     `<figcaption>`. An author who captioned an image thought it mattered.
  4. **Cap per document**, captioned ones first.

The asymmetry runs the same way as everywhere else in this tool: a missed
figure costs one diagram; a described logo costs one cheap API call and a row
that says NO SUBSTANTIVE CONTENT.
"""

from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
from urllib.parse import urljoin, urlsplit

from .urls import is_fetchable

# Path fragments that mark site furniture rather than content.
FURNITURE_MARKERS: tuple[str, ...] = (
    "logo", "/icon", "icon-", "-icon", "favicon", "avatar", "sprite", "badge",
    "button", "banner", "/ads/", "advert", "pixel", "spacer", "placeholder",
    "thumb", "profile", "headshot", "social", "share", "emoji", "flag-",
    "arrow", "chevron", "bullet", "divider", "watermark",
)

# Formats that are never a figure worth describing.
SKIP_EXTENSIONS: tuple[str, ...] = (".svg", ".ico", ".gif")

# Below this, in either declared dimension, it is furniture.
MIN_DECLARED_PIXELS = 200

# A figure a vision model can read is not a few hundred bytes.
MIN_BYTE_SIZE = 8_000


@dataclass(frozen=True)
class Figure:
    raw_src: str
    resolved_url: str
    alt_text: str | None
    caption: str | None

    @property
    def has_caption(self) -> bool:
        return bool(self.alt_text or self.caption)


class _ImageCollector(HTMLParser):
    """Collects <img> tags with their alt text and any enclosing <figcaption>.

    Tracks figure nesting so a caption can be attached to the image it
    describes — the caption is often the single most informative thing about a
    diagram, and it is free.
    """

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.images: list[dict] = []
        self._figure_depth = 0
        self._pending_in_figure: list[dict] = []
        self._in_caption = False
        self._caption: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {key.lower(): (value or "") for key, value in attrs}
        if tag == "figure":
            self._figure_depth += 1
        elif tag == "figcaption" and self._figure_depth:
            self._in_caption = True
            self._caption = []
        elif tag == "img":
            src = attributes.get("src") or attributes.get("data-src")
            if not src:
                return
            record = {
                "src": src,
                "alt": attributes.get("alt") or None,
                "width": attributes.get("width"),
                "height": attributes.get("height"),
                "caption": None,
            }
            self.images.append(record)
            if self._figure_depth:
                self._pending_in_figure.append(record)

    def handle_data(self, data: str) -> None:
        if self._in_caption:
            self._caption.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "figcaption" and self._in_caption:
            caption = " ".join("".join(self._caption).split())
            for record in self._pending_in_figure:
                record["caption"] = caption or None
            self._in_caption = False
        elif tag == "figure" and self._figure_depth:
            self._figure_depth -= 1
            if not self._figure_depth:
                self._pending_in_figure = []


def _declared_too_small(record: dict) -> bool:
    for key in ("width", "height"):
        raw = (record.get(key) or "").strip().rstrip("px")
        if not raw.isdigit():
            continue
        if int(raw) < MIN_DECLARED_PIXELS:
            return True
    return False


def _is_furniture(url: str) -> bool:
    lowered = url.lower()
    path = urlsplit(lowered).path
    if path.endswith(SKIP_EXTENSIONS):
        return True
    return any(marker in lowered for marker in FURNITURE_MARKERS)


def select_figures(html: bytes | str, base_url: str, *, max_figures: int = 5) -> list[Figure]:
    """Apply the four rules and return at most `max_figures`, captioned first."""
    if isinstance(html, bytes):
        html = html.decode("utf-8", "replace")

    parser = _ImageCollector()
    try:
        parser.feed(html)
        parser.close()
    except Exception:
        # Malformed markup must never abort a run.
        pass

    captioned: list[Figure] = []
    plain: list[Figure] = []
    seen: set[str] = set()

    for record in parser.images:
        src = record["src"].strip()
        # data: URIs carry the bytes inline. Skipped for now: archiving them
        # needs a different path than a fetch, and they are rarely figures.
        if not src or src.startswith("data:"):
            continue
        resolved = urljoin(base_url, src)
        if not is_fetchable(resolved) or resolved in seen:
            continue
        if _is_furniture(resolved) or _declared_too_small(record):
            continue
        seen.add(resolved)

        figure = Figure(
            raw_src=record["src"],
            resolved_url=resolved,
            alt_text=record["alt"],
            caption=record["caption"],
        )
        (captioned if figure.has_caption else plain).append(figure)

    return (captioned + plain)[:max_figures]


def looks_describable(content: bytes, content_type: str | None) -> bool:
    """Reject payloads a vision model cannot usefully read.

    Checked after fetching, because declared size and Content-Type both lie.
    """
    if len(content) < MIN_BYTE_SIZE:
        return False
    if content.startswith(b"<svg") or content.lstrip()[:5].lower() == b"<?xml":
        return False
    if content_type and "image" not in content_type.lower():
        # Only trusted negatively: a real image served as octet-stream still
        # starts with its own magic bytes, checked below.
        pass
    return media_type_of(content) is not None


def media_type_of(content: bytes) -> str | None:
    """The IANA media type, sniffed from magic bytes.

    The Claude API needs an accurate media_type; the Content-Type header is not
    reliable enough to pass through unchecked.
    """
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if content.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if content.startswith(b"RIFF") and content[8:12] == b"WEBP":
        return "image/webp"
    if content.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    return None
