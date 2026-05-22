"""
Replication round-trip: every derived calculation must survive an export →
re-import without drift.

A replication ZIP is the SLR's archival artefact — it's what authors hand to
journals so a reviewer can re-derive the manuscript numbers from a fresh
ReviQ instance. If κ, PABAK, PRISMA counts, QA aggregation, or extraction
summaries shift by even a single decimal between the source project and an
imported copy, the reproducibility claim breaks.

The earlier ``test_replication_roundtrip.py`` covers schema-level
deep-equal on the raw rows. This file adds the derived-statistics check:
spin up a project, fully populate it through every phase, compute every
downstream statistic, export → import, and assert every statistic on the
new project matches the source bit-for-bit (within numerical tolerance).
"""
import pytest


PAPERS = [
    {"citekey": f"p{i}", "title": f"Paper {i}", "year": 2020 + (i % 3),
     "doi": f"10.1000/repl.{i}", "venue": "ICSE"}
    for i in range(8)
]
R1_SCREENING = ["I", "I", "I", "I", "I", "E", "E", "E"]
R2_SCREENING = ["I", "I", "E", "E", "I", "I", "E", "E"]   # disagree on p2, p3, p5
R1_FULLTEXT  = ["I", "I", "I", "E", "E"]                  # 5 papers reach FT
R2_FULLTEXT  = ["I", "I", "E", "E", "E"]                  # disagree on p2
QA_SCORES = [
    (1.0, 1.0, 1.0, 1.0),  # 100 % → high
    (1.0, 1.0, 1.0, 0.5),  # 87.5 % → high
    (1.0, 0.5, 0.5, 0.5),  # 62.5 % → medium
    (1.0, 1.0, 0.0, 0.0),  # 50 % → medium
    (0.5, 0.0, 0.0, 0.0),  # 12.5 % → low
]


def _populate(instance):
    proj = instance.create_project(title="Drift", lead="Alice")
    pid = proj["id"]
    r1 = instance.reviewers(pid)[0]
    r2 = instance.add_reviewer(pid, name="Bob", role="R2")

    # Taxonomy + extraction field schema.
    for v in ["Tool", "Framework", "Method"]:
        instance.client.post(f"/api/projects/{pid}/taxonomies/contribution_type",
                              json={"value": v}).raise_for_status()
    for v in ["Validation", "Evaluation"]:
        instance.client.post(f"/api/projects/{pid}/taxonomies/research_type",
                              json={"value": v}).raise_for_status()
    instance.client.post(f"/api/projects/{pid}/extraction/fields", json={
        "field_name": "usage", "field_label": "Usage",
        "field_type": "dropdown", "sort_order": 0,
    }).raise_for_status()

    # Four QA criteria @ max 1.0.
    qa_crits = [instance.add_qa_criterion(pid, label=f"QA{i+1}") for i in range(4)]

    # Papers + screening decisions.
    instance.import_bib(pid, PAPERS, db_name="acm")
    for i, dec in enumerate(R1_SCREENING):
        p = instance.paper_by_citekey(pid, f"p{i}")
        instance.decide(pid, p["id"], reviewer_id=r1["id"],
                        phase="screening", decision=dec)
    for i, dec in enumerate(R2_SCREENING):
        p = instance.paper_by_citekey(pid, f"p{i}")
        instance.decide(pid, p["id"], reviewer_id=r2["id"],
                        phase="screening", decision=dec)
    # Resolve every conflict to "I" via discussion — so the first five papers
    # end up screening-included and progress to the full-text stage.
    for c in instance.conflicts(pid, resolved=False):
        instance.client.post(
            f"/api/projects/{pid}/conflicts/{c['id']}/resolve",
            json={"resolution": "I", "resolution_method": "discussion",
                  "resolved_by_reviewer_id": r1["id"]},
        ).raise_for_status()

    # Full-text decisions on the 5 included.
    for i, (d1, d2) in enumerate(zip(R1_FULLTEXT, R2_FULLTEXT)):
        p = instance.paper_by_citekey(pid, f"p{i}")
        instance.decide(pid, p["id"], reviewer_id=r1["id"],
                        phase="full-text", decision=d1)
        instance.decide(pid, p["id"], reviewer_id=r2["id"],
                        phase="full-text", decision=d2)
    for c in instance.conflicts(pid, resolved=False):
        if c["phase"] != "full-text": continue
        instance.client.post(
            f"/api/projects/{pid}/conflicts/{c['id']}/resolve",
            json={"resolution": "I", "resolution_method": "discussion",
                  "resolved_by_reviewer_id": r1["id"]},
        ).raise_for_status()

    # QA scores on the included papers.
    for i, scores in enumerate(QA_SCORES):
        p = instance.paper_by_citekey(pid, f"p{i}")
        for crit, sc in zip(qa_crits, scores):
            instance.upsert_qa(pid, p["id"], reviewer_id=r1["id"],
                                criterion_id=crit["id"], score=sc)

    # Extraction values.
    extraction = [
        {"contribution_type": "Tool",      "research_type": "Validation", "usage": "Direct"},
        {"contribution_type": "Tool",      "research_type": "Evaluation", "usage": "Direct"},
        {"contribution_type": "Framework", "research_type": "Validation", "usage": "Indirect"},
        {"contribution_type": "Method",    "research_type": "Evaluation", "usage": "Indirect"},
        {"contribution_type": "Tool",      "research_type": "Validation", "usage": "Direct"},
    ]
    for i, vals in enumerate(extraction):
        p = instance.paper_by_citekey(pid, f"p{i}")
        for name, value in vals.items():
            instance.client.post(
                f"/api/projects/{pid}/papers/{p['id']}/extraction",
                json={"reviewer_id": r1["id"], "field_name": name,
                      "field_value": value},
            ).raise_for_status()

    return pid


