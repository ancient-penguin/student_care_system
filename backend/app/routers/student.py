"""학생 API. 제출 전 응답에는 is_correct, 정답 태그, model_slots, explanation을 절대 넣지 않는다."""

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.assignments_service import (
    answered_counts,
    items_with_sentences,
    iso,
    lock_assignment,
    set_passages,
    summary,
)
from app.config import DURATION_CAP_PER_SAVE
from app.db import get_db
from app.deps import require_student
from app.grading import grade
from app.models import Answer, Assignment, User
from app.templates_service import judgement_key, template_map, validate_slots
from app.timeutil import as_utc, utcnow

router = APIRouter(prefix="/student")

NOT_FOUND = "숙제를 찾을 수 없습니다"


def own_assignment(db: Session, user: User, assignment_id: int, for_update: bool = False) -> Assignment:
    a = lock_assignment(db, assignment_id) if for_update else db.get(Assignment, assignment_id)
    if a is None or a.student_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, NOT_FOUND)
    return a


@router.get("/assignments")
def list_assignments(user: User = Depends(require_student), db: Session = Depends(get_db)):
    rows = list(db.scalars(select(Assignment).where(Assignment.student_id == user.id).order_by(Assignment.assigned_at.desc())))
    counts = answered_counts(db, [a.id for a in rows])
    return [summary(a, counts.get(a.id, 0)) for a in rows]


@router.get("/assignments/{assignment_id}")
def get_assignment(assignment_id: int, user: User = Depends(require_student), db: Session = Depends(get_db)):
    a = own_assignment(db, user, assignment_id)
    passages = set_passages(db, a.set_id)
    items, sentences = items_with_sentences(passages)
    answers = {ans.item_id: ans for ans in a.answers}
    return {
        **summary(a, len(answers)),
        "kind": passages[0].kind if passages else "grammar",
        "item_order": a.item_order,
        "passages": [{"id": p.id, "source": p.source, "text": p.text} for p in passages],
        "items": [
            {"id": iid, "passage_id": items[iid].passage_id, "no": items[iid].no, "choice": items[iid].choice, "sentence": sentences[iid]}
            for iid in a.item_order
        ],
        "answers": {
            str(iid): {"judgement": ans.judgement, "tag": ans.tag, "slots": ans.slots, "saved_at": iso(ans.saved_at)}
            for iid, ans in answers.items()
        },
    }


class AnswerIn(BaseModel):
    judgement: bool
    tag: str
    slots: dict[str, str]
    duration_sec: int = 0


@router.put("/assignments/{assignment_id}/answers/{item_id}")
def save_answer(assignment_id: int, item_id: int, body: AnswerIn, user: User = Depends(require_student), db: Session = Depends(get_db)):
    a = own_assignment(db, user, assignment_id, for_update=True)
    if a.submitted_at:
        raise HTTPException(status.HTTP_409_CONFLICT, "이미 제출한 숙제는 수정할 수 없습니다")
    if item_id not in a.item_order:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "항목을 찾을 수 없습니다")
    passages = set_passages(db, a.set_id)
    kind = next((p.kind for p in passages for it in p.items if it.id == item_id), "grammar")
    tpl = template_map(db, kind).get((body.tag, judgement_key(body.judgement)))
    if tpl is None:
        raise HTTPException(422, "알 수 없는 태그입니다")
    slots = {k: v.strip() for k, v in body.slots.items()}
    if errors := validate_slots(tpl, slots):
        raise HTTPException(422, {"message": "빈칸을 확인하세요", "errors": errors})

    now = utcnow()
    added = max(0, min(body.duration_sec, DURATION_CAP_PER_SAVE))
    ans = db.scalar(select(Answer).where(Answer.assignment_id == a.id, Answer.item_id == item_id))
    if ans is None:
        ans = Answer(assignment_id=a.id, item_id=item_id, created_at=now, duration_sec=0)
        db.add(ans)
    ans.judgement, ans.tag, ans.slots = body.judgement, body.tag, slots
    ans.saved_at = now
    ans.duration_sec = (ans.duration_sec or 0) + added
    db.commit()
    answered = answered_counts(db, [a.id]).get(a.id, 0)
    return {"ok": True, "saved_at": iso(now), "answered": answered, "total": len(a.item_order)}


@router.post("/assignments/{assignment_id}/submit")
def submit(assignment_id: int, user: User = Depends(require_student), db: Session = Depends(get_db)):
    a = own_assignment(db, user, assignment_id, for_update=True)
    if a.submitted_at:
        raise HTTPException(status.HTTP_409_CONFLICT, "이미 제출했습니다")
    answers = {ans.item_id: ans for ans in a.answers}
    incomplete = [iid for iid in a.item_order if iid not in answers]
    if incomplete:
        db.rollback()
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"detail": "아직 완료하지 않은 항목이 있습니다", "incomplete_item_ids": incomplete},
        )
    passages = set_passages(db, a.set_id)
    items, _ = items_with_sentences(passages)
    kind_of = {it.id: p.kind for p in passages for it in p.items}
    maps = {k: template_map(db, k) for k in set(kind_of.values())}
    for iid, ans in answers.items():
        tpl = maps[kind_of[iid]].get((ans.tag, judgement_key(ans.judgement)))
        grade(ans, items[iid], tpl)
    now = utcnow()
    a.submitted_at = now
    a.is_late = now > as_utc(a.due_at)
    db.commit()
    return {"ok": True, "submitted_at": iso(now), "is_late": a.is_late}


@router.get("/assignments/{assignment_id}/result")
def result(assignment_id: int, user: User = Depends(require_student), db: Session = Depends(get_db)):
    a = own_assignment(db, user, assignment_id)
    if not a.submitted_at:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "제출한 뒤에 결과를 볼 수 있습니다")
    passages = set_passages(db, a.set_id)
    items, sentences = items_with_sentences(passages)
    answers = {ans.item_id: ans for ans in a.answers}
    return {
        **summary(a, len(answers)),
        "kind": passages[0].kind if passages else "grammar",
        "passages": [
            {
                "id": p.id, "source": p.source, "text": p.text,
                "items": [
                    {
                        "id": it.id, "no": it.no, "choice": it.choice, "sentence": sentences[it.id],
                        "mine": {"judgement": answers[it.id].judgement, "tag": answers[it.id].tag, "slots": answers[it.id].slots},
                        "correct": {"is_correct": it.is_correct, "tag": it.tag, "model_slots": it.model_slots, "explanation": it.explanation},
                        "judgement_ok": answers[it.id].judgement_ok,
                        "tag_ok": answers[it.id].tag_ok,
                    }
                    for it in p.items if it.id in answers
                ],
            }
            for p in passages
        ],
    }
