"""
SQLModel table definitions for the ReviQ schema.

The schema mirrors the SLR process phases (Kitchenham & Charters 2007):
  Project -> Reviewers, Criteria (IC/EC/QA), Search Protocol
  -> Papers (imported from BibTeX) -> ReviewerDecisions -> FinalDecisions
  -> ConflictLog -> QAScores -> ExtractionRecords -> SnowballingIterations

Key conventions:
  - `decision` fields use single-letter codes: I (Include), E (Exclude), U (Uncertain)
  - `phase` is either "screening" (title/abstract) or "full-text"
  - `source` on Paper is the database name, "snowballing:<N>" for snowballed
    papers, or "grey:<engine>" for grey literature
  - `stream` is "formal" or "grey"; `discovery` is "search" or "snowball".
    These are authoritative — `source` is a display label, not a stream test.
  - `dedup_status` is "original" for a record that counts, anything else for a
    duplicate. Test it with `!= "original"` — never a prefix: the importers
    cannot name the record they duplicate, so no back-reference is stored.
"""
from sqlmodel import SQLModel, Field
from typing import Optional
from datetime import datetime


class Project(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    title: str
    description: Optional[str] = None
    lead_researcher: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    methodology: str = "Kitchenham & Charters (2007)"
    # "slr" or "mlr". Declared when the project is created rather than inferred
    # from whether grey literature happens to have been imported: a multivocal
    # review is designed as one in its protocol (Garousi, Felizardo & Mäntylä
    # 2019), and the choice decides what the PRISMA figure has to show and what
    # the report has to say. Inferring it would also mean the third stream
    # appears mid-review, changing a published figure without anyone deciding.
    #
    # Defaults to "slr", and the migration backfills existing rows to it: every
    # project that predates this column was a systematic review, and a tool
    # that silently promoted them would put an empty grey column in their
    # figures.
    review_type: str = "slr"
    qa_high_threshold: float = 75.0
    qa_medium_threshold: float = 50.0


class Reviewer(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="project.id", index=True)
    name: str
    email: Optional[str] = None
    role: str  # R1, R2, R3, R4, R5


class InclusionCriterion(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="project.id", index=True)
    label: str  # I1, I2, ...
    description: str
    phase: str = "screening"  # screening or full-text
    short_label: Optional[str] = None  # short human-readable name for PRISMA diagram


class ExclusionCriterion(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="project.id", index=True)
    label: str  # E1, E2, ...
    description: str
    phase: str = "screening"  # screening or full-text
    short_label: Optional[str] = None  # short human-readable name for PRISMA diagram


class QACriterion(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="project.id", index=True)
    label: str  # QA1, QA2, ...
    description: str
    max_score: float = 1.0  # 0.5 or 1.0


class TaxonomyEntry(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="project.id", index=True)
    taxonomy_type: str  # classification dimension, e.g. "research_type", "contribution_type"
    value: str
    sort_order: int = 0


class DatabaseSearchString(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="project.id", index=True)
    db_name: str
    query_string: Optional[str] = None
    filter_settings: Optional[str] = None
    search_date: Optional[str] = None
    results_count: Optional[int] = None


class Paper(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="project.id", index=True)
    citekey: str
    doi: Optional[str] = None
    title: str
    authors: Optional[str] = None
    year: Optional[int] = None
    venue: Optional[str] = None
    abstract: Optional[str] = None
    keywords: Optional[str] = None
    entry_type: Optional[str] = None
    venue_category_override: Optional[str] = None  # user-set: Journal/Conference/Workshop/…
    source: str  # db_name, "snowballing:N", or "grey:<engine>"
    # `stream` and `discovery` are two columns rather than one four-valued
    # field because they are orthogonal: an MLR must separate formal from grey
    # literature *and* database search from snowballing, and grey literature
    # has its own snowballing. Read them through app.services.streams, never
    # by parsing `source` — that is how the two-stream assumption ossified.
    stream: str = "formal"      # formal | grey
    discovery: str = "search"   # search | snowball
    # "original" for a record that counts, anything else for a duplicate. Test
    # it with `!= "original"`, never a prefix: no importer can name the record
    # it duplicates, so no back-reference is stored. The module docstring was
    # corrected when that was standardised; this line was missed.
    dedup_status: str = "original"
    language: Optional[str] = None
    full_text_url: Optional[str] = None
    full_text_inaccessible: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ReviewerDecision(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="project.id", index=True)
    paper_id: int = Field(foreign_key="paper.id", index=True)
    reviewer_id: int = Field(foreign_key="reviewer.id", index=True)
    phase: str  # screening, full-text
    decision: str  # I (Include), E (Exclude), U (Uncertain — treated as abstention in kappa)
    criterion_label: Optional[str] = None  # e.g. "E3" — which criterion motivated the decision
    rationale: Optional[str] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    source_file: Optional[str] = None  # filename if imported from a co-reviewer's JSON export


class FinalDecision(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="project.id", index=True)
    paper_id: int = Field(foreign_key="paper.id", index=True)
    phase: str
    decision: str  # I, E, U
    resolution_method: Optional[str] = None  # agreement, discussion, arbitration
    resolution_note: Optional[str] = None
    resolved_by_reviewer_id: Optional[int] = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class ConflictLog(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="project.id", index=True)
    paper_id: int = Field(foreign_key="paper.id", index=True)
    phase: str
    r1_reviewer_id: Optional[int] = None
    r2_reviewer_id: Optional[int] = None
    r1_decision: Optional[str] = None
    r2_decision: Optional[str] = None
    r1_rationale: Optional[str] = None
    r2_rationale: Optional[str] = None
    resolved: bool = False
    resolution: Optional[str] = None  # final decision
    resolution_method: Optional[str] = None
    resolved_by_reviewer_id: Optional[int] = None
    resolved_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)


