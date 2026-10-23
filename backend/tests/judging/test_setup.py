"""init-study: three ReviQ projects, idempotent, never rewriting criteria."""

import pytest
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

import app.models  # noqa: F401
from app.judging import config, setup
from app.models import ExclusionCriterion, InclusionCriterion, Project, QACriterion, Reviewer


@pytest.fixture
def session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def _roles(session, project):
    return {r.role for r in session.exec(select(Reviewer).where(Reviewer.project_id == project.id))}


def test_three_multivocal_projects_with_criteria_and_short_labels(session):
    study = config.load()
    setup.init_study(session, study)
    projects = {p.title: p for p in session.exec(select(Project))}
    assert set(projects) == {study.main_project, study.calibration_project,
                             study.validation_project}
    assert all(p.review_type == "mlr" for p in projects.values())
    main = projects[study.main_project]
    inclusion = session.exec(select(InclusionCriterion).where(
        InclusionCriterion.project_id == main.id)).all()
    exclusion = session.exec(select(ExclusionCriterion).where(
        ExclusionCriterion.project_id == main.id)).all()
    assert [c.label for c in inclusion] == ["IC1", "IC2", "IC3"]
    assert [c.label for c in exclusion] == ["EC1", "EC2", "EC3", "EC4", "EC5", "EC6"]
    assert all(c.short_label for c in [*inclusion, *exclusion])
    assert len(session.exec(select(QACriterion).where(
        QACriterion.project_id == main.id)).all()) == 12


def test_judges_vote_only_in_the_main_project(session):
    """The gold standard is coded where no judge rationale can be seen (E1)."""
    study = config.load()
    setup.init_study(session, study)
    projects = {p.title: p for p in session.exec(select(Project))}
    judge_roles = {j.role for j in study.judges}
    assert judge_roles | {"R1", "R2", "R7", "R8"} <= _roles(session, projects[study.main_project])
    for title in (study.calibration_project, study.validation_project):
        assert _roles(session, projects[title]) == {"R1", "R2"}


def test_a_second_run_changes_nothing(session):
    study = config.load()
    assert setup.init_study(session, study).changed
    report = setup.init_study(session, study)
    assert not report.changed
    assert len(session.exec(select(Project)).all()) == 3


def test_an_existing_criterion_is_never_reworded(session):
    study = config.load()
    setup.init_study(session, study)
    criterion = session.exec(select(InclusionCriterion).where(
        InclusionCriterion.label == "IC1")).first()
    criterion.description = "Wording a reviewer screened against."
    session.add(criterion)
    session.commit()
    setup.init_study(session, study)
    assert session.get(InclusionCriterion, criterion.id).description == \
        "Wording a reviewer screened against."


def test_a_criterion_added_to_the_file_is_added_to_every_project(session):
    study = config.load()
    setup.init_study(session, study)
    criteria = setup.load_criteria()
    criteria["exclusion"].append({"label": "EC7", "short_label": "x", "phase": "screening",
                                  "description": "Added after the first run."})
    report = setup.init_study(session, study, criteria)
    assert sorted(report.added) == sorted(
        f"{t}: EC7" for t in (study.main_project, study.calibration_project,
                              study.validation_project))
