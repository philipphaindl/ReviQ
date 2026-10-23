"""`init-study`: the ReviQ projects a study runs in.

Three projects, not one (PLAN.md, E1). The main project holds the search
results and every vote, judges included. The calibration and validation
projects hold only their samples and only the two human reviewers: a human
coding the gold standard in the main project would see the judges' rationales
in ReviQ's conflict view, and a gold standard coded with the answers in sight
is not one.

Idempotent by title, label and role, so running it twice changes nothing and
running it after a criterion was added to `criteria.toml` adds that one
criterion. It never edits or deletes what is already there: a criterion that
was screened against is evidence, and rewording it in place would change what
recorded decisions mean.
"""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from sqlmodel import Session, select

from app.database import MLR_METHODOLOGY
from app.models import ExclusionCriterion, InclusionCriterion, Project, QACriterion, Reviewer

from .config import Study

CRITERIA_PATH = Path(__file__).with_name("criteria.toml")


@dataclass
class SetupReport:
    created_projects: list[str] = field(default_factory=list)
    added: list[str] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return bool(self.created_projects or self.added)


def load_criteria(path: Path = CRITERIA_PATH) -> dict:
    return tomllib.loads(path.read_text(encoding="utf-8"))


def judge_reviewers(study: Study) -> list[dict]:
    return [{"name": f"{j.key} ({j.family})", "role": j.role} for j in study.judges]


def _project(session: Session, title: str, report: SetupReport, lead: str) -> Project:
    project = session.exec(select(Project).where(Project.title == title)).first()
    if project is None:
        project = Project(title=title, lead_researcher=lead, review_type="mlr",
                          methodology=MLR_METHODOLOGY,
                          description="Created by python -m app.judging init-study.")
        session.add(project)
        session.commit()
        session.refresh(project)
        report.created_projects.append(title)
    return project


def _criteria(session: Session, project: Project, criteria: dict, report: SetupReport) -> None:
    for model, key in ((InclusionCriterion, "inclusion"), (ExclusionCriterion, "exclusion")):
        existing = {c.label for c in session.exec(
            select(model).where(model.project_id == project.id))}
        for entry in criteria[key]:
            if entry["label"] not in existing:
                session.add(model(project_id=project.id, label=entry["label"],
                                  description=entry["description"], phase=entry["phase"],
                                  short_label=entry["short_label"]))
                report.added.append(f"{project.title}: {entry['label']}")
    existing_qa = {c.label for c in session.exec(
        select(QACriterion).where(QACriterion.project_id == project.id))}
    for entry in criteria["qa"]:
        if entry["label"] not in existing_qa:
            session.add(QACriterion(project_id=project.id, label=entry["label"],
                                    description=entry["description"], max_score=1.0))
            report.added.append(f"{project.title}: {entry['label']}")


def _reviewers(session: Session, project: Project, wanted: list[dict],
               report: SetupReport) -> None:
    roles = {r.role for r in session.exec(
        select(Reviewer).where(Reviewer.project_id == project.id))}
    for entry in wanted:
        if entry["role"] not in roles:
            session.add(Reviewer(project_id=project.id, name=entry["name"], role=entry["role"]))
            report.added.append(f"{project.title}: {entry['role']} {entry['name']}")


def init_study(session: Session, study: Study, criteria: dict | None = None) -> SetupReport:
    criteria = criteria if criteria is not None else load_criteria()
    report = SetupReport()
    humans = [r for r in criteria["reviewer"] if r["role"] in ("R1", "R2")]
    lead = humans[0]["name"] if humans else "R1"

    main = _project(session, study.main_project, report, lead)
    _criteria(session, main, criteria, report)
    _reviewers(session, main, criteria["reviewer"] + judge_reviewers(study), report)

    for title in (study.calibration_project, study.validation_project):
        project = _project(session, title, report, lead)
        _criteria(session, project, criteria, report)
        _reviewers(session, project, humans, report)

    session.commit()
    return report
