"""
Decision state machine tests (services.decision_service.sync_decision_state).

These pin the FinalDecision/ConflictLog lifecycle that both the interactive
decision endpoint and the co-reviewer import share:

  - a solo vote creates a provisional FinalDecision that tracks the vote
  - a disagreement opens a ConflictLog and REMOVES the provisional final
    (one reviewer's solo call must never count as the project's decision)
  - later agreement auto-resolves the conflict and (re)creates the final
    with the agreed value — even when a stale final existed
  - an adjudicated disagreement (resolved via discussion/arbitration)
    survives re-submitting the same votes, but reopens when a vote changes
"""
import pytest


PAPERS = [
    {"citekey": f"p{i}", "title": f"Paper {i}", "year": 2021,
     "doi": f"10.1000/statemachine.{i}", "venue": "ICSE"}
    for i in range(3)
]


@pytest.fixture
def project(instance):
    proj = instance.create_project(title="StateMachine", lead="Alice")
    pid = proj["id"]
    r1 = instance.reviewers(pid)[0]
    r2 = instance.add_reviewer(pid, name="Bob", role="R2")
    instance.import_bib(pid, PAPERS, db_name="acm")
    paper = instance.paper_by_citekey(pid, "p0")
    return SimpleNamespace(instance=instance, pid=pid, r1=r1, r2=r2, paper=paper)


class SimpleNamespace:
    def __init__(self, **kw): self.__dict__.update(kw)


def _final(project):
    body = project.instance.client.get(
        f"/api/projects/{project.pid}/papers/{project.paper['id']}/decisions",
        params={"phase": "screening"},
    ).json()
    return body["final_decision"]


def _decide(project, reviewer, decision, rationale=None):
    project.instance.client.post(
        f"/api/projects/{project.pid}/papers/{project.paper['id']}/decisions",
        json={"reviewer_id": reviewer["id"], "phase": "screening",
              "decision": decision, "rationale": rationale},
    ).raise_for_status()


def _resolve_all(project, resolution="I", method="discussion"):
    for c in project.instance.conflicts(project.pid, resolved=False):
        project.instance.client.post(
            f"/api/projects/{project.pid}/conflicts/{c['id']}/resolve",
            json={"resolution": resolution, "resolution_method": method,
                  "resolved_by_reviewer_id": project.r1["id"]},
        ).raise_for_status()


class TestSoloReviewer:
    def test_first_vote_creates_provisional_final(self, project):
        _decide(project, project.r1, "I")
        final = _final(project)
        assert final is not None
        assert final["decision"] == "I"

    def test_changed_solo_vote_updates_provisional_final(self, project):
        _decide(project, project.r1, "I")
        _decide(project, project.r1, "E")
        assert _final(project)["decision"] == "E"


class TestDisagreement:
    def test_conflict_removes_provisional_final(self, project):
        _decide(project, project.r1, "I")
        _decide(project, project.r2, "E")

        conflicts = project.instance.conflicts(project.pid, resolved=False)
        assert len(conflicts) == 1
        # R1's solo call must not survive as the project's decision.
        assert _final(project) is None

    def test_conflicted_paper_counts_as_undecided(self, project):
        _decide(project, project.r1, "I")
        _decide(project, project.r2, "E")

        stats = project.instance.export_stats(project.pid)
        assert stats["screening_included"] == 0
        assert stats["screening_excluded"] == 0
        assert stats["open_conflicts"] == 1

    def test_open_conflict_tracks_changed_votes(self, project):
        _decide(project, project.r1, "I")
        _decide(project, project.r2, "E", rationale="out of scope")
        _decide(project, project.r2, "U", rationale="need full text")

        conflicts = project.instance.conflicts(project.pid, resolved=False)
        assert len(conflicts) == 1
        recorded = {conflicts[0]["r1_decision"], conflicts[0]["r2_decision"]}
        assert recorded == {"I", "U"}
        assert conflicts[0]["r2_rationale"] == "need full text"


class TestAgreementAfterConflict:
    def test_agreement_resolves_conflict_and_restores_final(self, project):
        _decide(project, project.r1, "I")
        _decide(project, project.r2, "E")
        assert _final(project) is None

        _decide(project, project.r2, "I")  # R2 changes their mind

        assert project.instance.conflicts(project.pid, resolved=False) == []
        resolved = project.instance.conflicts(project.pid, resolved=True)
        assert len(resolved) == 1
        assert resolved[0]["resolution"] == "I"
        assert _final(project)["decision"] == "I"

    def test_agreement_updates_stale_final_value(self, project):
        """R1=I (provisional final I) → R2=E (conflict, final removed) →
        R1 switches to E → both agree on E and the final must say E, not I."""
        _decide(project, project.r1, "I")
        _decide(project, project.r2, "E")
        _decide(project, project.r1, "E")

        final = _final(project)
        assert final is not None
        assert final["decision"] == "E"
        assert project.instance.conflicts(project.pid, resolved=False) == []


