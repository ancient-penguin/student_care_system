from datetime import timedelta

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import get_db
from app.models import AuthSession, User
from app.security import hash_token
from app.timeutil import as_utc, utcnow


def session_ttl(role: str) -> timedelta:
    days = settings.session_ttl_teacher_days if role == "teacher" else settings.session_ttl_student_days
    return timedelta(days=days)


def _unauthorized() -> HTTPException:
    return HTTPException(status.HTTP_401_UNAUTHORIZED, "로그인이 필요합니다", headers={"WWW-Authenticate": "Bearer"})


def current_session(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> AuthSession:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise _unauthorized()
    token = authorization[7:].strip()
    sess = db.scalar(select(AuthSession).where(AuthSession.token_hash == hash_token(token)))
    now = utcnow()
    if sess is None or sess.revoked_at is not None or as_utc(sess.expires_at) <= now:
        raise _unauthorized()
    if not sess.user.is_active:
        raise _unauthorized()
    # sliding 만료: 사용할 때마다 연장
    sess.last_used_at = now
    sess.expires_at = now + session_ttl(sess.user.role)
    db.commit()
    return sess


def current_user(sess: AuthSession = Depends(current_session)) -> User:
    return sess.user


def require_student(user: User = Depends(current_user)) -> User:
    if user.role != "student":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "학생 전용입니다")
    return user


def require_teacher(user: User = Depends(current_user)) -> User:
    if user.role != "teacher":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "선생님 전용입니다")
    return user
