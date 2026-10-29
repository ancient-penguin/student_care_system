import random
import re
from collections import Counter
from datetime import date, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.assignments_service import (
    answered_counts,
    items_with_sentences,
    iso,
    set_passages,
    summary,
)
from app.db import get_db
from app.deps import require_teacher
from app.grading import diagnosis
from app.models import (
    Answer,
    Assignment,
    AuthSession,
    Item,
    Passage,
    QuestionSet,
    QuestionSetPassage,
    Review,
    User,
)
from app.passages_service import apply_passage, locked_changes, parse_passage_yaml
from app.security import hash_secret, hash_token, new_token
from app.templates_service import tag_order, templates_for_kind
from app.timeutil import KST, as_utc, kst_date, utcnow, week_start_kst

router = APIRouter(prefix="/teacher", dependencies=[Depends(require_teacher)])

PIN_RE = re.compile(r"^\d{4,6}$")


# ---------- 학생 관리 ----------

def active_sessions(db: Session, user_id: int) -> list[AuthSession]:
    now = utcnow()
    rows = db.scalars(
        select(AuthSession).where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))
        .order_by(AuthSession.last_used_at.desc())
    )
    return [s for s in rows if as_utc(s.expires_at) > now]


def get_student(db: Session, student_id: int) -> User:
    u = db.get(User, student_id)
    if u is None or u.role != "student":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "학생을 찾을 수 없습니다")
    return u


def issue_link(u: User) -> str:
    token = new_token()
    u.link_token_hash = hash_token(token)
    u.link_rotated_at = utcnow()
    return token


@router.get("/students")
def list_students(db: Session = Depends(get_db)):
    out = []
    for u in db.scalars(select(User).where(User.role == "student").order_by(User.name)):
        sessions = active_sessions(db, u.id)
        out.append({
            "id": u.id, "name": u.name, "login_code": u.login_code, "is_active": u.is_active,
            "link_rotated_at": iso(u.link_rotated_at), "active_sessions": len(sessions),
            "last_used_at": iso(sessions[0].last_used_at) if sessions else None,
        })
    return out


class StudentIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    login_code: str = Field(min_length=1, max_length=64)
    pin: str


@router.post("/students", status_code=201)
def create_student(body: StudentIn, db: Session = Depends(get_db)):
    if not PIN_RE.match(body.pin):
        raise HTTPException(422, "PIN은 숫자 4~6자리입니다")
    code = body.login_code.strip()
    if db.scalar(select(User).where(User.login_code == code)):
        raise HTTPException(status.HTTP_409_CONFLICT, "이미 쓰고 있는 코드입니다")
    u = User(role="student", name=body.name.strip(), login_code=code, pin_hash=hash_secret(body.pin), failed_count=0, is_active=True)
    token = issue_link(u)
    db.add(u)
    db.commit()
    return {"id": u.id, "name": u.name, "login_code": u.login_code, "link_token": token}


@router.get("/students/{student_id}")
def student_detail(student_id: int, db: Session = Depends(get_db)):
    u = get_student(db, student_id)
    assignments = list(db.scalars(select(Assignment).where(Assignment.student_id == u.id).order_by(Assignment.assigned_at.desc())))
    counts = answered_counts(db, [a.id for a in assignments])
    return {
        "id": u.id, "name": u.name, "login_code": u.login_code, "is_active": u.is_active,
        "link_rotated_at": iso(u.link_rotated_at),
        "locked_until": iso(u.locked_until) if u.locked_until and as_utc(u.locked_until) > utcnow() else None,
        "sessions": [
            {"id": s.id, "created_at": iso(s.created_at), "last_used_at": iso(s.last_used_at), "expires_at": iso(s.expires_at), "user_agent": s.user_agent}
            for s in active_sessions(db, u.id)
        ],
        "assignments": [summary(a, counts.get(a.id, 0)) for a in assignments],
    }


