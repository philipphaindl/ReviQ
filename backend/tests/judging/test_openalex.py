"""OpenAlex client: parsing against a fixture, requests against a mock transport."""

import json
from pathlib import Path

import httpx
import pytest

from app.judging.search.openalex import (OpenAlex, OpenAlexError, abstract_from_index,
                                         normalise_doi, parse_work)

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "openalex_work.json").read_text())


def test_a_work_is_parsed_with_its_abstract_rebuilt_in_order():
    work = parse_work(FIXTURE)
    assert work.openalex_id == "W1000000001"
    assert work.doi == "10.1000/example.1"
    assert work.abstract.startswith("We propose an AI maturity model")
    assert work.keywords == "AI maturity; Readiness"
    assert work.referenced_works == ("W1000000002", "W1000000003")
    assert work.is_oa and work.year == 2024


def test_an_empty_inverted_index_is_no_abstract():
    assert abstract_from_index(None) is None and abstract_from_index({}) is None


@pytest.mark.parametrize("raw", ["https://doi.org/10.1/X", "doi:10.1/x", " 10.1/X "])
def test_dois_are_normalised(raw):
    assert normalise_doi(raw) == "10.1/x"


def _client(handler):
    return OpenAlex(httpx.Client(transport=httpx.MockTransport(handler)),
                    mailto="study@example.org", delay=0)


def test_requests_carry_the_contact_address_and_count_reads_meta():
    seen = []

    def handler(request):
        seen.append(request)
        if request.url.path == "/works/doi:10.1000/example.1":
            return httpx.Response(200, json=FIXTURE)
        return httpx.Response(200, json={"meta": {"count": 4321}, "results": []})

    client = _client(handler)
    assert client.work_by_doi("10.1000/EXAMPLE.1").openalex_id == "W1000000001"
    assert client.count("title_and_abstract.search:x") == 4321
    assert all(r.url.params["mailto"] == "study@example.org" for r in seen)


def test_not_found_is_an_error_not_an_empty_work():
    client = _client(lambda request: httpx.Response(404))
    with pytest.raises(OpenAlexError, match="not found"):
        client.work_by_doi("10.1/none")
