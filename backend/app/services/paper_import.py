"""Writing parsed entries into a project, and saying what became of each one.

Both BibTeX importers — the database search in `routers/import_.py` and the
snowballing iteration in `routers/snowballing.py` — ran their own copy of this
loop, and the copies had drifted. `detected_duplicates` counted a duplicate
only once a row had been written in one of them, and always in the other, so
the same field name in the same UI tile meant two different things depending on
which importer had filled it. That is the `dedup_status` defect of Increment 0
repeating one level up, and the reason this lives in one place now.

The counts are the point, not a by-product. A PRISMA diagram's "records
identified" and "duplicates removed" come from them, and any entry that lands
in none of the buckets makes those numbers unreconcilable for whoever reads the
diagram afterwards. `Outcome.total` therefore has to equal the number of
entries handed in, and a test holds every importer to it.
"""
from __future__ import annotations

from typing import Any, NamedTuple, Optional

from sqlmodel import Session, select

from app.models import Paper


class Outcome(NamedTuple):
    """What became of a set of parsed entries. The four are disjoint."""

    imported: list[str]           # new, written as `original`
    duplicates: list[str]         # duplicate of another entry, written as such
    already_present: list[str]    # the project already had this citekey
    skipped_incomplete: int       # no citekey or no title, unusable

    @property
    def total(self) -> int:
        return (len(self.imported) + len(self.duplicates)
                + len(self.already_present) + self.skipped_incomplete)

    def counts(self, total_in_file: int) -> dict[str, Any]:
        """The response fields every paper importer reports, named alike.

        `total_in_file` is passed rather than taken from `total` so that a
        mismatch between what was read and what was accounted for surfaces in
        the response instead of being defined away.
        """
        return {
            "total_in_file": total_in_file,
            "imported_unique": len(self.imported),
            "imported_duplicates": len(self.duplicates),
            "already_present": len(self.already_present),
            "skipped_incomplete": self.skipped_incomplete,
            "imported_citekeys": self.imported,
            "duplicate_citekeys": self.duplicates,
            "already_present_citekeys": self.already_present,
        }


def apply_entries(
    session: Session,
    project_id: int,
    unique: list[dict],
    duplicates: list[dict],
    *,
    to_paper_dict,
    extra_fields: Optional[dict[str, Any]] = None,
) -> Outcome:
    """Write both sets into the project and report what happened to each entry.

    `to_paper_dict` maps one parsed entry to `Paper` fields — the caller passes
    it already bound to its source label, which is the only thing that differs
    between a database search and a snowballing iteration. `extra_fields` is
    for columns the caller sets on every row it writes.

    Does not commit: the caller owns the transaction, as both importers already
    did.
    """
    imported: list[str] = []
    duplicate_keys: list[str] = []
    already_present: list[str] = []
    skipped = 0

    for entry, is_duplicate in [(e, False) for e in unique] + [(e, True) for e in duplicates]:
        data = to_paper_dict(entry)
        # Both fields are required: a paper with no citekey cannot be addressed
        # in a decision file, and one with no title cannot be screened.
        if not data.get("citekey") or not data.get("title"):
            skipped += 1
            continue
        if is_duplicate:
            # Anything other than "original" counts as a duplicate. No
            # `duplicate_of:<citekey>` back-reference: `detect_duplicates` does
            # not report which record matched, so the citekey would be fiction.
            data["dedup_status"] = "duplicate"

        existing = session.exec(
            select(Paper)
            .where(Paper.project_id == project_id)
            .where(Paper.citekey == data["citekey"])
        ).first()
        if existing:
            # A separate outcome from a duplicate *within this file*: the paper
            # was not newly identified at all, so counting it among removed
            # duplicates would inflate that box on every re-import.
            already_present.append(data["citekey"])
            continue

        session.add(Paper(project_id=project_id, **{**(extra_fields or {}), **data}))
        (duplicate_keys if is_duplicate else imported).append(data["citekey"])

    return Outcome(imported, duplicate_keys, already_present, skipped)