@router.post("/students/{student_id}/rotate-link")
def rotate_link(student_id: int, db: Session = Depends(get_db)):
    u = get_student(db, student_id)
    token = issue_link(u)
    db.commit()
    return {"link_token": token, "link_rotated_at": iso(u.link_rotated_at)}


@router.post("/students/{student_id}/revoke-sessions")
def revoke_sessions(student_id: int, db: Session = Depends(get_db)):
    u = get_student(db, student_id)
    res = db.execute(
        update(AuthSession).where(AuthSession.user_id == u.id, AuthSession.revoked_at.is_(None)).values(revoked_at=utcnow())
    )
    db.commit()
    return {"revoked": res.rowcount}


# ---------- 지문 ----------

@router.post("/passages/upload")
async def upload_passages(files: list[UploadFile] = File(...), db: Session = Depends(get_db)):
    """모든 파일을 검증한 뒤, 하나라도 실패하면 아무것도 저장하지 않는다(전부 아니면 전무)."""
    results, parsed = [], []
    seen_ids: dict[str, str] = {}
    for f in files:
        raw = await f.read()
        r = {"filename": f.filename, "passage_id": None, "status": "ok", "errors": [], "warnings": [], "changes": []}
        try:
            content = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            r.update(status="error", errors=[{"line": None, "message": "UTF-8 텍스트 파일이 아니다"}])
            results.append(r)
            continue
        pr = parse_passage_yaml(content, db)
        r["errors"] = [e.as_dict() for e in pr.errors]
        r["warnings"] = [w.as_dict() for w in pr.warnings]
        if pr.passage is None:
            r["status"] = "error"
            results.append(r)
            continue
        pid = pr.passage.passage_id
        r["passage_id"] = pid
        if pid in seen_ids:
            r["status"] = "error"
            r["errors"].append({"line": None, "message": f"같은 passage_id가 {seen_ids[pid]}에도 있다"})
            results.append(r)
            continue
        seen_ids[pid] = f.filename or ""
        existing = db.get(Passage, pid)
        if existing is not None and existing.locked:
            blocking, soft = locked_changes(existing, pr.passage)
            if blocking:
                r.update(status="conflict", changes=blocking)
                r["errors"].append({"line": None, "message": "배정된 적 있는 지문이라 정답·지문 변경이 거부되었다"})
            else:
                r["changes"] = soft
                r["warnings"] += [{"line": None, "message": f"배정된 지문 수정: {c}"} for c in soft]
        results.append(r)
        parsed.append((r, existing, pr.passage))

    has_conflict = any(r["status"] == "conflict" for r in results)
    has_error = any(r["status"] == "error" for r in results)
    if has_conflict or has_error:
        db.rollback()
        for r in results:
            if r["status"] == "ok":
                r["status"] = "skipped"
        code = status.HTTP_409_CONFLICT if has_conflict else 422
        return JSONResponse(status_code=code, content={"saved": False, "results": results})

    for r, existing, new in parsed:
        r["status"] = apply_passage(db, existing, new)
    db.commit()
    return {"saved": True, "results": results}


@router.get("/passages")
def list_passages(db: Session = Depends(get_db)):
    return [
        {"id": p.id, "kind": p.kind, "source": p.source, "locked": p.locked, "item_count": len(p.items), "created_at": iso(p.created_at)}
        for p in db.scalars(select(Passage).order_by(Passage.created_at.desc(), Passage.id))
    ]


# ---------- 세트와 배정 ----------

@router.get("/question-sets")
def list_sets(db: Session = Depends(get_db)):
    out = []
    for s in db.scalars(select(QuestionSet).order_by(QuestionSet.created_at.desc())):
        passages = set_passages(db, s.id)
        out.append({
            "id": s.id, "title": s.title, "mode": s.mode, "created_at": iso(s.created_at),
            "passage_ids": [p.id for p in passages], "item_count": sum(len(p.items) for p in passages),
        })
    return out


class SetIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    passage_ids: list[str] = Field(min_length=1)