def _snapshot_calculations(instance, pid):
    """Capture every reviewer-visible derived statistic in one bundle."""
    reviewers = sorted(instance.reviewers(pid), key=lambda r: r["role"])
    r1, r2 = reviewers[0], reviewers[1]
    stats = instance.export_stats(pid)
    kappa_scr = instance.kappa(pid, "screening", r1_id=r1["id"], r2_id=r2["id"])
    kappa_ft  = instance.kappa(pid, "full-text", r1_id=r1["id"], r2_id=r2["id"])
    qa = instance.qa_summary(pid)
    ext = instance.client.get(f"/api/projects/{pid}/extraction/summary").json()
    return {
        "prisma": {
            "total_retrieved":     stats["total_retrieved"],
            "total_unique":        stats["total_unique"],
            "screening_included":  stats["screening_included"],
            "screening_excluded":  stats["screening_excluded"],
            "fulltext_included":   stats["fulltext_included"],
            "fulltext_excluded":   stats["fulltext_excluded"],
            "open_conflicts":      stats["open_conflicts"],
        },
        "kappa_screening": {
            "kappa":              kappa_scr["kappa"],
            "kappa_ci_lower":     kappa_scr["kappa_ci_lower"],
            "kappa_ci_upper":     kappa_scr["kappa_ci_upper"],
            "pabak":              kappa_scr["pabak"],
            "observed_agreement": kappa_scr["observed_agreement"],
            "n_papers":           kappa_scr["n_papers"],
        },
        "kappa_fulltext": {
            "kappa":              kappa_ft["kappa"],
            "pabak":              kappa_ft["pabak"],
            "observed_agreement": kappa_ft["observed_agreement"],
            "n_papers":           kappa_ft["n_papers"],
        },
        "qa": {
            "n_papers":   len(qa["papers"]),
            "by_level":   {lvl: sum(1 for p in qa["papers"] if p["quality_level"] == lvl)
                           for lvl in ("low", "medium", "high")},
            "by_pct":     sorted(round(p["percentage"], 2) for p in qa["papers"]),
        },
        "extraction": {
            "n_papers":   len(ext["papers"]),
            "n_fields":   len(ext["fields"]),
            "usage_dist": _value_counts(ext["papers"], "usage"),
            "contrib_dist": _value_counts(ext["papers"], "contribution_type"),
            "research_dist": _value_counts(ext["papers"], "research_type"),
        },
    }


def _value_counts(papers, field):
    out = {}
    for p in papers:
        v = p["values"].get(field)
        if v: out[v] = out.get(v, 0) + 1
    return out


class TestReplicationDrift:
    def test_full_calculation_snapshot_survives_round_trip(self, two_instances):
        # Source project in instance A.
        two_instances.use(two_instances.a)
        src_pid = _populate(two_instances.a)
        before = _snapshot_calculations(two_instances.a, src_pid)

        # Export → import on instance B.
        zip_bytes = two_instances.a.export_replication(src_pid)
        two_instances.use(two_instances.b)
        meta = two_instances.b.import_replication(zip_bytes)
        new_pid = meta["id"]

        after = _snapshot_calculations(two_instances.b, new_pid)

        assert before["prisma"] == after["prisma"], "PRISMA counts drifted on round-trip"
        for key, ref_val in before["kappa_screening"].items():
            assert after["kappa_screening"][key] == pytest.approx(ref_val, abs=1e-4), \
                f"screening κ {key} drifted"
        for key, ref_val in before["kappa_fulltext"].items():
            assert after["kappa_fulltext"][key] == pytest.approx(ref_val, abs=1e-4), \
                f"full-text κ {key} drifted"
        assert before["qa"] == after["qa"], "QA aggregation drifted"
        assert before["extraction"] == after["extraction"], "Extraction summary drifted"

    def test_double_round_trip_is_idempotent(self, two_instances):
        """Export → import → export → import should still match the original."""
        two_instances.use(two_instances.a)
        src_pid = _populate(two_instances.a)
        original = _snapshot_calculations(two_instances.a, src_pid)

        zip_1 = two_instances.a.export_replication(src_pid)
        two_instances.use(two_instances.b)
        first_pid = two_instances.b.import_replication(zip_1)["id"]

        # Round-trip back into B itself — this is what happens when an SLR
        # is archived twice (e.g., supplementary materials of two papers).
        zip_2 = two_instances.b.export_replication(first_pid)
        second_pid = two_instances.b.import_replication(zip_2)["id"]
        twice = _snapshot_calculations(two_instances.b, second_pid)

        assert twice["prisma"]     == original["prisma"]
        assert twice["qa"]         == original["qa"]
        assert twice["extraction"] == original["extraction"]
        for k, v in original["kappa_screening"].items():
            assert twice["kappa_screening"][k] == pytest.approx(v, abs=1e-4)
