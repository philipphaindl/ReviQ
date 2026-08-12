"""Text extraction for HTML and PDF.

HTML goes through trafilatura: it is the only main-content extractor with a
published, peer-reviewed benchmark (Barbaresi, ACL 2021 System Demonstrations),
which matters because the extraction step has to be defensible in a methods
section. It removes boilerplate and returns metadata in the same call.

PDF goes through pdfminer.six (MIT). PyMuPDF would be 10-50x faster but is
AGPL-3.0, which would force this tool to AGPL or a commercial licence — see
docs/decisions.md.
"""

from __future__ import annotations

from dataclasses import dataclass
from html.parser import HTMLParser
from io import BytesIO

PDF_MAGIC = b"%PDF-"
HTML_HINTS = (b"<!doctype html", b"<html", b"<head", b"<body")

# Soft blocks: a WAF or bot-challenge page served with HTTP 200. These are the
# most dangerous retrieval failure for a review, because every layer reports
# success — status 200, content present, text extracted, hash computed — and a
# firewall notice ends up in the corpus posing as a source.
#
# Matching is deliberately paired with a length ceiling below: a long article
# that happens to discuss "access denied" is not a block page, and silently
# discarding a real source would be the worse error.
BLOCK_SIGNATURES: tuple[tuple[str, str], ...] = (
    ("the requested url was rejected", "F5 BIG-IP ASM"),
    ("please consult with your administrator", "F5 BIG-IP ASM"),
    ("attention required!", "Cloudflare"),
    ("checking your browser before accessing", "Cloudflare"),
    ("just a moment...", "Cloudflare challenge"),
    ("enable javascript and cookies to continue", "Cloudflare challenge"),
    ("pardon our interruption", "Imperva/Distil"),
    ("incapsula incident id", "Imperva Incapsula"),
    ("request unsuccessful", "Imperva Incapsula"),
    ("access denied", "generic WAF"),
    ("you don't have permission to access", "generic WAF"),
    ("verify you are human", "bot challenge"),
    ("are you a robot", "bot challenge"),
    ("unusual traffic from your computer", "rate-limit challenge"),
    ("403 forbidden", "HTTP 403 body"),
    ("captcha", "captcha challenge"),
)

# Block pages are short. A genuine report, article or whitepaper is not.
MAX_BLOCK_PAGE_WORDS = 200


@dataclass
class Extraction:
    extractor: str
    title: str | None = None
    author: str | None = None
    publication_date: str | None = None
    language: str | None = None
    text: str | None = None
    error: str | None = None

    @property
    def word_count(self) -> int:
        return len(self.text.split()) if self.text else 0


def detect_media_type(content: bytes) -> str:
    """Sniff the payload rather than trusting Content-Type.

    Content-Type lies constantly in grey literature: PDFs are served as
    text/html or application/octet-stream by CMSes and download gateways. Five
    bytes of sniffing prevents a silent mis-extraction that would look like an
    empty document rather than an error.
    """
    if content.startswith(PDF_MAGIC):
        return "pdf"
    head = content[:2048].lstrip().lower()
    if any(hint in head for hint in HTML_HINTS):
        return "html"
    return "other"


