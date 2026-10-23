"""The LLM cache: every call stored, every repeat answered from storage (A.3.1).

The key covers exactly what determines an answer. Leaving something out (the
prompt text behind a version number, a parameter) would let two different
requests share one stored answer; putting something in that does not matter
(a timestamp, the API key) would make every request unique and the cache
useless. The API key in particular never enters the key, the stored request
or the stored response.

`offline=True` turns a miss into an error instead of a call. That is how a
replication run proves it used nothing but the shipped cache.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Callable

from sqlmodel import Session, select

from app.retrieval.redact import scrub

from .models import AiqmLlmCall


class CacheMiss(LookupError):
    """Offline, and the request has never been made."""


@dataclass(frozen=True)
class Request:
    provider: str
    model: str
    params: dict[str, Any]
    prompt_name: str
    prompt_version: str
    prompt_sha256: str
    input: dict[str, Any]

    @property
    def key(self) -> str:
        canonical = json.dumps(
            {
                "provider": self.provider, "model": self.model, "params": self.params,
                "prompt": [self.prompt_name, self.prompt_version, self.prompt_sha256],
                "input": self.input,
            },
            sort_keys=True, ensure_ascii=False, separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Response:
    raw: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: float | None = None
    batch: bool = False
    from_cache: bool = False


def lookup(session: Session, request: Request) -> Response | None:
    row = session.exec(select(AiqmLlmCall).where(AiqmLlmCall.key == request.key)).first()
    if row is None:
        return None
    return Response(raw=row.raw_response, input_tokens=row.input_tokens,
                    output_tokens=row.output_tokens, cost_usd=row.cost_usd,
                    batch=row.batch, from_cache=True)


def store(session: Session, request: Request, response: Response) -> None:
    session.add(AiqmLlmCall(
        key=request.key, provider=request.provider, model=request.model,
        params_json=json.dumps(request.params, sort_keys=True),
        prompt_name=request.prompt_name, prompt_version=request.prompt_version,
        prompt_sha256=request.prompt_sha256,
        input_json=json.dumps(request.input, sort_keys=True, ensure_ascii=False),
        # A provider may echo request details into an error body; scrub before
        # it is stored, exactly as creel does for its error strings.
        raw_response=scrub(response.raw) or "",
        input_tokens=response.input_tokens, output_tokens=response.output_tokens,
        cost_usd=response.cost_usd, batch=response.batch,
    ))
    session.commit()


def cached_call(session: Session, request: Request, call: Callable[[Request], Response],
                *, offline: bool = False) -> Response:
    """Answer from the cache, or call once and store the answer."""

    hit = lookup(session, request)
    if hit is not None:
        return hit
    if offline:
        raise CacheMiss(f"{request.provider}/{request.model} {request.prompt_name} "
                        f"v{request.prompt_version}: not in cache ({request.key[:12]})")
    response = call(request)
    store(session, request, response)
    return response
