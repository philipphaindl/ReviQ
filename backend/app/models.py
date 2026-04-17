"""
SQLModel table definitions for the ReviQ schema.

The schema mirrors the SLR process phases (Kitchenham & Charters 2007):
  Project -> Reviewers, Criteria (IC/EC/QA), Search Protocol
  -> Papers (imported from BibTeX) -> ReviewerDecisions -> FinalDecisions
  -> ConflictLog -> QAScores -> ExtractionRecords -> SnowballingIterations

Key conventions:
  - `decision` fields use single-letter codes: I (Include), E (Exclude), U (Uncertain)
  - `phase` is either "screening" (title/abstract) or "full-text"
  - `source` on Paper is the database name or "snowballing:<N>" for snowballed papers
  - `dedup_status` is "original" or "duplicate_of:<citekey>"
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
    source: str  # db_name or "snowballing:N"
    dedup_status: str = "original"  # "original" or "duplicate_of:{citekey}"
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