class QAScore(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="project.id", index=True)
    paper_id: int = Field(foreign_key="paper.id", index=True)
    criterion_id: int = Field(foreign_key="qacriterion.id", index=True)
    score: float
    rationale: Optional[str] = None
    scored_by_reviewer_id: int = Field(foreign_key="reviewer.id")
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class ExtractionField(SQLModel, table=True):
    """Project-level field schema definition for data extraction."""
    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="project.id", index=True)
    field_name: str
    field_label: str
    field_type: str  # dropdown, text, boolean, number
    options: Optional[str] = None  # JSON array for dropdown options
    sort_order: int = 0


class ExtractionRecord(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="project.id", index=True)
    paper_id: int = Field(foreign_key="paper.id", index=True)
    field_name: str
    field_value: Optional[str] = None
    extracted_by_reviewer_id: int = Field(foreign_key="reviewer.id")
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class SnowballingIteration(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="project.id", index=True)
    iteration_number: int
    iteration_type: str = "forward"  # forward, backward
    is_saturated: bool = False
    saturation_confirmed: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)


class PaperDatabaseLink(SQLModel, table=True):
    """Tracks which databases found a given paper (many-to-many).
    Used for correct precision/recall calculation across databases."""
    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="project.id", index=True)
    paper_id: int = Field(foreign_key="paper.id", index=True)
    db_name: str  # canonical database name


