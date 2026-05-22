"""
Cross-instance reviewer decision exchange — integration tests.

ReviQ's collaboration model is asynchronous: each reviewer runs their own
instance, makes decisions, exports a JSON file via
``GET /export/decisions``, and shares it with co-reviewers who import it
via ``POST /import/reviewer-decisions``. Every downstream calculation
(Cohen's κ + 95% CI, PABAK, observed agreement Pₒ, PRISMA flow counts,
conflict log) must produce identical numbers regardless of which instance
computes them, or the manuscript's claim of reproducible review numbers
breaks.

These tests build two parallel instances using ``two_instances`` from
``conftest.py``, run the export → import dance real co-reviewers go
through, and assert every derived statistic matches a reference value
computed on the "monolithic" version where both reviewers' decisions
live in the same DB from the start.

Note: the user-facing collaboration artifact is JSON (not CSV) — see
``app/routers/export.py:export_decisions``. CSV exports in the codebase
are limited to chart-data downloads on the frontend.
"""
import pytest

from app.services.kappa_service import calculate_kappa


# ──────────────────────────────────────────────────────────────────────────────
# Shared fixture: same six papers, two parallel instances, R1 in A, R2 in B
# ──────────────────────────────────────────────────────────────────────────────

PAPERS = [
    {"citekey": f"p{i}", "title": f"Paper {i}", "year": 2020 + (i % 3),
     "doi": f"10.1000/exchange.{i}", "venue": "ICSE"}
    for i in range(6)
]

# Hand-crafted decisions chosen so the resulting κ is in the "moderate"
# range — neither perfect agreement nor random — so any drift in the
# calculation is detectable.
R1_DECISIONS = ["I", "I", "I", "E", "E", "E"]
R2_DECISIONS = ["I", "I", "E", "E", "I", "E"]  # disagree on p2 (I/E) and p4 (E/I)


def _seed_papers_and_r1(instance, *, lead="Alice"):
    proj = instance.create_project(title=f"SLR-{instance.label}", lead=lead)
    pid = proj["id"]
    instance.import_bib(pid, PAPERS, db_name="acm")
    r1 = instance.reviewers(pid)[0]
    return pid, r1


def _decide_all(instance, pid, reviewer_id, decisions, phase="screening"):
    for pap_idx, dec in enumerate(decisions):
        paper = instance.paper_by_citekey(pid, f"p{pap_idx}")
        instance.decide(pid, paper["id"], reviewer_id=reviewer_id,
                        phase=phase, decision=dec)


# ──────────────────────────────────────────────────────────────────────────────
# Reference computations (monolithic — both reviewers in one instance)
# ──────────────────────────────────────────────────────────────────────────────

def _reference_kappa():
    """κ that a monolithic project would compute, used as the gold standard."""
    r1 = {f"p{i}": d for i, d in enumerate(R1_DECISIONS)}
    r2 = {f"p{i}": d for i, d in enumerate(R2_DECISIONS)}
    return calculate_kappa(r1, r2)


# ──────────────────────────────────────────────────────────────────────────────
# Tests
# ──────────────────────────────────────────────────────────────────────────────

