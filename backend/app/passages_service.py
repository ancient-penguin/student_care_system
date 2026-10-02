"""지문 YAML 파싱, 검증(줄 번호 포함), 문장 분리, upsert와 locked 처리."""

import re
from dataclasses import dataclass, field

import yaml
from sqlalchemy.orm import Session

from app import yamlutil
from app.config import ALLOWED_KINDS
from app.models import Item, Passage
from app.templates_service import judgement_key, template_map, validate_slots

MARKER = re.compile(r"\[\[(\d+)\]\]")
# 마침표/물음표/느낌표 (+ 닫는 따옴표·괄호) 뒤의 공백
BOUNDARY = re.compile(r"[.?!][\"'”’)]*\s+")
ABBREVIATIONS = {
    "mr", "mrs", "ms", "dr", "prof", "st", "jr", "sr", "vs", "etc", "e.g", "i.e",
    "no", "u.s", "u.k", "a.m", "p.m", "fig", "inc", "ltd", "co", "cf", "approx",
}
OPENING_QUOTES = "\"'“‘("


@dataclass
class Issue:
    line: int | None
    message: str

    def as_dict(self) -> dict:
        return {"line": self.line, "message": self.message}


@dataclass
class ParsedPassage:
    passage_id: str
    kind: str
    source: str
    text: str
    items: list[dict]


@dataclass
class ParseResult:
    passage: ParsedPassage | None
    errors: list[Issue] = field(default_factory=list)
    warnings: list[Issue] = field(default_factory=list)


# ---------- 문장 분리 ----------

def normalize_text(text: str) -> str:
    return " ".join(text.split())


def split_sentences(text: str, choices: dict[int, str]) -> list[str]:
    """마커는 그대로 둔 채 문장 단위로 자른다. 마커로 시작하는 문장은 그 항목의 choice 첫 글자로 대문자 여부를 판단한다."""
    text = normalize_text(text)
    sentences, start = [], 0
    for m in BOUNDARY.finditer(text):
        nxt = m.end()
        if nxt >= len(text):
            continue
        # 다음 문장의 첫 글자
        j = nxt
        while j < len(text) and text[j] in OPENING_QUOTES:
            j += 1
        marker = MARKER.match(text, j)
        first = (choices.get(int(marker.group(1)), "") or " ")[0] if marker else text[j : j + 1]
        if not first.isupper():
            continue
        # 약어 오분리 방지
        if text[m.start()] == ".":
            word = text[start : m.start()].split(" ")[-1].lstrip(OPENING_QUOTES).lower()
            if word in ABBREVIATIONS or (len(word) == 1 and word.isalpha()):
                continue
        sentences.append(text[start:nxt].strip())
        start = nxt
    tail = text[start:].strip()
    if tail:
        sentences.append(tail)
    return sentences


def item_sentences(text: str, items: list) -> dict[int, str]:
    """항목 no → 학생에게 보여줄 문장. context가 있으면 우선."""
    get = (lambda it, k: it[k] if isinstance(it, dict) else getattr(it, k))
    choices = {get(it, "no"): get(it, "choice") for it in items}
    sentences = split_sentences(text, choices)
    out = {}
    for it in items:
        no, ctx = get(it, "no"), get(it, "context")
        if ctx:
            out[no] = normalize_text(ctx)
            continue
        tag = f"[[{no}]]"
        out[no] = next((s for s in sentences if tag in s), "")
    return out


# ---------- YAML 줄 번호 ----------

def _line_of(root, path: tuple) -> int | None:
    node = root
    found = node.start_mark.line + 1 if node is not None else None
    for key in path:
        if isinstance(node, yaml.MappingNode):
            nxt = next((v for k, v in node.value if k.value == key), None)
            if nxt is None:
                return found
            # 키 위치를 우선 사용(값이 블록 스칼라일 때 더 정확)
            found = next(k for k, v in node.value if k.value == key).start_mark.line + 1
            node = nxt
        elif isinstance(node, yaml.SequenceNode) and isinstance(key, int) and key < len(node.value):
            node = node.value[key]
            found = node.start_mark.line + 1
        else:
            return found
    return found