class GreyImport(SQLModel, table=True):
    """One `python -m app.retrieval export-json` package taken into a project.

    Kept because a grey search is only reproducible if the package it came from
    can be named. `canonicalization` in particular: the retrieval tool pins the
    algorithm that produced every canonical URL in a package and warns a
    consumer never to re-canonicalise with its own copy, so two imports made
    under different versions are not joinable — and this is what lets a later
    reader notice that rather than silently joining them.

    `documents_reported` and `usable_reported` are the package's own counts.
    Storing them next to what was actually imported is the reconciliation check
    a PRISMA diagram needs: if they disagree, the diagram is wrong and someone
    has to know which side moved.
    """
    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="project.id", index=True)
    schema_version: Optional[str] = None
    canonicalization: Optional[str] = None
    tool_name: Optional[str] = None
    tool_version: Optional[str] = None
    exported_at_utc: Optional[str] = None
    scope_kind: Optional[str] = None      # "run" or "batch" on the retrieval side
    scope_id: Optional[str] = None        # the run_id or batch_id retrieved
    filename: Optional[str] = None
    queries: Optional[int] = None
    records_in_package: Optional[int] = None
    documents_reported: Optional[int] = None
    usable_reported: Optional[int] = None
    # What became of the records, in the same four disjoint categories the
    # import response reports. Together with `records_in_package` they have to
    # add up: this row is the stored version of a PRISMA "records identified",
    # and a category missing here makes the number unreconcilable later for the
    # same reason it did in the response.
    imported_count: int = 0
    duplicate_count: int = 0            # duplicates *within* the package
    already_present_count: int = 0      # the project already had the document
    skipped_count: int = 0              # no record_key, unusable
    imported_at: datetime = Field(default_factory=datetime.utcnow)


class GreySource(SQLModel, table=True):
    """The retrieval provenance of one grey paper.

    Beside `Paper` rather than inside it, because it belongs to the retrieval
    and not to the review: a paper is a paper whether it came from Scopus or
    from a ministry's website, and only the grey one has a payload digest and
    an archive offset. For a grey source those are not metadata — a retrieval
    timestamp, a SHA-256 over the bytes read, and where those bytes are
    archived *are* the citation, because the page itself may be edited or gone
    by the time anyone checks.

    `retrieval_reason` carries the retrieval package's vocabulary for why a source yielded
    nothing: `origin_unreachable` (commonly publisher access control),
    `no_article_text` (a platform post that was never a document),
    `not_found` (link rot), and so on. They are different exclusion criteria
    and a review that reports them as one number cannot defend any of them.
    """
    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="project.id", index=True)
    paper_id: int = Field(foreign_key="paper.id", index=True)
    grey_import_id: Optional[int] = Field(default=None, foreign_key="greyimport.id", index=True)
    record_key: str
    canonical_url: str = Field(index=True)   # the identity, and the dedup key
    source_url: Optional[str] = None         # after redirects
    host: Optional[str] = None
    retrieved_at_utc: Optional[str] = None
    sha256: Optional[str] = Field(default=None, index=True)
    media_type: Optional[str] = None         # html | pdf | other
    content_length: Optional[int] = None
    word_count: Optional[int] = None
    archive_filename: Optional[str] = None   # the WARC holding the bytes
    archive_offset: Optional[int] = None     # seek straight to the record
    archive_record_id: Optional[str] = None
    retrieval_status: Optional[str] = None   # ok | blocked | failed | empty | not_fetched
    retrieval_reason: Optional[str] = None   # why, when it is not "ok"
    search_observations: int = 0             # how many queries returned this document
    best_rank: Optional[int] = None          # best position across those queries
    # Join keys into the retrieval tables, filled when this installation made
    # the retrieval itself. Nullable and without a foreign key on purpose: a
    # package from a co-reviewer names documents this database may not hold, and
    # the integer ids it was written with belonged to theirs. `canonical_url`
    # and `sha256` above stay the identity that travels between installations;
    # these two are the shortcut home, and what turns "show me the archived text
    # of this source" into a join.
    document_id: Optional[int] = Field(default=None, index=True)
    snapshot_id: Optional[int] = None


