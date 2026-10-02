"""선생님 계정 생성/비밀번호 재설정. 회원가입 API는 없고 이 스크립트로만 만든다.

사용: cd backend && python -m scripts.create_teacher --name 선생님 --code teacher
비밀번호는 TEACHER_PASSWORD 환경변수가 있으면 그것을, 없으면 프롬프트로 입력받는다.
"""

import argparse
import getpass
import os
import sys

from sqlalchemy import select

from app.db import SessionLocal
from app.models import User
from app.security import hash_secret


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", required=True)
    ap.add_argument("--code", required=True)
    args = ap.parse_args()

    password = os.environ.get("TEACHER_PASSWORD") or getpass.getpass("비밀번호: ")
    if len(password) < 8:
        print("비밀번호는 8자 이상이어야 합니다", file=sys.stderr)
        return 1

    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.login_code == args.code))
        if user is not None and user.role != "teacher":
            print(f"코드 {args.code!r}는 학생이 쓰고 있습니다", file=sys.stderr)
            return 1
        if user is None:
            user = User(role="teacher", login_code=args.code, failed_count=0, is_active=True)
            db.add(user)
            action = "생성"
        else:
            action = "비밀번호 재설정"
        user.name = args.name
        user.password_hash = hash_secret(password)
        user.failed_count = 0
        user.locked_until = None
        db.commit()
    print(f"선생님 계정 {action}: {args.name} ({args.code})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
