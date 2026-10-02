"""배정 조회/상태 계산 공용 함수."""

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Answer, Assignment, Item, Passage, QuestionSetPassage
from app.passages_service import item_sentences
from app.timeutil import as_utc, utcnow


def iso(dt: datetime | None) -> str | None:
    return as_utc(dt).isoformat() if dt else None


def answered_counts(db: Session, assignment_ids: list[int]) -> dict[int, int]:
    if not assignment_ids:
        return {}
    rows = db.execute(
        select(Answer.assignment_id, func.count()).where(Answer.assignment_id.in_(assignment_ids)).group_by(Answer.assignment_id)
    )
    return dict(rows.all())


def status_of(a: Assignment, answered: int, now: datetime | None = None) -> str:
    """not_started / in_progress / done / late_done / overdue"""
    now = now or utcnow()
    if a.submitted_at:
        return "late_done" if a.is_late else "done"
    if as_utc(a.due_at) < now:
        return "overdue"
    return "in_progress" if answered else "not_started"


def summary(a: Assignment, answered: int) -> dict:
    return {
        "id": a.id,
        "title": a.question_set.title,
        "assigned_at": iso(a.assigned_at),
        "due_at": iso(a.due_at),
        "submitted_at": iso(a.submitted_at),
        "is_late": a.is_late,
        "status": status_of(a, answered),
        "total": len(a.item_order),
        "answered": answered,
    }


def set_passages(db: Session, set_id: int) -> list[Passage]:
    rows = db.scalars(
        select(Passage).join(QuestionSetPassage, QuestionSetPassage.passage_id == Passage.id)
        .where(QuestionSetPassage.set_id == set_id).order_by(QuestionSetPassage.order)
    )
    return list(rows)


def items_with_sentences(passages: list[Passage]) -> tuple[dict[int, Item], dict[int, str]]:
    items: dict[int, Item] = {}
    sentences: dict[int, str] = {}
    for p in passages:
        by_no = item_sentences(p.text, p.items)
        for it in p.items:
            items[it.id] = it
            sentences[it.id] = by_no[it.no]
    return items, sentences


def lock_assignment(db: Session, assignment_id: int) -> Assignment | None:
    return db.scalar(select(Assignment).where(Assignment.id == assignment_id).with_for_update())
