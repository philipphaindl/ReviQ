"""
Shared decision state machine.

After any change to a paper's ReviewerDecisions (interactive upsert or
co-reviewer import), the derived state — FinalDecision and ConflictLog —
must be recomputed the same way regardless of which code path made the
change. ``sync_decision_state()`` is that single source of truth:

  exactly 1 decision            -> provisional FinalDecision mirroring it
  >= 2 decisions, all identical -> FinalDecision ("agreement"); any open
                                   conflict is auto-resolved
  >= 2 decisions, differing     -> open ConflictLog (created or refreshed)
                                   and NO FinalDecision — a provisional or
                                   stale final would leak one reviewer's
                                   solo call into PRISMA counts and later
                                   phases. Exception: if a *resolved*
                                   conflict already adjudicated exactly
                                   these votes, the resolution's final
                                   decision stays in place.
"""
from datetime import datetime

from sqlmodel import Session, select

from app.models import ConflictLog, FinalDecision, ReviewerDecision


def sync_decision_state(session: Session, project_id: int, paper_id: int, phase: str) -> str:
    """Recompute FinalDecision/ConflictLog from the current ReviewerDecisions.

    Returns a status string ("provisional" | "agreement" | "conflict_opened" |
    "conflict_updated" | "adjudicated" | "noop") that callers may use for
    reporting. The caller is responsible for ``session.commit()``.
    """
    decisions = session.exec(
        select(ReviewerDecision)
        .where(ReviewerDecision.paper_id == paper_id)
        .where(ReviewerDecision.phase == phase)
    ).all()
    if not decisions:
        return "noop"

    final = session.exec(
        select(FinalDecision)
        .where(FinalDecision.paper_id == paper_id)
        .where(FinalDecision.phase == phase)
    ).first()

    if len(decisions) == 1:
        # Solo reviewer — provisional final that tracks their current vote.
        _upsert_final(session, final, project_id, paper_id, phase, decisions[0].decision)
        return "provisional"

    open_conflict = session.exec(
        select(ConflictLog)
        .where(ConflictLog.paper_id == paper_id)
        .where(ConflictLog.phase == phase)
        .where(ConflictLog.resolved == False)  # noqa: E712
    ).first()

    if len({d.decision for d in decisions}) == 1:
        agreed = decisions[0].decision
        _upsert_final(session, final, project_id, paper_id, phase, agreed)
        if open_conflict:
            open_conflict.resolved = True
            open_conflict.resolution = agreed
            open_conflict.resolution_method = "agreement"
            open_conflict.resolved_at = datetime.utcnow()
            session.add(open_conflict)
        return "agreement"

    # Disagreement. ConflictLog is two-reviewer-oriented: record the first
    # vote plus the first vote that actually differs from it (by reviewer id).
    sorted_decs = sorted(decisions, key=lambda d: d.reviewer_id)
    d1 = sorted_decs[0]
    d2 = next(d for d in sorted_decs[1:] if d.decision != d1.decision)

    if open_conflict is None:
        if _already_adjudicated(session, paper_id, phase, d1, d2):
            # A human already settled exactly this disagreement — keep the
            # FinalDecision their resolution produced; do not reopen.
            return "adjudicated"
        session.add(ConflictLog(
            project_id=project_id,
            paper_id=paper_id,
            phase=phase,
            r1_reviewer_id=d1.reviewer_id,
            r2_reviewer_id=d2.reviewer_id,
            r1_decision=d1.decision,
            r2_decision=d2.decision,
            r1_rationale=d1.rationale,
            r2_rationale=d2.rationale,
        ))
        status = "conflict_opened"
    else:
        # Keep the open conflict in step with the votes it tracks, so the
        # conflict view never shows a vote a reviewer has since changed.
        open_conflict.r1_reviewer_id = d1.reviewer_id
        open_conflict.r2_reviewer_id = d2.reviewer_id
        open_conflict.r1_decision = d1.decision
        open_conflict.r2_decision = d2.decision
        open_conflict.r1_rationale = d1.rationale
        open_conflict.r2_rationale = d2.rationale
        session.add(open_conflict)
        status = "conflict_updated"

    # While a conflict is open there is no consensus: a provisional/stale
    # FinalDecision here is one reviewer's solo call and must not count as
    # the project's decision.
    if final is not None:
        session.delete(final)
    return status


def _upsert_final(session: Session, final: FinalDecision | None,
                  project_id: int, paper_id: int, phase: str, decision: str) -> None:
    if final is None:
        session.add(FinalDecision(
            project_id=project_id,
            paper_id=paper_id,
            phase=phase,
            decision=decision,
            resolution_method="agreement",
        ))
    elif final.decision != decision:
        final.decision = decision
        final.resolution_method = "agreement"
        final.timestamp = datetime.utcnow()
        session.add(final)
    # Same decision already recorded: leave the row (and its
    # discussion/arbitration provenance) untouched.


def _already_adjudicated(session: Session, paper_id: int, phase: str,
                         d1: ReviewerDecision, d2: ReviewerDecision) -> bool:
    """True if the most recent *resolved* conflict covers exactly the current votes."""
    latest = session.exec(
        select(ConflictLog)
        .where(ConflictLog.paper_id == paper_id)
        .where(ConflictLog.phase == phase)
        .where(ConflictLog.resolved == True)  # noqa: E712
        .order_by(ConflictLog.id.desc())
    ).first()
    if latest is None:
        return False
    recorded = {(latest.r1_reviewer_id, latest.r1_decision),
                (latest.r2_reviewer_id, latest.r2_decision)}
    current = {(d1.reviewer_id, d1.decision), (d2.reviewer_id, d2.decision)}
    return recorded == current