@router.post("/question-sets", status_code=201)
def create_set(body: SetIn, db: Session = Depends(get_db)):
    if len(set(body.passage_ids)) != len(body.passage_ids):
        raise HTTPException(422, "같은 지문이 두 번 들어 있습니다")
    missing = [pid for pid in body.passage_ids if db.get(Passage, pid) is None]
    if missing:
        raise HTTPException(422, f"없는 지문: {', '.join(missing)}")
    s = QuestionSet(title=body.title.strip(), mode="shuffle")
    s.passages = [QuestionSetPassage(passage_id=pid, order=i) for i, pid in enumerate(body.passage_ids)]
    db.add(s)
    db.commit()
    return {"id": s.id, "title": s.title}


class AssignIn(BaseModel):
    student_ids: list[int] = Field(min_length=1)
    set_id: int
    due_at: datetime


@router.post("/assignments", status_code=201)
def create_assignments(body: AssignIn, db: Session = Depends(get_db)):
    qs = db.get(QuestionSet, body.set_id)
    if qs is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "세트를 찾을 수 없습니다")
    due = body.due_at if body.due_at.tzinfo else body.due_at.replace(tzinfo=KST)  # 시간대 없으면 KST로 본다
    passages = set_passages(db, qs.id)
    item_ids = [it.id for p in passages for it in p.items]
    if not item_ids:
        raise HTTPException(422, "세트에 항목이 없습니다")
    students = [get_student(db, sid) for sid in dict.fromkeys(body.student_ids)]
    created = []
    for u in students:
        order = item_ids[:]
        random.shuffle(order)
        a = Assignment(student_id=u.id, set_id=qs.id, assigned_at=utcnow(), due_at=as_utc(due), item_order=order, is_late=False)
        db.add(a)
        created.append(a)
    for p in passages:
        p.locked = True
    db.commit()
    return {"assignment_ids": [a.id for a in created]}


# ---------- 현황 ----------

