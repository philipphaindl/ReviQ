"""The interface every judge backend implements.

Kept to one method so that a provider is a thin translation between a cache
`Request` and that provider's HTTP API, nothing more. Retries, caching, cost
accounting and parsing live outside, once, rather than once per vendor.

Only the interface exists in WP1. The backends follow in WP4, after the model
ids are chosen: each one is written against the provider's official API
documentation at that time and tested against recorded responses. By rule
(A.3.10) no backend may go through a coding assistant's CLI or a chat login;
every call is a plain API call with a key from the environment.
"""

from __future__ import annotations

from typing import Protocol

from .cache import Request, Response


class Provider(Protocol):
    name: str

    def call(self, request: Request) -> Response:
        """Send one request and return the raw body with token counts."""
        ...


class Unavailable:
    """Placeholder for a family whose backend is not written yet. Calling it is
    an error rather than a silent no-op, so a run cannot appear to have asked a
    judge it never reached; answers already in the cache stay replayable."""

    def __init__(self, name: str) -> None:
        self.name = name

    def call(self, request: Request) -> Response:
        raise NotImplementedError(f"no backend for {self.name} yet (WP4)")
