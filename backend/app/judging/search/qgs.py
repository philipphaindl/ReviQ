"""The quasi-gold standard: import, human check, deterministic split.

Three steps with a person in the middle. `import_seeds` collects candidates:
the seed models and known reviews from `qgs_seeds.toml` and, where marked, the
works they cite. `export_for_review` and `apply_review` hand the list to both
authors and take their verdict back, one column per work. `split` then divides
the accepted works 60/40 with the study's seed — once.
"""

from __future__ import annotations

import csv
import random
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from sqlmodel import Session, select

from ..models import AiqmQgs
from .openalex import OpenAlex, OpenAlexError, Work

SEEDS_PATH = Path(__file__).with_name("qgs_seeds.toml")
DEV_SHARE = 0.6


class QgsError(RuntimeError):
    pass


@dataclass
class ImportReport:
    added: int = 0
    already_present: int = 0
    unresolved: list[str] = field(default_factory=list)


def load_seeds(path: Path = SEEDS_PATH) -> list[dict]:
    return tomllib.loads(path.read_text(encoding="utf-8"))["work"]


def _key(work: Work) -> str:
    return work.openalex_id


def _same_title(a: str | None, b: str | None) -> bool:
    from .boolean import tokens
    return bool(a and b) and tokens(a) == tokens(b)


def _add(session: Session, study: str, work: Work, role: str, origin: str | None,
         report: ImportReport) -> None:
    exists = session.exec(select(AiqmQgs).where(
        AiqmQgs.study == study, AiqmQgs.key == _key(work))).first()
    if exists:
        report.already_present += 1
        return
    session.add(AiqmQgs(study=study, key=_key(work), openalex_id=work.openalex_id,
                        doi=work.doi, title=work.title, abstract=work.abstract,
                        keywords=work.keywords, year=work.year, work_type=work.work_type,
                        role=role, origin=origin))
    report.added += 1


def _resolve(client: OpenAlex, entry: dict) -> Work | None:
    if entry.get("doi"):
        return client.work_by_doi(entry["doi"])
    if entry.get("arxiv"):
        return client.work_by_doi(f"10.48550/arXiv.{entry['arxiv']}")
    if entry.get("title") and not entry.get("needs_reference"):
        match = client.work_by_title(entry["title"])
        if match and _same_title(match.title, entry["title"]):
            return match
    return None


def import_seeds(session: Session, study: str, client: OpenAlex,
                 seeds: list[dict] | None = None, *, expand: bool = True) -> ImportReport:
    report = ImportReport()
    for entry in seeds if seeds is not None else load_seeds():
        try:
            work = _resolve(client, entry)
        except OpenAlexError:
            work = None
        if work is None:
            report.unresolved.append(entry["citation"])
            continue
        _add(session, study, work, entry["role"], None, report)
        if expand and entry.get("expand"):
            for reference in work.referenced_works:
                try:
                    cited = client.work_by_id(reference)
                except OpenAlexError:
                    report.unresolved.append(f"{reference} (cited by {work.openalex_id})")
                    continue
                _add(session, study, cited, "reference", work.openalex_id, report)
    session.commit()
    return report


REVIEW_COLUMNS = ["key", "role", "origin", "year", "doi", "title", "accept"]


def export_for_review(session: Session, study: str, path: Path) -> int:
    rows = session.exec(select(AiqmQgs).where(AiqmQgs.study == study)
                        .order_by(AiqmQgs.role, AiqmQgs.key)).all()
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(REVIEW_COLUMNS)
        for r in rows:
            accept = "" if r.accepted is None else ("y" if r.accepted else "n")
            writer.writerow([r.key, r.role, r.origin or "", r.year or "", r.doi or "",
                             r.title or "", accept])
    return len(rows)


def apply_review(session: Session, study: str, path: Path) -> int:
    """Take the authors' verdicts back: `accept` is y or n; empty stays open."""
    changed = 0
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            verdict = (row.get("accept") or "").strip().lower()
            if verdict not in ("y", "n"):
                continue
            record = session.exec(select(AiqmQgs).where(
                AiqmQgs.study == study, AiqmQgs.key == row["key"])).first()
            if record is None:
                raise QgsError(f"unknown QGS key {row['key']!r}")
            if record.split and (verdict == "y") != record.accepted:
                raise QgsError(f"{row['key']}: already split; the verdict cannot change now")
            record.accepted = verdict == "y"
            session.add(record)
            changed += 1
    session.commit()
    return changed


def split(session: Session, study: str, seed: int, dev_share: float = DEV_SHARE) -> dict[str, int]:
    """Assign dev or holdout to every accepted work, deterministically. Refuses
    to run twice, and refuses while works are still unchecked."""

    rows = session.exec(select(AiqmQgs).where(AiqmQgs.study == study)).all()
    if any(r.split for r in rows):
        raise QgsError("the QGS is already split; the holdout must not be redrawn")
    if any(r.accepted is None for r in rows):
        raise QgsError("some candidates are not checked yet (accept = y or n)")
    accepted = sorted((r for r in rows if r.accepted), key=lambda r: r.key)
    if not accepted:
        raise QgsError("no accepted works to split")
    order = list(accepted)
    random.Random(seed).shuffle(order)
    cut = round(len(order) * dev_share)
    for index, record in enumerate(order):
        record.split = "dev" if index < cut else "holdout"
        session.add(record)
    session.commit()
    return {"dev": cut, "holdout": len(order) - cut}


def dev_set(session: Session, study: str) -> list[AiqmQgs]:
    return list(session.exec(select(AiqmQgs).where(
        AiqmQgs.study == study, AiqmQgs.split == "dev").order_by(AiqmQgs.key)))


def holdout_set(session: Session, study: str) -> list[AiqmQgs]:
    return list(session.exec(select(AiqmQgs).where(
        AiqmQgs.study == study, AiqmQgs.split == "holdout").order_by(AiqmQgs.key)))