@router.get("/overview")
def overview(week: date | None = None, weeks: int = 6, db: Session = Depends(get_db)):
    """학생 × 주차 표(배정일 기준, KST 월요일 시작) + 마감 지난 미제출 목록."""
    weeks = max(1, min(weeks, 26))
    last = week_start_kst(utcnow()) if week is None else week - timedelta(days=week.weekday())
    week_list = [last - timedelta(weeks=i) for i in range(weeks - 1, -1, -1)]
    first_utc = datetime.combine(week_list[0], datetime.min.time(), tzinfo=KST)
    end_utc = datetime.combine(last + timedelta(days=7), datetime.min.time(), tzinfo=KST)

    students = list(db.scalars(select(User).where(User.role == "student", User.is_active.is_(True)).order_by(User.name)))
    in_range = list(db.scalars(select(Assignment).where(Assignment.assigned_at >= first_utc, Assignment.assigned_at < end_utc)))
    overdue_rows = list(db.scalars(
        select(Assignment).where(Assignment.submitted_at.is_(None), Assignment.due_at < utcnow()).order_by(Assignment.due_at)
    ))
    counts = answered_counts(db, list({a.id for a in in_range + overdue_rows}))

    cells: dict[int, dict[str, list]] = {s.id: {w.isoformat(): [] for w in week_list} for s in students}
    for a in in_range:
        wk = week_start_kst(a.assigned_at).isoformat()
        if a.student_id in cells and wk in cells[a.student_id]:
            cells[a.student_id][wk].append(summary(a, counts.get(a.id, 0)))

    now = utcnow()
    return {
        "weeks": [w.isoformat() for w in week_list],
        "students": [{"id": s.id, "name": s.name, "cells": cells[s.id]} for s in students],
        "overdue": [
            {
                "assignment_id": a.id, "student_id": a.student_id, "student_name": a.student.name,
                "title": a.question_set.title, "due_at": iso(a.due_at),
                "days_overdue": (kst_date(now) - kst_date(a.due_at)).days,
                "answered": counts.get(a.id, 0), "total": len(a.item_order),
            }
            for a in overdue_rows if a.student.is_active
        ],
    }


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db)):
    """요약 지표 + 학생별 최근 숙제 + 세트별 성과(제출된 답 기준)."""
    now = utcnow()
    students = list(db.scalars(select(User).where(User.role == "student", User.is_active.is_(True)).order_by(User.name)))
    student_ids = [s.id for s in students]
    assignments = list(db.scalars(
        select(Assignment).where(Assignment.student_id.in_(student_ids)).order_by(Assignment.assigned_at.desc(), Assignment.id.desc())
    )) if student_ids else []
    counts = answered_counts(db, [a.id for a in assignments])

    # 제출된 답: (학생, 세트, 판단 정답, 태그 정답, 리뷰 여부)
    rows = db.execute(
        select(Assignment.student_id, Assignment.set_id, Answer.judgement_ok, Answer.tag_ok, Review.id)
        .join(Answer, Answer.assignment_id == Assignment.id)
        .outerjoin(Review, Review.answer_id == Answer.id)
        .where(Assignment.submitted_at.is_not(None), Assignment.student_id.in_(student_ids or [0]))
    ).all()
    per_student: dict[int, list[int]] = {}  # [답 수, 판단 정답 수, 검토 대기 수]
    per_set: dict[int, list[int]] = {}  # [답 수, 판단 정답 수, 태그 정답 수]
    for sid, set_id, j_ok, t_ok, review_id in rows:
        s = per_student.setdefault(sid, [0, 0, 0])
        s[0] += 1
        s[1] += 1 if j_ok else 0
        s[2] += 0 if review_id else 1
        q = per_set.setdefault(set_id, [0, 0, 0])
        q[0] += 1
        q[1] += 1 if j_ok else 0
        q[2] += 1 if t_ok else 0

    last_activity = dict(db.execute(
        select(Assignment.student_id, func.max(Answer.saved_at))
        .join(Answer, Answer.assignment_id == Assignment.id)
        .where(Assignment.student_id.in_(student_ids or [0])).group_by(Assignment.student_id)
    ).all())

    latest: dict[int, Assignment] = {}
    for a in assignments:
        latest.setdefault(a.student_id, a)

    # 최근 배정된 세트부터 최대 8개
    recent_sets: list[int] = []
    for a in assignments:
        if a.set_id not in recent_sets:
            recent_sets.append(a.set_id)
    recent_sets = recent_sets[:8]
    submitted_per_set = Counter(a.set_id for a in assignments if a.submitted_at)
    set_titles = {qs.id: qs.title for qs in db.scalars(select(QuestionSet).where(QuestionSet.id.in_(recent_sets or [0])))}

    total_answers = sum(v[0] for v in per_student.values())
    rate = lambda ok, n: ok / n if n else None  # noqa: E731
    return {
        "metrics": {
            "total_students": len(students),
            "accuracy": rate(sum(v[1] for v in per_student.values()), total_answers),
            "pending_reviews": sum(v[2] for v in per_student.values()),
            "overdue": sum(1 for a in assignments if not a.submitted_at and as_utc(a.due_at) < now),
        },
        "students": [
            {
                "id": s.id,
                "name": s.name,
                "latest": summary(latest[s.id], counts.get(latest[s.id].id, 0)) if s.id in latest else None,
                "accuracy": rate(per_student.get(s.id, [0, 0])[1], per_student.get(s.id, [0])[0]),
                "pending_reviews": per_student.get(s.id, [0, 0, 0])[2],
                "last_activity_at": iso(last_activity.get(s.id)),
            }
            for s in students
        ],
        "assignments_chart": [
            {
                "set_id": set_id,
                "title": set_titles.get(set_id, ""),
                "submitted": submitted_per_set.get(set_id, 0),
                "accuracy": rate(per_set.get(set_id, [0, 0])[1], per_set.get(set_id, [0])[0]),
                "tag_accuracy": rate(per_set.get(set_id, [0, 0, 0])[2], per_set.get(set_id, [0])[0]),
            }
            for set_id in recent_sets
        ],
    }