class TestSingleRoundtripExchange:
    """A → export R1 decisions → import into B → κ on B matches reference."""

    def test_kappa_observed_agreement_matches_reference(self, two_instances):
        ref = _reference_kappa()

        # Instance A: R1 decides, exports.
        two_instances.use(two_instances.a)
        pid_a, r1_a = _seed_papers_and_r1(two_instances.a, lead="Alice")
        _decide_all(two_instances.a, pid_a, r1_a["id"], R1_DECISIONS)
        r1_payload = two_instances.a.export_decisions(pid_a, r1_a["id"])

        # Instance B: papers + R2 already, then import R1's file.
        two_instances.use(two_instances.b)
        pid_b, _ = _seed_papers_and_r1(two_instances.b, lead="Bob")
        r2_b = two_instances.b.reviewers(pid_b)[0]  # auto-created from lead
        _decide_all(two_instances.b, pid_b, r2_b["id"], R2_DECISIONS)
        result = two_instances.b.import_decisions(pid_b, r1_payload)
        # The import endpoint returns a summary of what it absorbed.
        assert result["reviewer_name"] == "Alice"
        assert result["imported_decisions"] == 6
        assert result["new_conflicts_detected"] == 2
        assert set(result["conflict_papers"]) == {"p2", "p4"}

        # κ on B (R1 vs R2) must equal the monolithic κ to four decimals.
        reviewers_b = sorted(two_instances.b.reviewers(pid_b), key=lambda r: r["role"])
        kappa_b = two_instances.b.kappa(pid_b,
            r1_id=reviewers_b[0]["id"], r2_id=reviewers_b[1]["id"])
        assert kappa_b["kappa"] == pytest.approx(ref.kappa, abs=1e-4)
        assert kappa_b["observed_agreement"] == pytest.approx(
            ref.observed_agreement, abs=1e-4)
        assert kappa_b["pabak"] == pytest.approx(ref.pabak, abs=1e-4)
        assert kappa_b["n_papers"] == ref.n_papers

    def test_confidence_interval_matches_reference(self, two_instances):
        ref = _reference_kappa()

        two_instances.use(two_instances.a)
        pid_a, r1_a = _seed_papers_and_r1(two_instances.a)
        _decide_all(two_instances.a, pid_a, r1_a["id"], R1_DECISIONS)
        payload = two_instances.a.export_decisions(pid_a, r1_a["id"])

        two_instances.use(two_instances.b)
        pid_b, _ = _seed_papers_and_r1(two_instances.b, lead="Bob")
        r2_b = two_instances.b.reviewers(pid_b)[0]
        _decide_all(two_instances.b, pid_b, r2_b["id"], R2_DECISIONS)
        two_instances.b.import_decisions(pid_b, payload)

        reviewers_b = sorted(two_instances.b.reviewers(pid_b), key=lambda r: r["role"])
        kappa_b = two_instances.b.kappa(pid_b,
            r1_id=reviewers_b[0]["id"], r2_id=reviewers_b[1]["id"])
        assert kappa_b["kappa_ci_lower"] == pytest.approx(ref.kappa_ci_lower, abs=1e-4)
        assert kappa_b["kappa_ci_upper"] == pytest.approx(ref.kappa_ci_upper, abs=1e-4)

    def test_prisma_counts_consistent_after_import(self, two_instances):
        """The PRISMA totals must remain self-consistent after the second
        reviewer's file is absorbed.

        ReviQ's decision state machine (see ``decisions.py``) gives a paper a
        *provisional* FinalDecision the moment one reviewer touches it. When a
        co-reviewer is later imported and disagrees, a ConflictLog is opened
        but the provisional FinalDecision is left in place until a human
        resolves the conflict. So with this fixture:

          - p0 (I, I) → agreement → final = I
          - p1 (I, I) → agreement → final = I
          - p2 (R1=I, R2=E) → conflict; provisional final = E (R2's earlier solo call)
          - p3 (E, E) → agreement → final = E
          - p4 (R1=E, R2=I) → conflict; provisional final = I
          - p5 (E, E) → agreement → final = E

        Total: 3 included, 3 excluded, 2 open conflicts. The invariant that
        matters for PRISMA reproducibility is that ``included + excluded +
        undecided`` covers every original paper exactly once.
        """
        two_instances.use(two_instances.a)
        pid_a, r1_a = _seed_papers_and_r1(two_instances.a)
        _decide_all(two_instances.a, pid_a, r1_a["id"], R1_DECISIONS)
        payload = two_instances.a.export_decisions(pid_a, r1_a["id"])

        two_instances.use(two_instances.b)
        pid_b, _ = _seed_papers_and_r1(two_instances.b, lead="Bob")
        r2_b = two_instances.b.reviewers(pid_b)[0]
        _decide_all(two_instances.b, pid_b, r2_b["id"], R2_DECISIONS)
        two_instances.b.import_decisions(pid_b, payload)

        stats = two_instances.b.export_stats(pid_b)
        assert stats["screening_included"] == 3
        assert stats["screening_excluded"] == 3
        assert stats["open_conflicts"] == 2
        # PRISMA partition invariant — every original paper accounted for.
        assert (stats["screening_included"]
                + stats["screening_excluded"]
                + stats["screening_undecided"]) == stats["total_unique"]

    def test_conflicts_are_logged_for_disagreements(self, two_instances):
        two_instances.use(two_instances.a)
        pid_a, r1_a = _seed_papers_and_r1(two_instances.a)
        _decide_all(two_instances.a, pid_a, r1_a["id"], R1_DECISIONS)
        payload = two_instances.a.export_decisions(pid_a, r1_a["id"])

        two_instances.use(two_instances.b)
        pid_b, _ = _seed_papers_and_r1(two_instances.b, lead="Bob")
        r2_b = two_instances.b.reviewers(pid_b)[0]
        _decide_all(two_instances.b, pid_b, r2_b["id"], R2_DECISIONS)
        two_instances.b.import_decisions(pid_b, payload)

        conflicts = two_instances.b.conflicts(pid_b)
        citekeys = {c["paper_citekey"] for c in conflicts}
        assert citekeys == {"p2", "p4"}
        for c in conflicts:
            assert c["resolved"] is False


