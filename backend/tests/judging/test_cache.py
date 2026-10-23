"""The LLM cache: one call per distinct request, replay without a key (A.3.1)."""

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.judging import models  # noqa: F401
from app.judging.cache import CacheMiss, Request, Response, cached_call


@pytest.fixture
def session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def _request(**changes):
    values = dict(provider="anthropic", model="m-1", params={"effort": "low"},
                  prompt_name="screening", prompt_version="0.1", prompt_sha256="a" * 64,
                  input={"title": "AI maturity", "abstract": "..."})
    values.update(changes)
    return Request(**values)


class Counter:
    def __init__(self):
        self.calls = 0

    def __call__(self, request):
        self.calls += 1
        return Response(raw='{"decision": "I"}', input_tokens=10, output_tokens=3)


def test_a_repeated_request_is_answered_from_the_cache(session):
    counter = Counter()
    first = cached_call(session, _request(), counter)
    second = cached_call(session, _request(), counter)
    assert counter.calls == 1
    assert not first.from_cache and second.from_cache
    assert second.raw == first.raw and second.input_tokens == 10


@pytest.mark.parametrize("change", [
    {"model": "m-2"},
    {"params": {"effort": "high"}},
    {"prompt_version": "0.2"},
    {"prompt_sha256": "b" * 64},
    {"input": {"title": "AI maturity", "abstract": "changed"}},
])
def test_anything_that_changes_the_answer_changes_the_key(session, change):
    assert _request().key != _request(**change).key


def test_the_key_does_not_depend_on_dictionary_order():
    a = _request(params={"effort": "low", "max_tokens": 100})
    b = _request(params={"max_tokens": 100, "effort": "low"})
    assert a.key == b.key


def test_offline_replay_fails_loudly_on_a_miss_instead_of_calling(session):
    counter = Counter()
    with pytest.raises(CacheMiss):
        cached_call(session, _request(), counter, offline=True)
    assert counter.calls == 0
    cached_call(session, _request(), counter)
    assert cached_call(session, _request(), counter, offline=True).from_cache


def test_a_key_echoed_in_a_response_is_scrubbed_before_storage(session, monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-secret-123456")

    def leaky(request):
        return Response(raw="error: invalid key sk-test-secret-123456")

    cached_call(session, _request(provider="openai"), leaky)
    stored = session.exec(models.AiqmLlmCall.__table__.select()).first()
    assert "sk-test-secret-123456" not in stored.raw_response
    assert "[REDACTED]" in stored.raw_response
