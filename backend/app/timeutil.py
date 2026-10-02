from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(dt: datetime) -> datetime:
    """DB에서 tz 없이 돌아오는 경우까지 포함해 UTC aware로 맞춘다."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def week_start_kst(dt: datetime) -> date:
    """KST 기준, 월요일 시작 주의 첫날."""
    d = as_utc(dt).astimezone(KST).date()
    return d - timedelta(days=d.weekday())


def kst_date(dt: datetime) -> date:
    return as_utc(dt).astimezone(KST).date()