class TestImportIdempotency:
    """Re-importing the same export must not duplicate decisions or κ inputs."""

    def test_double_import_does_not_change_kappa(self, two_instances):
        ref = _reference_kappa()
        two_instances.use(two_instances.a)
        pid_a, r1_a = _seed_papers_and_r1(two_instances.a)
        _decide_all(two_instances.a, pid_a, r1_a["id"], R1_DECISIONS)
        payload = two_instances.a.export_decisions(pid_a, r1_a["id"])

        two_instances.use(two_instances.b)
        pid_b, _ = _seed_papers_and_r1(two_instances.b, lead="Bob")
        r2_b = two_instances.b.reviewers(pid_b)[0]
        _decide_all(two_instances.b, pid_b, r2_b["id"], R2_DECISIONS)
        two_instances.b.import_decisions(pid_b, payload)
        # Idempotency: re-import the same file twice.
        two_instances.b.import_decisions(pid_b, payload)
        two_instances.b.import_decisions(pid_b, payload)

        reviewers_b = sorted(two_instances.b.reviewers(pid_b), key=lambda r: r["role"])
        kappa_b = two_instances.b.kappa(pid_b,
            r1_id=reviewers_b[0]["id"], r2_id=reviewers_b[1]["id"])
        assert kappa_b["kappa"] == pytest.approx(ref.kappa, abs=1e-4)
        assert kappa_b["n_papers"] == ref.n_papers

    def test_double_import_does_not_duplicate_conflicts(self, two_instances):
        two_instances.use(two_instances.a)
        pid_a, r1_a = _seed_papers_and_r1(two_instances.a)
        _decide_all(two_instances.a, pid_a, r1_a["id"], R1_DECISIONS)
        payload = two_instances.a.export_decisions(pid_a, r1_a["id"])

        two_instances.use(two_instances.b)
        pid_b, _ = _seed_papers_and_r1(two_instances.b, lead="Bob")
        r2_b = two_instances.b.reviewers(pid_b)[0]
        _decide_all(two_instances.b, pid_b, r2_b["id"], R2_DECISIONS)
        two_instances.b.import_decisions(pid_b, payload)
        two_instances.b.import_decisions(pid_b, payload)

        # Still exactly 2 conflicts (p2 + p4) — no duplicates.
        assert len(two_instances.b.conflicts(pid_b)) == 2


class TestUpdatedDecisionOnReimport:
    """When R1 changes their mind and re-exports, the imported decisions
    should reflect the new value (upsert semantics) and κ must recompute."""

    def test_changed_decision_propagates_through_kappa(self, two_instances):
        two_instances.use(two_instances.a)
        pid_a, r1_a = _seed_papers_and_r1(two_instances.a)
        _decide_all(two_instances.a, pid_a, r1_a["id"], R1_DECISIONS)
        payload_v1 = two_instances.a.export_decisions(pid_a, r1_a["id"])

        # R1 changes their mind on paper p0: I → E.
        p0 = two_instances.a.paper_by_citekey(pid_a, "p0")
        two_instances.a.decide(pid_a, p0["id"], reviewer_id=r1_a["id"],
                               phase="screening", decision="E")
        payload_v2 = two_instances.a.export_decisions(pid_a, r1_a["id"])
        assert payload_v1 != payload_v2  # the export captured the change

        two_instances.use(two_instances.b)
        pid_b, _ = _seed_papers_and_r1(two_instances.b, lead="Bob")
        r2_b = two_instances.b.reviewers(pid_b)[0]
        _decide_all(two_instances.b, pid_b, r2_b["id"], R2_DECISIONS)
        two_instances.b.import_decisions(pid_b, payload_v1)
        kappa_v1 = two_instances.b.kappa(pid_b)["kappa"]

        two_instances.b.import_decisions(pid_b, payload_v2)
        kappa_v2 = two_instances.b.kappa(pid_b)["kappa"]
        # The κ value MUST shift now that one decision flipped.
        assert kappa_v1 != pytest.approx(kappa_v2, abs=1e-4)

        # And it must match a freshly-computed reference using R1_v2.
        r1_v2 = ["E"] + R1_DECISIONS[1:]
        ref = calculate_kappa(
            {f"p{i}": d for i, d in enumerate(r1_v2)},
            {f"p{i}": d for i, d in enumerate(R2_DECISIONS)},
        )
        assert kappa_v2 == pytest.approx(ref.kappa, abs=1e-4)


