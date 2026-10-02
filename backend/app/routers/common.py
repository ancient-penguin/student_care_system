from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.config import ALLOWED_KINDS, LOCK_MINUTES, PIN_MAX_FAILURES
from app.db import get_db
from app.deps import current_session, current_user, session_ttl
from app.models import AuthSession, User
from app.security import hash_token, new_token, verify_secret
from app.templates_service import tag_order, templates_for_kind
from app.timeutil import as_utc, utcnow

router = APIRouter()


def user_out(u: User) -> dict:
    return {"id": u.id, "role": u.role, "name": u.name, "login_code": u.login_code}


def start_session(db: Session, user: User, request: Request) -> dict:
    token = new_token()
    now = utcnow()
    db.add(AuthSession(
        user_id=user.id, token_hash=hash_token(token), created_at=now, last_used_at=now,
        expires_at=now + session_ttl(user.role), user_agent=(request.headers.get("user-agent") or "")[:500],
    ))
    db.commit()
    return {"token": token, "user": user_out(user)}


@router.get("/health")
def health(db: Session = Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"ok": True}


class LinkLogin(BaseModel):
    token: str


class CodeLogin(BaseModel):
    code: str
    pin: str


class TeacherLogin(BaseModel):
    code: str
    password: str


@router.post("/auth/link-login")
def link_login(body: LinkLogin, request: Request, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.link_token_hash == hash_token(body.token.strip())))
    if user is None or user.role != "student" or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "링크가 만료되었습니다. 선생님께 새 링크를 요청하세요")
    return start_session(db, user, request)


def _password_login(db: Session, request: Request, code: str, secret: str, role: str) -> dict:
    user = db.scalar(select(User).where(User.login_code == code.strip(), User.role == role))
    fail = HTTPException(status.HTTP_401_UNAUTHORIZED, "코드 또는 비밀번호가 맞지 않습니다")
    if user is None or not user.is_active:
        raise fail
    now = utcnow()
    if user.locked_until and as_utc(user.locked_until) > now:
        raise HTTPException(status.HTTP_423_LOCKED, f"여러 번 틀려 잠겼습니다. {LOCK_MINUTES}분 뒤에 다시 시도하세요")
    hashed = user.pin_hash if role == "student" else user.password_hash
    if not verify_secret(hashed, secret):
        user.failed_count = (user.failed_count or 0) + 1
        if user.failed_count >= PIN_MAX_FAILURES:
            user.failed_count = 0
            user.locked_until = now + timedelta(minutes=LOCK_MINUTES)
        db.commit()
        raise fail
    user.failed_count = 0
    user.locked_until = None
    return start_session(db, user, request)


@router.post("/auth/code-login")
def code_login(body: CodeLogin, request: Request, db: Session = Depends(get_db)):
    return _password_login(db, request, body.code, body.pin, "student")


@router.post("/auth/teacher-login")
def teacher_login(body: TeacherLogin, request: Request, db: Session = Depends(get_db)):
    return _password_login(db, request, body.code, body.password, "teacher")


@router.post("/auth/logout")
def logout(sess: AuthSession = Depends(current_session), db: Session = Depends(get_db)):
    sess.revoked_at = utcnow()
    db.commit()
    return {"ok": True}


@router.get("/me")
def me(user: User = Depends(current_user)):
    return user_out(user)


@router.get("/templates")
def get_templates(kind: str = "grammar", _: User = Depends(current_user), db: Session = Depends(get_db)):
    if kind not in ALLOWED_KINDS:
        raise HTTPException(404, "알 수 없는 kind")
    tpls = templates_for_kind(db, kind)
    return {
        "kind": kind,
        "tags": tag_order(tpls),
        "templates": [{"tag": t.tag, "judgement": t.judgement, "body": t.body, "slots": t.slots} for t in tpls],
    }