class _LanguageFinder(HTMLParser):
    """Reads the language a document declares about itself, from the head."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.lang: str | None = None
        self.og_locale: str | None = None
        self.http_equiv: str | None = None
        self.done = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self.done:
            return
        values = {k.lower(): (v or "") for k, v in attrs}
        if tag == "html":
            self.lang = values.get("lang") or values.get("xml:lang")
        elif tag == "meta":
            name = (values.get("property") or values.get("name") or "").lower()
            equiv = (values.get("http-equiv") or "").lower()
            if name == "og:locale":
                self.og_locale = values.get("content")
            elif equiv == "content-language":
                self.http_equiv = values.get("content")
        elif tag == "body":
            # Everything that declares a language sits in the head; stopping
            # here keeps this linear in the head rather than in the document.
            self.done = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "head":
            self.done = True


def _normalise_tag(value: str | None) -> str | None:
    """A declared value to a lowercase BCP-47-ish tag, or None if it is noise.

    `de_AT` and `de-AT` both become `de-at`; a consumer filtering on language
    takes the part before the first hyphen. Values that are not plausible
    language tags — empty strings, template placeholders left in the markup,
    `x-default` from an hreflang copy-paste — are rejected rather than stored,
    because a junk value in this field is worse than an absent one: it would
    silently pass a "documents in English only" inclusion filter.
    """
    if not value:
        return None
    tag = value.strip().replace("_", "-").lower().split(",")[0].strip()
    if not tag:
        return None
    primary = tag.split("-")[0]
    if not (2 <= len(primary) <= 3) or not primary.isalpha() or primary == "x":
        return None
    return tag


def declared_language(content: bytes) -> str | None:
    """The language the document states it is written in, or None.

    Deliberately the *declared* language and not a detected one. trafilatura
    only fills its `language` field when a language-detection package is
    installed, which this project does not depend on, so in practice the field
    arrived empty for every document — 358 of 358 in the pilot corpus — while
    language is a standard inclusion criterion in a multivocal review (Garousi
    et al. 2019). A declaration is weaker evidence than detection, but it is
    evidence with a source: it is in the archived bytes, it is reproducible
    offline, and a methods section can state exactly what it means.

    Precedence follows how specific the declaration is about the document
    itself: the `lang` attribute on `<html>` first, then a `content-language`
    header equivalent, then `og:locale`, which describes the page as shared on
    a social platform and is the most likely to be a site-wide default.
    """
    finder = _LanguageFinder()
    try:
        finder.feed(content.decode("utf-8", errors="replace"))
    except Exception:  # malformed markup must never abort an extraction
        pass
    for candidate in (finder.lang, finder.http_equiv, finder.og_locale):
        tag = _normalise_tag(candidate)
        if tag:
            return tag
    return None


def extract_html(content: bytes, url: str | None = None) -> Extraction:
    import trafilatura

    version = getattr(trafilatura, "__version__", "unknown")
    extractor = f"trafilatura-{version}"
    try:
        document = trafilatura.bare_extraction(
            content,
            url=url,
            favor_precision=True,     # a review needs clean text more than complete text
            include_comments=False,   # comments are not the source document
            include_tables=True,
            with_metadata=True,
        )
    except Exception as exc:  # extraction must never abort a run
        return Extraction(extractor=extractor, error=f"{type(exc).__name__}: {exc}")

    if not document:
        return Extraction(extractor=extractor, error="no main content extracted")

    # trafilatura returns a Document object in 2.x and a dict in some 1.x paths.
    get = document.get if isinstance(document, dict) else lambda k: getattr(document, k, None)
    return Extraction(
        extractor=extractor,
        title=get("title"),
        author=get("author"),
        publication_date=get("date"),
        # `declared_language`, not trafilatura's `language`: that field is
        # populated only when a language-detection package is installed, which
        # this project does not depend on. Mixing the two would put a detected
        # value and a declared one in the same column with no way to tell them
        # apart, and the column feeds an inclusion criterion.
        language=declared_language(content),
        text=get("text"),
    )


def extract_pdf(content: bytes, ocr: bool = False) -> Extraction:
    from pdfminer.high_level import extract_text

    try:
        from pdfminer import __version__ as pdfminer_version
    except ImportError:
        pdfminer_version = "unknown"
    extractor = f"pdfminer.six-{pdfminer_version}"

    try:
        text = extract_text(BytesIO(content))
    except Exception as exc:
        return Extraction(extractor=extractor, error=f"{type(exc).__name__}: {exc}")

    if not text or not text.strip():
        # Almost always a scanned PDF. Government reports and older whitepapers
        # -- core grey literature -- are frequently scans.
        if ocr:
            return extract_pdf_ocr(content)
        return Extraction(
            extractor=extractor,
            error="no text layer (scanned PDF?); retry the run with --ocr",
        )
    return Extraction(extractor=extractor, text=text.strip())


def extract_pdf_ocr(content: bytes, dpi: int = 200, max_pages: int = 40) -> Extraction:
    """Rasterise and OCR a PDF that has no text layer.

    Opt-in, and isolated behind its own import, because it needs the extra
    `ocr` dependencies plus a tesseract binary on the system. A missing
    install must degrade to a recorded extraction error, never break a run.

    pypdfium2 does the rasterising rather than PyMuPDF: same reason as D2, it
    is BSD/Apache rather than AGPL.
    """
    try:
        import pypdfium2
        import pytesseract
    except ImportError as exc:
        return Extraction(
            extractor="ocr-unavailable",
            error=(f"OCR requested but not installed ({exc.name}); "
                   f"uv sync --extra ocr, and install tesseract "
                   f"(macOS: brew install tesseract)"),
        )

    try:
        version = pytesseract.get_tesseract_version()
    except Exception as exc:
        return Extraction(
            extractor="ocr-unavailable",
            error=f"tesseract binary not found ({exc}); macOS: brew install tesseract",
        )

    extractor = f"pypdfium2+tesseract-{version}"
    try:
        pdf = pypdfium2.PdfDocument(content)
        pages = min(len(pdf), max_pages)
        chunks = []
        for index in range(pages):
            image = pdf[index].render(scale=dpi / 72).to_pil()
            chunks.append(pytesseract.image_to_string(image))
        text = "\n".join(chunks).strip()
    except Exception as exc:
        return Extraction(extractor=extractor, error=f"{type(exc).__name__}: {exc}")

    if not text:
        return Extraction(extractor=extractor, error="OCR produced no text")
    note = f" (first {max_pages} pages)" if len(pdf) > max_pages else ""
    return Extraction(extractor=f"{extractor}{note}", text=text)


def detect_block_page(content: bytes, extracted_text: str | None) -> str | None:
    """Name the blocking system if this looks like a WAF or challenge page.

    Returns a short reason, or None if the payload looks like a real document.
    Checks the extracted text and the raw bytes: a challenge page may carry its
    marker in a <title> or a script that boilerplate removal strips away.

    A signature alone is not enough — it must also be short. That ordering is
    the point: missing a block page costs one flagged row on the next run,
    while discarding a genuine source costs a source, silently.
    """
    word_count = len(extracted_text.split()) if extracted_text else 0
    if word_count > MAX_BLOCK_PAGE_WORDS:
        return None

    haystack = (extracted_text or "").lower()
    # Only the head of the raw payload: enough for <title> and early markup,
    # cheap on a multi-megabyte page.
    haystack += "\n" + content[:8192].decode("utf-8", "replace").lower()

    for signature, system in BLOCK_SIGNATURES:
        if signature in haystack:
            return f"{system}: {signature!r}"
    return None


def extract(
    content: bytes, media_type: str, url: str | None = None, ocr: bool = False
) -> Extraction:
    if media_type == "html":
        return extract_html(content, url)
    if media_type == "pdf":
        return extract_pdf(content, ocr=ocr)
    return Extraction(extractor="none", error=f"unsupported media type: {media_type}")
