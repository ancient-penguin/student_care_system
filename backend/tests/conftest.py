import os
from pathlib import Path

from dotenv import dotenv_values

# app을 import하기 전에 테스트 DB로 바꿔 둔다.
_env = dotenv_values(Path(__file__).resolve().parents[1] / ".env")
TEST_DB = os.environ.get("TEST_DATABASE_URL") or _env.get("TEST_DATABASE_URL")
if not TEST_DB:
    raise RuntimeError("TEST_DATABASE_URL이 필요합니다 (backend/.env 또는 환경변수)")
os.environ["DATABASE_URL"] = TEST_DB

import pytest  # noqa: E402
from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.config import REPO_DIR, normalize_db_url  # noqa: E402
from app.db import SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.models import User  # noqa: E402
from app.security import hash_secret  # noqa: E402
from app.templates_service import DEFAULT_TEMPLATES_PATH, load_templates, parse_templates_file  # noqa: E402

BACKEND = Path(__file__).resolve().parents[1]
SAMPLE = (REPO_DIR / "data" / "passages" / "g1-2021-29-a.yaml").read_text(encoding="utf-8")
TEACHER_PW = "teacher-pass-1234"


@pytest.fixture(scope="session", autouse=True)
def schema():
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    cfg.attributes["database_url"] = normalize_db_url(TEST_DB)
    command.upgrade(cfg, "head")
    yield


@pytest.fixture(autouse=True)
def clean_db():
    with engine.begin() as conn:
        conn.execute(text(
            "TRUNCATE reviews, answers, assignments, question_set_passages, question_sets, "
            "items, passages, sessions, users, templates RESTART IDENTITY CASCADE"
        ))
    with SessionLocal() as db:
        load_templates(db, parse_templates_file(DEFAULT_TEMPLATES_PATH))
        db.add(User(role="teacher", name="선생님", login_code="teacher", password_hash=hash_secret(TEACHER_PW), failed_count=0, is_active=True))
        db.commit()
    yield


@pytest.fixture
def client():
    return TestClient(app)


def bearer(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def teacher(client) -> dict:
    r = client.post("/auth/teacher-login", json={"code": "teacher", "password": TEACHER_PW})
    assert r.status_code == 200, r.text
    return bearer(r.json()["token"])


class World:
    """학생 2명, 샘플 지문 1개, 세트 1개, 학생별 배정 1개."""

    def __init__(self, client, teacher):
        self.client, self.teacher = client, teacher
        self.students = {}
        for code in ("kim", "lee"):
            r = client.post("/teacher/students", headers=teacher, json={"name": code, "login_code": code, "pin": "1234"})
            assert r.status_code == 201, r.text
            body = r.json()
            login = client.post("/auth/link-login", json={"token": body["link_token"]}).json()
            self.students[code] = {"id": body["id"], "link": body["link_token"], "headers": bearer(login["token"])}
        r = upload(client, teacher, {"a.yaml": SAMPLE})
        assert r.status_code == 200, r.text
        r = client.post("/teacher/question-sets", headers=teacher, json={"title": "1주차", "passage_ids": ["g1-2021-29-a"]})
        self.set_id = r.json()["id"]
        r = client.post("/teacher/assignments", headers=teacher, json={
            "student_ids": [s["id"] for s in self.students.values()], "set_id": self.set_id, "due_at": "2099-01-01T23:59:00+09:00",
        })
        assert r.status_code == 201, r.text
        ids = r.json()["assignment_ids"]
        self.students["kim"]["assignment"], self.students["lee"]["assignment"] = ids

    def h(self, code):
        return self.students[code]["headers"]

    def aid(self, code):
        return self.students[code]["assignment"]


@pytest.fixture
def world(client, teacher) -> World:
    return World(client, teacher)


def upload(client, teacher, files: dict[str, str]):
    return client.post(
        "/teacher/passages/upload", headers=teacher,
        files=[("files", (name, content.encode("utf-8"), "application/x-yaml")) for name, content in files.items()],
    )


# 샘플 지문의 모범 답(정답)을 학생 답 형식으로
MODEL_ANSWERS = {
    1: {"judgement": True, "tag": "접속사·명사절", "slots": {"role": "명사절을 이끄는 접속사", "word": "that"}},
    2: {"judgement": True, "tag": "본동사 유무", "slots": {"subject": "you", "verb": "Allow"}},
    3: {"judgement": False, "tag": "수일치", "slots": {"subject": "Finding", "number": "단수", "current": "are", "fixed": "is"}},
    4: {"judgement": True, "tag": "준동사", "slots": {"trigger": "desire", "form": "to부정사", "word": "to find"}},
    5: {"judgement": True, "tag": "형용사·부사", "slots": {"target": "relevant", "role": "부사", "word": "increasingly"}},
}


def answer_all(client, headers, assignment_id, skip: set[int] = frozenset()) -> dict:
    detail = client.get(f"/student/assignments/{assignment_id}", headers=headers).json()
    for it in detail["items"]:
        if it["no"] in skip:
            continue
        r = client.put(
            f"/student/assignments/{assignment_id}/answers/{it['id']}", headers=headers,
            json={**MODEL_ANSWERS[it["no"]], "duration_sec": 30},
        )
        assert r.status_code == 200, r.text
    return detail
