"""Tables of the judging module.

Prefixed `aiqm_` and kept apart from the review tables: the judging module
reads ReviQ's tables and never writes them directly — what it decides reaches
ReviQ through the decision import and the conflict endpoint, the same doors a
human co-reviewer uses. Everything ReviQ's model has no place for lives here.

Only the LLM cache exists so far (WP1). Judge decisions, the quasi-gold
standard, candidate statements and the model hierarchy follow with the work
packages that fill them (PLAN.md, section 4).
"""

from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel


class AiqmLlmCall(SQLModel, table=True):
    """One model call, stored before anything is derived from it.

    `key` is the hash over everything that determines the answer (provider,
    model id, parameters, prompt name, version and text hash, input). A second
    call with the same key is answered from here, which is what lets a run be
    replayed without an API key — and what the replication package ships.

    `raw_response` is the provider's body as received, not a parsed form: a
    parser can be fixed later, a discarded response cannot.
    """

    __tablename__ = "aiqm_llm_call"

    id: Optional[int] = Field(default=None, primary_key=True)
    key: str = Field(index=True, unique=True)
    provider: str
    model: str
    params_json: str
    prompt_name: str
    prompt_version: str
    prompt_sha256: str
    input_json: str
    raw_response: str
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    cost_usd: Optional[float] = None
    batch: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)