class GreyFullText(SQLModel, table=True):
    """The extracted body text of one grey source.

    Its own table rather than a column on `Paper`, and never in
    `Paper.abstract`. Both halves of that are load-bearing.

    **Not a `Paper` column**, because `list_papers` selects `Paper.*` for every
    paper in a project and the screening view calls it on every filter change.
    A text column would drag the full body of every source through a listing
    that renders a title and a year — the pilot corpus holds one source of
    27,784 words, and 424 of them together are megabytes per request.

    **Not `abstract`**, because `abstract` holds the snippet the search engine
    displayed, which is what a screener actually saw when deciding. Overwriting
    it with body text would change, months later and silently, the evidence a
    recorded screening decision rests on.

    Absent for a source that yielded no bytes at all: a row of empty text would
    be indistinguishable from a page that genuinely held none.

    Present, however, for some sources whose retrieval did *not* succeed — see
    `retrieval_status` below, and D31. That case is real rather than
    theoretical: in the pilot corpus five of them carry text.
    """
    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="project.id", index=True)
    paper_id: int = Field(foreign_key="paper.id", index=True, unique=True)
    text: str
    # The status the retrieval carried when this text was extracted. A copy of
    # `GreySource.retrieval_status`, and deliberately so: the two answer
    # different questions. There it describes the *retrieval*; here it
    # qualifies *this text*, and no reader of a full text may be able to reach
    # it without also reaching the reason to distrust it.
    #
    # Not "ok" is not a reason to drop the text. Under a bot challenge
    # trafilatura extracts whatever the page served, and in the pilot corpus
    # that is genuine post content three times ("We've just launched the AI
    # Maturity Self Assessment tool…") and the challenge page's own boilerplate
    # twice ("Checking your browser before accessing…"). Nothing distinguishes
    # them mechanically — both are `blocked`/`bot_challenge` — so dropping on
    # status loses real sources and keeping silently presents boilerplate as a
    # document. The text is kept and the status travels with it.
    retrieval_status: Optional[str] = None
    # As the extractor counted it, not recomputed here: `GreySource.word_count`
    # carries the same number, and two independently derived counts for one
    # source is how a report and an export end up disagreeing.
    word_count: Optional[int] = None
    # e.g. "trafilatura-2.2.0". Pinned in the package because an extractor
    # upgrade changes extracted text, and a review may already cite this one.
    extractor: Optional[str] = None
    # Set when extraction ran and failed. Distinct from "no row at all", which
    # means the source was never retrieved.
    extraction_error: Optional[str] = None


class GreyFigure(SQLModel, table=True):
    """One image from a grey source, as the page carried it.

    `alt_text` and `caption` are source content: the page's own words about its
    own image. What a model said the image shows lives in
    `GreyFigureDescription`, separately — the retrieval side already draws that
    line (`interchange._figures`), and collapsing the two here would let
    generated text be quoted in a review as if the source had written it.
    """
    id: Optional[int] = Field(default=None, primary_key=True)
    project_id: int = Field(foreign_key="project.id", index=True)
    paper_id: int = Field(foreign_key="paper.id", index=True)
    raw_src: Optional[str] = None        # verbatim from the markup
    resolved_url: Optional[str] = None
    alt_text: Optional[str] = None
    caption: Optional[str] = None
    sha256: Optional[str] = None         # over the image bytes
    content_type: Optional[str] = None
    byte_size: Optional[int] = None
    archive_filename: Optional[str] = None
    archive_offset: Optional[int] = None
    archive_record_id: Optional[str] = None
    fetch_error: Optional[str] = None    # the image itself could not be fetched


class GreyFigureDescription(SQLModel, table=True):
    """What a model said one figure shows.

    `model` and `prompt` are stored verbatim rather than summarised, because
    this is generated text entering a review: a reader has to be able to say
    which model produced it and on what instruction. The retrieval side stores
    them for the same reason, and a description whose provenance was dropped in
    transit could not be defended in a methods section.

    Several rows per figure are legitimate — the same image described by two
    models, or by one model under a revised prompt.
    """
    id: Optional[int] = Field(default=None, primary_key=True)
    grey_figure_id: int = Field(foreign_key="greyfigure.id", index=True)
    description: Optional[str] = None
    model: Optional[str] = None
    prompt: Optional[str] = None
    described_at_utc: Optional[str] = None
    error: Optional[str] = None          # the description attempt failed