class TestAdjudicatedDisagreement:
    def test_resolution_survives_resubmitting_same_votes(self, project):
        _decide(project, project.r1, "I")
        _decide(project, project.r2, "E")
        _resolve_all(project, resolution="I", method="discussion")
        assert _final(project)["decision"] == "I"

        # Re-submitting the identical (still disagreeing) votes must NOT
        # reopen the conflict or discard the adjudicated final.
        _decide(project, project.r2, "E")

        assert project.instance.conflicts(project.pid, resolved=False) == []
        final = _final(project)
        assert final["decision"] == "I"
        assert final["resolution_method"] == "discussion"

    def test_changed_vote_after_resolution_reopens_conflict(self, project):
        _decide(project, project.r1, "I")
        _decide(project, project.r2, "E")
        _resolve_all(project, resolution="I", method="discussion")

        _decide(project, project.r2, "U")  # new disagreement, not the adjudicated one

        assert len(project.instance.conflicts(project.pid, resolved=False)) == 1
        assert _final(project) is None

    def test_agreement_after_resolution_keeps_final_provenance(self, project):
        """When reviewers converge on the adjudicated value, the resolved
        final (and its discussion provenance) stays untouched."""
        _decide(project, project.r1, "I")
        _decide(project, project.r2, "E")
        _resolve_all(project, resolution="I", method="discussion")

        _decide(project, project.r2, "I")  # R2 now matches the resolution

        final = _final(project)
        assert final["decision"] == "I"
        assert final["resolution_method"] == "discussion"


class TestImportPathParity:
    """The co-reviewer import must run the same state machine as the
    interactive endpoint — a conflict discovered during import removes the
    provisional final exactly like a live disagreement does."""

    def test_import_conflict_removes_provisional_final(self, two_instances):
        two_instances.use(two_instances.a)
        proj_a = two_instances.a.create_project(title="A", lead="Alice")
        pid_a = proj_a["id"]
        two_instances.a.import_bib(pid_a, PAPERS, db_name="acm")
        r1_a = two_instances.a.reviewers(pid_a)[0]
        p_a = two_instances.a.paper_by_citekey(pid_a, "p0")
        two_instances.a.decide(pid_a, p_a["id"], reviewer_id=r1_a["id"],
                               phase="screening", decision="I")
        payload = two_instances.a.export_decisions(pid_a, r1_a["id"])

        two_instances.use(two_instances.b)
        proj_b = two_instances.b.create_project(title="B", lead="Bob")
        pid_b = proj_b["id"]
        two_instances.b.import_bib(pid_b, PAPERS, db_name="acm")
        r2_b = two_instances.b.reviewers(pid_b)[0]
        p_b = two_instances.b.paper_by_citekey(pid_b, "p0")
        two_instances.b.decide(pid_b, p_b["id"], reviewer_id=r2_b["id"],
                               phase="screening", decision="E")

        result = two_instances.b.import_decisions(pid_b, payload)
        assert result["new_conflicts_detected"] == 1

        body = two_instances.b.client.get(
            f"/api/projects/{pid_b}/papers/{p_b['id']}/decisions",
            params={"phase": "screening"},
        ).json()
        assert body["final_decision"] is None

    def test_import_agreement_creates_final(self, two_instances):
        two_instances.use(two_instances.a)
        proj_a = two_instances.a.create_project(title="A", lead="Alice")
        pid_a = proj_a["id"]
        two_instances.a.import_bib(pid_a, PAPERS, db_name="acm")
        r1_a = two_instances.a.reviewers(pid_a)[0]
        p_a = two_instances.a.paper_by_citekey(pid_a, "p0")
        two_instances.a.decide(pid_a, p_a["id"], reviewer_id=r1_a["id"],
                               phase="screening", decision="I")
        payload = two_instances.a.export_decisions(pid_a, r1_a["id"])

        two_instances.use(two_instances.b)
        proj_b = two_instances.b.create_project(title="B", lead="Bob")
        pid_b = proj_b["id"]
        two_instances.b.import_bib(pid_b, PAPERS, db_name="acm")
        r2_b = two_instances.b.reviewers(pid_b)[0]
        p_b = two_instances.b.paper_by_citekey(pid_b, "p0")
        two_instances.b.decide(pid_b, p_b["id"], reviewer_id=r2_b["id"],
                               phase="screening", decision="I")

        two_instances.b.import_decisions(pid_b, payload)

        body = two_instances.b.client.get(
            f"/api/projects/{pid_b}/papers/{p_b['id']}/decisions",
            params={"phase": "screening"},
        ).json()
        assert body["final_decision"] is not None
        assert body["final_decision"]["decision"] == "I"