# ---------- 파싱 + 검증 ----------

def parse_passage_yaml(content: str, db: Session) -> ParseResult:
    try:
        root = yamlutil.compose(content)
        data = yamlutil.load(content)
    except yaml.YAMLError as e:
        mark = getattr(e, "problem_mark", None)
        return ParseResult(None, [Issue(mark.line + 1 if mark else None, f"YAML 문법 오류: {getattr(e, 'problem', e)}")])

    res = ParseResult(None)
    err = lambda path, msg: res.errors.append(Issue(_line_of(root, path), msg))  # noqa: E731
    warn = lambda path, msg: res.warnings.append(Issue(_line_of(root, path), msg))  # noqa: E731

    if not isinstance(data, dict):
        err((), "최상위는 passage_id, kind, source, text, items를 가진 객체여야 한다")
        return res

    passage_id = data.get("passage_id")
    if not isinstance(passage_id, str) or not passage_id.strip():
        err(("passage_id",), "passage_id는 비어 있지 않은 문자열이어야 한다")
    kind = data.get("kind")
    if kind not in ALLOWED_KINDS:
        err(("kind",), f"kind {kind!r}는 허용되지 않는다 (허용: {', '.join(ALLOWED_KINDS)})")
    source = data.get("source", "")
    if not isinstance(source, str):
        err(("source",), "source는 문자열이어야 한다")
    text = data.get("text")
    if not isinstance(text, str) or not text.strip():
        err(("text",), "text는 비어 있지 않은 문자열이어야 한다")
        text = ""
    items = data.get("items")
    if not isinstance(items, list) or not items:
        err(("items",), "items는 하나 이상의 항목 리스트여야 한다")
        items = []

    templates = template_map(db, kind) if kind in ALLOWED_KINDS else {}
    known_tags = {tag for tag, _ in templates}

    clean_items: list[dict] = []
    seen_nos: set[int] = set()
    for i, it in enumerate(items):
        p = ("items", i)
        if not isinstance(it, dict):
            err(p, f"항목 #{i + 1}은 객체여야 한다")
            continue
        no = it.get("no")
        if not isinstance(no, int) or isinstance(no, bool) or no < 1:
            err(p + ("no",), f"항목 #{i + 1}: no는 1 이상의 정수여야 한다")
            continue
        if no in seen_nos:
            err(p + ("no",), f"항목 {no}: no가 중복된다")
            continue
        seen_nos.add(no)
        ok = True
        choice = it.get("choice")
        if not isinstance(choice, str) or not choice.strip():
            err(p + ("choice",), f"항목 {no}: choice는 비어 있지 않은 문자열이어야 한다")
            ok = False
        is_correct = it.get("is_correct")
        if not isinstance(is_correct, bool):
            err(p + ("is_correct",), f"항목 {no}: is_correct는 true/false여야 한다")
            ok = False
        tag = it.get("tag")
        if tag not in known_tags:
            err(p + ("tag",), f"항목 {no}: 등록되지 않은 태그 {tag!r}")
            ok = False
        model_slots = it.get("model_slots")
        if not isinstance(model_slots, dict):
            err(p + ("model_slots",), f"항목 {no}: model_slots는 객체여야 한다")
            ok = False
        elif ok:
            tpl = templates.get((tag, judgement_key(is_correct)))
            if tpl is None:
                err(p + ("tag",), f"항목 {no}: ({tag}, {judgement_key(is_correct)}) 틀이 없다")
                ok = False
            else:
                model_slots = {k: str(v) if v is not None else "" for k, v in model_slots.items()}
                for msg in validate_slots(tpl, model_slots):
                    err(p + ("model_slots",), f"항목 {no}: model_slots — {msg}")
                    ok = False
        explanation = it.get("explanation", "")
        if not isinstance(explanation, str):
            err(p + ("explanation",), f"항목 {no}: explanation은 문자열이어야 한다")
            ok = False
        context = it.get("context")
        if context is not None and (not isinstance(context, str) or f"[[{no}]]" not in context):
            err(p + ("context",), f"항목 {no}: context는 [[{no}]] 마커를 포함한 문자열이어야 한다")
            ok = False
        if ok:
            clean_items.append({
                "no": no, "choice": choice.strip(), "is_correct": is_correct, "tag": tag,
                "model_slots": model_slots, "explanation": explanation.strip(),
                "context": context.strip() if context else None,
            })

    # 마커 ↔ 항목 대응
    if text:
        counts: dict[int, int] = {}
        for m in MARKER.finditer(text):
            counts[int(m.group(1))] = counts.get(int(m.group(1)), 0) + 1
        for no in sorted(seen_nos):
            c = counts.get(no, 0)
            if c == 0:
                err(("text",), f"항목 {no}의 마커 [[{no}]]가 text에 없다")
            elif c > 1:
                err(("text",), f"마커 [[{no}]]가 text에 {c}번 있다 (정확히 한 번이어야 한다)")
        for no in sorted(set(counts) - seen_nos):
            err(("text",), f"마커 [[{no}]]에 해당하는 항목이 없다")

    if res.errors:
        return res

    # 한 문장 안에 마커 2개 이상 → 경고
    choices = {it["no"]: it["choice"] for it in clean_items}
    no_ctx = {it["no"] for it in clean_items if not it["context"]}
    for s in split_sentences(text, choices):
        nos = [int(n) for n in MARKER.findall(s)]
        if len(nos) >= 2 and set(nos) & no_ctx:
            warn(("text",), f"한 문장에 마커 {', '.join(f'[[{n}]]' for n in nos)}가 함께 있다 (필요하면 context로 문장을 지정)")

    res.passage = ParsedPassage(passage_id.strip(), kind, source.strip(), normalize_text(text), sorted(clean_items, key=lambda x: x["no"]))
    return res


