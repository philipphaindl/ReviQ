"""
BibTeX processing service.
Ports and extends logic from the original modules/bibtex_processing.py and modules/selection.py.
"""
import re
from typing import Any
import bibtexparser
from bibtexparser.bparser import BibTexParser
from bibtexparser.customization import convert_to_unicode


def parse_bib_content(content: str) -> list[dict[str, Any]]:
    """Parse BibTeX string content and return list of entry dicts."""
    parser = BibTexParser()
    parser.customization = convert_to_unicode
    parser.ignore_nonstandard_types = False
    bib_db = bibtexparser.loads(content, parser=parser)
    return bib_db.entries


def normalize_title(title: str) -> str:
    """Normalize a title for deduplication comparison."""
    if not title:
        return ""
    cleaned = re.sub(r"[^a-z0-9\s]", "", title.lower())
    return re.sub(r"\s+", " ", cleaned).strip()


def get_venue(entry: dict) -> str:
    entry_type = entry.get("ENTRYTYPE", "").lower()
    return {
        "inproceedings": entry.get("booktitle", ""),
        "book": entry.get("publisher", ""),
        "article": entry.get("journal", ""),
        "conference": entry.get("booktitle", ""),
    }.get(entry_type, "")


def detect_duplicates(
    new_entries: list[dict],
    existing_dois: set[str],
    existing_title_venues: set[str],
    known_duplicates: list[str] | None = None,
) -> tuple[list[dict], list[dict], set[str], set[str]]:
    """
    Separate new_entries into unique and duplicate sets.

    Uses DOI (primary) and normalized title+venue (fallback) matching,
    porting the logic from modules/selection.py::remove_duplicates.

    Returns: (unique_entries, duplicate_entries, updated_dois, updated_title_venues)
    """
    known_dupes = {d.lower() for d in (known_duplicates or [])}
    unique = []
    duplicates = []

    for entry in new_entries:
        doi = entry.get("doi", "").strip().lower()
        title = entry.get("title", "")
        title_norm = normalize_title(title)
        venue_norm = normalize_title(get_venue(entry))
        title_venue_key = f"{title_norm}__{venue_norm}"

        # Check known manual duplicates first
        if title_norm and title_norm in known_dupes:
            duplicates.append(entry)
            continue

        if doi:
            if doi in existing_dois:
                duplicates.append(entry)
                continue
            # New DOI: check title+venue as secondary guard
            if title_venue_key and title_venue_key in existing_title_venues:
                duplicates.append(entry)
                continue
            existing_dois.add(doi)
            if title_venue_key:
                existing_title_venues.add(title_venue_key)
            unique.append(entry)
        else:
            # No DOI: rely on title+venue only
            if title_venue_key and title_venue_key in existing_title_venues:
                duplicates.append(entry)
                continue
            if title_venue_key:
                existing_title_venues.add(title_venue_key)
            unique.append(entry)

    return unique, duplicates, existing_dois, existing_title_venues


def detect_language(abstract: str) -> str | None:
    """Detect the language of an abstract using langid."""
    if not abstract or len(abstract.strip()) < 20:
        return None
    try:
        import langid
        lang, _ = langid.classify(abstract)
        return lang
    except Exception:
        return None


def entry_to_paper_dict(entry: dict, source: str) -> dict:
    """Convert a bibtexparser entry dict to a Paper field dict."""
    return {
        "citekey": entry.get("ID", ""),
        "doi": entry.get("doi", None),
        "title": entry.get("title", "").strip(),
        "authors": entry.get("author", None),
        "year": _parse_year(entry.get("year")),
        "venue": get_venue(entry) or None,
        "abstract": entry.get("abstract", None),
        "keywords": entry.get("keywords", None),
        "entry_type": entry.get("ENTRYTYPE", None),
        "source": source,
        "dedup_status": "original",
        "language": detect_language(entry.get("abstract", "")),
    }


def _parse_year(year_str) -> int | None:
    if not year_str:
        return None
    try:
        return int(str(year_str).strip()[:4])
    except (ValueError, TypeError):
        return None
