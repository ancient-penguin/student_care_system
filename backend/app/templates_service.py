"""근거 문장 틀(templates) 적재와 조회, 슬롯 검증."""

import re
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app import yamlutil
from app.config import ALLOWED_KINDS, REPO_DIR
from app.models import Template

DEFAULT_TEMPLATES_PATH = REPO_DIR / "data" / "templates.yaml"
PLACEHOLDER = re.compile(r"\{(\w+)\}")
JUDGEMENTS = ("wrong", "right")


def judgement_key(is_correct: bool) -> str:
    return "right" if is_correct else "wrong"


def parse_templates_file(path: Path) -> list[dict]:
    entries = yamlutil.load(path.read_text(encoding="utf-8")) or []
    errors = []
    seen = set()
    for i, e in enumerate(entries):
        where = f"#{i + 1} ({e.get('tag')}/{e.get('judgement')})"
        if e.get("kind") not in ALLOWED_KINDS:
            errors.append(f"{where}: 알 수 없는 kind {e.get('kind')!r}")
        if e.get("judgement") not in JUDGEMENTS:
            errors.append(f"{where}: judgement는 wrong/right 중 하나")
        key = (e.get("kind"), e.get("tag"), e.get("judgement"))
        if key in seen:
            errors.append(f"{where}: 중복된 (kind, tag, judgement)")
        seen.add(key)
        slots = e.get("slots") or {}
        names = PLACEHOLDER.findall(e.get("body", ""))
        if set(names) != set(slots):
            errors.append(f"{where}: body의 빈칸 {sorted(set(names))}과 slots {sorted(slots)}가 다르다")
        for name, spec in slots.items():
            if spec != "text" and not (isinstance(spec, list) and spec and all(isinstance(v, str) for v in spec)):
                errors.append(f"{where}: 슬롯 {name}은 text 또는 보기 리스트여야 한다")
    if errors:
        raise ValueError("\n".join(errors))
    return entries


def load_templates(db: Session, entries: list[dict]) -> int:
    """파일에 등장한 kind의 틀을 통째로 교체한다. id 순서 = 파일 순서 = 태그 표시 순서."""
    kinds = {e["kind"] for e in entries}
    db.execute(delete(Template).where(Template.kind.in_(kinds)))
    for e in entries:
        db.add(Template(kind=e["kind"], tag=e["tag"], judgement=e["judgement"], body=e["body"], slots=e["slots"]))
    db.commit()
    return len(entries)


def templates_for_kind(db: Session, kind: str) -> list[Template]:
    return list(db.scalars(select(Template).where(Template.kind == kind).order_by(Template.id)))


def template_map(db: Session, kind: str) -> dict[tuple[str, str], Template]:
    return {(t.tag, t.judgement): t for t in templates_for_kind(db, kind)}


def tag_order(templates: list[Template]) -> list[str]:
    tags: list[str] = []
    for t in templates:
        if t.tag not in tags:
            tags.append(t.tag)
    return tags


def validate_slots(template: Template, slots: dict) -> list[str]:
    """슬롯 키가 틀과 일치하고, 선택형 값은 보기 안에, 입력형 값은 비어 있지 않아야 한다."""
    errors = []
    if not isinstance(slots, dict):
        return ["slots는 객체여야 한다"]
    expected = set(template.slots)
    got = set(slots)
    if missing := sorted(expected - got):
        errors.append(f"빠진 슬롯: {', '.join(missing)}")
    if extra := sorted(got - expected):
        errors.append(f"알 수 없는 슬롯: {', '.join(extra)}")
    for name in sorted(expected & got):
        spec, value = template.slots[name], slots[name]
        if not isinstance(value, str) or not value.strip():
            errors.append(f"슬롯 {name}이 비어 있다")
        elif isinstance(spec, list) and value not in spec:
            errors.append(f"슬롯 {name}의 값 {value!r}은 보기 {spec} 밖이다")
    return errors