# ---------- locked 비교와 적용 ----------

def locked_changes(existing: Passage, new: ParsedPassage) -> tuple[list[str], list[str]]:
    """(거부할 변경, 경고할 변경)"""
    blocking, soft = [], []
    if existing.kind != new.kind:
        blocking.append(f"kind: {existing.kind} → {new.kind}")
    if normalize_text(existing.text) != new.text:
        blocking.append("text가 바뀌었다")
    old = {it.no: it for it in existing.items}
    new_items = {it["no"]: it for it in new.items}
    for no in sorted(set(old) - set(new_items)):
        blocking.append(f"항목 {no}가 삭제되었다")
    for no in sorted(set(new_items) - set(old)):
        blocking.append(f"항목 {no}가 추가되었다")
    for no in sorted(set(old) & set(new_items)):
        o, n = old[no], new_items[no]
        for f in ("choice", "is_correct", "tag"):
            if getattr(o, f) != n[f]:
                blocking.append(f"항목 {no} {f}: {getattr(o, f)!r} → {n[f]!r}")
        if o.explanation != n["explanation"]:
            soft.append(f"항목 {no} explanation 변경")
        if (o.model_slots or {}) != n["model_slots"]:
            soft.append(f"항목 {no} model_slots 변경")
    return blocking, soft


def apply_passage(db: Session, existing: Passage | None, new: ParsedPassage) -> str:
    """검증을 통과한 지문을 DB에 반영한다. 반환: created / updated / unchanged"""
    if existing is None:
        p = Passage(id=new.passage_id, kind=new.kind, source=new.source, text=new.text)
        p.items = [Item(**it) for it in new.items]
        db.add(p)
        return "created"

    before = _snapshot(existing)
    existing.kind, existing.source, existing.text = new.kind, new.source, new.text
    old = {it.no: it for it in existing.items}
    new_nos = {it["no"] for it in new.items}
    for no, it in old.items():
        if no not in new_nos:
            existing.items.remove(it)
    for data in new.items:
        it = old.get(data["no"])
        if it is None:
            existing.items.append(Item(**data))
        else:
            for k, v in data.items():
                setattr(it, k, v)
    return "unchanged" if _snapshot(existing) == before else "updated"


def _snapshot(p: Passage):
    return (
        p.kind, p.source, p.text,
        tuple(sorted((it.no, it.choice, it.is_correct, it.tag, repr(sorted((it.model_slots or {}).items())), it.explanation, it.context) for it in p.items)),
    )
