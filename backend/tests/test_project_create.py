"""Creating a project answers with the project it created.

The second commit in create_project (the one that adds R1) expired the
instance, so the 201 response carried an empty object. A script creating a
project and then adding criteria to it had to look the id up again by title,
which breaks as soon as two projects share a title.
"""
from __future__ import annotations


def test_the_created_project_comes_back_with_its_id(instance):
    r = instance.client.post("/api/projects", json={
        "title": "Created", "lead_researcher": "Alice", "review_type": "mlr"})
    assert r.status_code == 201
    body = r.json()
    assert body["title"] == "Created"
    assert body["review_type"] == "mlr"
    assert instance.client.get(f"/api/projects/{body['id']}").json()["title"] == "Created"


def test_the_lead_researcher_still_becomes_r1(instance):
    pid = instance.client.post("/api/projects", json={
        "title": "With R1", "lead_researcher": "Alice"}).json()["id"]
    reviewers = instance.client.get(f"/api/projects/{pid}/reviewers").json()
    assert [(r["role"], r["name"]) for r in reviewers] == [("R1", "Alice")]