class TestExportPayloadShape:
    """Pin the JSON contract that real co-reviewers will exchange."""

    def test_payload_contains_required_top_level_fields(self, instance):
        pid, r1 = _seed_papers_and_r1(instance)
        _decide_all(instance, pid, r1["id"], R1_DECISIONS)
        payload = instance.export_decisions(pid, r1["id"])
        for key in ("project_title", "reviewer_name", "reviewer_role",
                    "phase", "export_timestamp", "decisions"):
            assert key in payload, f"missing key: {key}"

    def test_each_decision_references_paper_by_citekey(self, instance):
        """Citekey is the cross-instance join key — it must always be present."""
        pid, r1 = _seed_papers_and_r1(instance)
        _decide_all(instance, pid, r1["id"], R1_DECISIONS)
        payload = instance.export_decisions(pid, r1["id"])
        assert {d["paper_citekey"] for d in payload["decisions"]} == {
            "p0", "p1", "p2", "p3", "p4", "p5",
        }
        for d in payload["decisions"]:
            assert d["decision"] in ("I", "E", "U")

    def test_export_filters_by_phase(self, instance):
        pid, r1 = _seed_papers_and_r1(instance)
        _decide_all(instance, pid, r1["id"], R1_DECISIONS, phase="screening")
        # Add a full-text decision; export with phase=screening should ignore it.
        p0 = instance.paper_by_citekey(pid, "p0")
        instance.decide(pid, p0["id"], reviewer_id=r1["id"],
                        phase="full-text", decision="I")
        payload = instance.export_decisions(pid, r1["id"], phase="screening")
        assert all(d["phase"] == "screening" for d in payload["decisions"])
        assert len(payload["decisions"]) == 6


class TestImportRobustness:
    def test_decisions_for_unknown_citekeys_are_skipped(self, two_instances):
        """Foreign citekeys in the import file must not raise, must not pollute."""
        two_instances.use(two_instances.b)
        pid_b, _ = _seed_papers_and_r1(two_instances.b, lead="Bob")
        # Hand-crafted payload referencing only one real paper out of three.
        payload = {
            "project_title": "from-elsewhere", "reviewer_name": "Charlie",
            "reviewer_role": "R3", "phase": "screening",
            "export_timestamp": "2026-01-01T00:00:00",
            "decisions": [
                {"paper_citekey": "p0",        "phase": "screening", "decision": "I"},
                {"paper_citekey": "ghost-1",   "phase": "screening", "decision": "I"},
                {"paper_citekey": "ghost-2",   "phase": "screening", "decision": "E"},
            ],
        }
        two_instances.b.import_decisions(pid_b, payload)

        # Charlie was auto-created with one decision on p0.
        charlie = next(r for r in two_instances.b.reviewers(pid_b)
                       if r["name"] == "Charlie")
        p0 = two_instances.b.paper_by_citekey(pid_b, "p0")
        body = two_instances.b.client.get(
            f"/api/projects/{pid_b}/papers/{p0['id']}/decisions",
        ).json()
        charlie_decs = [d for d in body["decisions"] if d["reviewer_id"] == charlie["id"]]
        assert len(charlie_decs) == 1
        assert charlie_decs[0]["decision"] == "I"

    def test_importing_decisions_auto_creates_new_reviewer(self, two_instances):
        two_instances.use(two_instances.b)
        pid_b, _ = _seed_papers_and_r1(two_instances.b, lead="Bob")
        before = {r["name"] for r in two_instances.b.reviewers(pid_b)}

        payload = {
            "project_title": "from-elsewhere", "reviewer_name": "Dana",
            "reviewer_role": "R2", "phase": "screening",
            "export_timestamp": "2026-01-01T00:00:00",
            "decisions": [{"paper_citekey": "p0", "phase": "screening", "decision": "I"}],
        }
        two_instances.b.import_decisions(pid_b, payload)

        after = {r["name"] for r in two_instances.b.reviewers(pid_b)}
        assert "Dana" in (after - before)

    def test_malformed_payload_is_rejected_with_400(self, instance):
        pid, _ = _seed_papers_and_r1(instance)
        r = instance.client.post(
            f"/api/projects/{pid}/import/reviewer-decisions",
            files={"file": ("bad.json", b'{"missing":"required"}',
                            "application/json")},
        )
        assert r.status_code == 400
