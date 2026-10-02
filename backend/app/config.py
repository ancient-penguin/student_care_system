import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = BACKEND_DIR.parent

load_dotenv(BACKEND_DIR / ".env")


def normalize_db_url(url: str) -> str:
    """Neon/Render가 주는 postgres:// 주소를 psycopg 3 드라이버 주소로 바꾼다."""
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


@dataclass(frozen=True)
class Settings:
    database_url: str
    cors_origins: list[str]
    session_ttl_student_days: int
    session_ttl_teacher_days: int
    app_env: str


def load_settings() -> Settings:
    return Settings(
        database_url=normalize_db_url(os.environ.get("DATABASE_URL", "")),
        cors_origins=[o.strip() for o in os.environ.get("CORS_ORIGINS", "").split(",") if o.strip()],
        session_ttl_student_days=int(os.environ.get("SESSION_TTL_STUDENT_DAYS", "90")),
        session_ttl_teacher_days=int(os.environ.get("SESSION_TTL_TEACHER_DAYS", "30")),
        app_env=os.environ.get("APP_ENV", "development"),
    )


settings = load_settings()

# 정책 상수
PIN_MAX_FAILURES = 5
LOCK_MINUTES = 5
DURATION_CAP_PER_SAVE = 600
ALLOWED_KINDS = ("grammar",)
