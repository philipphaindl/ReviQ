"""Tables of the judging module.

Prefixed `aiqm_` and kept apart from the review tables: the judging module
reads ReviQ's tables and never writes them directly — what it decides reaches
ReviQ through the decision import and the conflict endpoint, the same doors a
human co-reviewer uses. Everything ReviQ's model has no place for lives here.

So far: the LLM cache (WP1), the quasi-gold standard and the evaluated search
candidates (WP2). Judge decisions, candidate statements and the model hierarchy
follow with the work packages that fill them (PLAN.md, section 4).
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


class AiqmQgs(SQLModel, table=True):
    """One work of the quasi-gold standard (protocol.md, section 5.3).

    A candidate first: `accepted` stays empty until both authors have checked
    it, because a QGS that contains off-topic work measures the search against
    the wrong target. Only accepted works are split, and `split` is assigned
    once — the holdout has to stay untouched until G1, and re-drawing it after
    a look at the results would quietly turn it into a second dev set.
    """

    __tablename__ = "aiqm_qgs"

    id: Optional[int] = Field(default=None, primary_key=True)
    study: str = Field(index=True)
    key: str = Field(index=True)          # OpenAlex id, else DOI, else arXiv id
    openalex_id: Optional[str] = None
    doi: Optional[str] = None
    arxiv_id: Optional[str] = None
    title: Optional[str] = None
    abstract: Optional[str] = None
    keywords: Optional[str] = None
    year: Optional[int] = None
    work_type: Optional[str] = None
    role: str                             # seed | review | related | reference
    origin: Optional[str] = None          # the seed or review a reference came from
    accepted: Optional[bool] = None
    split: Optional[str] = None           # dev | holdout
    created_at: datetime = Field(default_factory=datetime.utcnow)


class AiqmSearchCandidate(SQLModel, table=True):
    """One evaluated candidate string (C.4). Kept, not just printed, because the
    selection at G1 has to be reproducible from what was measured."""

    __tablename__ = "aiqm_search_candidate"

    id: Optional[int] = Field(default=None, primary_key=True)
    study: str = Field(index=True)
    name: str
    base: str                              # S1 or S2
    variant: str                           # how it differs from the base
    label: str                             # canonical form, readable
    terms: int
    dev_matched: int
    dev_total: int
    hits_openalex: Optional[int] = None
    precision: Optional[float] = None
    precision_n: Optional[int] = None
    evaluated_at: datetime = Field(default_factory=datetime.utcnow)