@router.get("/assignments/{assignment_id}")
def assignment_detail(assignment_id: int, db: Session = Depends(get_db)):
    a = db.get(Assignment, assignment_id)
    if a is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "숙제를 찾을 수 없습니다")
    passages = set_passages(db, a.set_id)
    _, sentences = items_with_sentences(passages)
    answers = {ans.item_id: ans for ans in a.answers}
    firsts = [as_utc(ans.created_at) for ans in answers.values()]
    daily = Counter(kst_date(t).isoformat() for t in firsts)

    def answer_out(ans: Answer | None):
        if ans is None:
            return None
        return {
            "answer_id": ans.id, "judgement": ans.judgement, "tag": ans.tag, "slots": ans.slots,
            "created_at": iso(ans.created_at), "saved_at": iso(ans.saved_at), "duration_sec": ans.duration_sec,
            "judgement_ok": ans.judgement_ok, "tag_ok": ans.tag_ok, "slots_check": ans.slots_check,
            "diagnosis": diagnosis(ans), "review_status": ans.review.status if ans.review else None,
        }

    return {
        **summary(a, len(answers)),
        "student": {"id": a.student.id, "name": a.student.name},
        "kind": passages[0].kind if passages else "grammar",
        "started_at": iso(min(firsts)) if firsts else None,
        "total_duration_sec": sum(ans.duration_sec or 0 for ans in answers.values()),
        "daily_saves": [{"date": d, "count": c} for d, c in sorted(daily.items())],
        "passages": [
            {
                "id": p.id, "source": p.source, "text": p.text,
                "items": [
                    {
                        "id": it.id, "no": it.no, "choice": it.choice, "sentence": sentences[it.id],
                        "correct": {"is_correct": it.is_correct, "tag": it.tag, "model_slots": it.model_slots, "explanation": it.explanation},
                        "answer": answer_out(answers.get(it.id)),
                    }
                    for it in p.items
                ],
            }
            for p in passages
        ],
    }


class ReviewIn(BaseModel):
    status: Literal["ok", "needs_work"]


@router.put("/answers/{answer_id}/review")
def review_answer(answer_id: int, body: ReviewIn, db: Session = Depends(get_db)):
    ans = db.get(Answer, answer_id)
    if ans is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "답을 찾을 수 없습니다")
    if not ans.assignment.submitted_at:
        raise HTTPException(status.HTTP_409_CONFLICT, "제출된 숙제만 검토할 수 있습니다")
    if ans.review is None:
        ans.review = Review(status=body.status, reviewed_at=utcnow())
    else:
        ans.review.status = body.status
        ans.review.reviewed_at = utcnow()
    db.commit()
    return {"answer_id": ans.id, "status": ans.review.status}


@router.get("/stats/tags")
def tag_stats(student_id: int | None = None, kind: str = "grammar", db: Session = Depends(get_db)):
    """제출된 답 기준. 태그 = 항목의 정답 태그."""
    q = (
        select(Item.tag, Answer.judgement_ok, Answer.tag_ok)
        .join(Answer, Answer.item_id == Item.id)
        .join(Assignment, Answer.assignment_id == Assignment.id)
        .join(Passage, Item.passage_id == Passage.id)
        .where(Assignment.submitted_at.is_not(None), Passage.kind == kind)
    )
    if student_id is not None:
        q = q.where(Assignment.student_id == student_id)
    agg: dict[str, list[int]] = {}
    for tag, j_ok, t_ok in db.execute(q):
        n, j_err, t_err = agg.setdefault(tag, [0, 0, 0])
        agg[tag] = [n + 1, j_err + (0 if j_ok else 1), t_err + (0 if t_ok else 1)]
    order = tag_order(templates_for_kind(db, kind))
    order += [t for t in agg if t not in order]
    return {
        "student_id": student_id,
        "tags": [
            {
                "tag": t, "count": agg.get(t, [0])[0],
                "judgement_error_rate": agg[t][1] / agg[t][0] if t in agg else None,
                "tag_mismatch_rate": agg[t][2] / agg[t][0] if t in agg else None,
            }
            for t in order
        ],
    }
