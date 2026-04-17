"""Tests for BibTeX parsing and deduplication (SX5 requirement)."""
import pytest
from app.services.bibtex_service import (
    parse_bib_content, normalize_title, detect_duplicates, entry_to_paper_dict, get_venue,
)

SAMPLE_BIB = """
@article{smith2020,
  author = {Smith, John},
  title = {A Survey of JVMTI Usage in Production Systems},
  year = {2020},
  journal = {Journal of Software Engineering},
  doi = {10.1000/jse.2020.001},
  abstract = {This paper surveys the usage of JVMTI in production systems.}
}

@inproceedings{jones2019,
  author = {Jones, Alice and Brown, Bob},
  title = {Profiling Java Applications with JVMTI},
  year = {2019},
  booktitle = {Proceedings of ICSE 2019},
  doi = {10.1145/icse.2019.001}
}

@inproceedings{duplicate2020,
  author = {Smith, John},
  title = {A Survey of JVMTI Usage in Production Systems},
  year = {2020},
  booktitle = {ICSE 2020},
  doi = {10.1000/jse.2020.001}
}
"""

SAMPLE_BIB_NO_DOI = """
@article{nodoi2021,
  author = {White, Carol},
  title = {Dynamic Analysis with Java Agents},
  year = {2021},
  journal = {Software and Systems Modeling}
}

@article{nodoi_dup2021,
  author = {White, Carol},
  title = {Dynamic Analysis with Java Agents},
  year = {2021},
  journal = {Software and Systems Modeling}
}
"""


class TestParsing:
    def test_parse_basic(self):
        entries = parse_bib_content(SAMPLE_BIB)
        assert len(entries) == 3

    def test_parse_citekeys(self):
        entries = parse_bib_content(SAMPLE_BIB)
        keys = [e['ID'] for e in entries]
        assert 'smith2020' in keys
        assert 'jones2019' in keys

    def test_parse_fields(self):
        entries = parse_bib_content(SAMPLE_BIB)
        smith = next(e for e in entries if e['ID'] == 'smith2020')
        assert smith['title'] == 'A Survey of JVMTI Usage in Production Systems'
        assert smith['year'] == '2020'
        assert smith['doi'] == '10.1000/jse.2020.001'

    def test_parse_empty(self):
        entries = parse_bib_content("")
        assert entries == []

    def test_parse_invalid_graceful(self):
        # Should not raise, just return what it can parse
        entries = parse_bib_content("this is not bibtex at all")
        assert isinstance(entries, list)


class TestNormalizeTitle:
    def test_lowercases(self):
        assert normalize_title("Hello World") == "hello world"

    def test_removes_special_chars(self):
        assert normalize_title("A Survey: {Special} Chars!") == "a survey special chars"

    def test_collapses_whitespace(self):
        assert normalize_title("  A   B   C  ") == "a b c"

    def test_empty(self):
        assert normalize_title("") == ""

    def test_none_like(self):
        assert normalize_title(None) == ""  # type: ignore


class TestDeduplication:
    def test_doi_dedup(self):
        entries = parse_bib_content(SAMPLE_BIB)
        unique, dupes, _, _ = detect_duplicates(entries, set(), set())
        # smith2020 and duplicate2020 share the same DOI
        assert len(unique) == 2
        assert len(dupes) == 1

    def test_title_venue_dedup_no_doi(self):
        entries = parse_bib_content(SAMPLE_BIB_NO_DOI)
        unique, dupes, _, _ = detect_duplicates(entries, set(), set())
        assert len(unique) == 1
        assert len(dupes) == 1

    def test_existing_dois_respected(self):
        entries = parse_bib_content(SAMPLE_BIB)
        existing_dois = {'10.1000/jse.2020.001'}
        unique, dupes, _, _ = detect_duplicates(entries, existing_dois, set())
        # smith2020 already in DB → duplicate; duplicate2020 same doi → duplicate too
        assert len(dupes) >= 1
        unique_dois = {e.get('doi', '').lower() for e in unique}
        assert '10.1000/jse.2020.001' not in unique_dois

    def test_cross_session_dedup(self):
        """Second import of same papers should all be flagged as duplicates."""
        entries = parse_bib_content(SAMPLE_BIB)
        unique1, _, dois, tvs = detect_duplicates(entries, set(), set())
        unique2, dupes2, _, _ = detect_duplicates(entries, dois, tvs)
        assert len(unique2) == 0
        assert len(dupes2) == len(entries)


class TestGetVenue:
    def test_article(self):
        entry = {'ENTRYTYPE': 'article', 'journal': 'Nature'}
        assert get_venue(entry) == 'Nature'

    def test_inproceedings(self):
        entry = {'ENTRYTYPE': 'inproceedings', 'booktitle': 'ICSE 2020'}
        assert get_venue(entry) == 'ICSE 2020'

    def test_unknown_type(self):
        entry = {'ENTRYTYPE': 'misc'}
        assert get_venue(entry) == ''


class TestEntryToPaperDict:
    def test_basic_conversion(self):
        entries = parse_bib_content(SAMPLE_BIB)
        smith = next(e for e in entries if e['ID'] == 'smith2020')
        paper = entry_to_paper_dict(smith, source='scopus')
        assert paper['citekey'] == 'smith2020'
        assert paper['source'] == 'scopus'
        assert paper['dedup_status'] == 'original'
        assert paper['year'] == 2020
        assert paper['doi'] == '10.1000/jse.2020.001'

    def test_missing_year(self):
        entry = {'ID': 'test', 'ENTRYTYPE': 'article', 'title': 'Test'}
        paper = entry_to_paper_dict(entry, source='ieee')
        assert paper['year'] is None
