"""guide.md 16절 수용 기준."""

import json
from datetime import timedelta

import yaml
from sqlalchemy import update

from app import yamlutil
from app.db import SessionLocal
from app.models import AuthSession, User
from app.timeutil import utcnow
from tests.conftest import SAMPLE, answer_all, bearer, upload

FORBIDDEN_KEYS = {"is_correct", "model_slots", "explanation", "correct", "judgement_ok", "tag_ok", "slots_check", "diagnosis"}


def _keys(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield k
            yield from _keys(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _keys(v)


def _public_strings(sample: dict) -> str:
    from app.templates_service import DEFAULT_TEMPLATES_PATH

    options = [o for t in yamlutil.load(DEFAULT_TEMPLATES_PATH.read_text(encoding="utf-8")) for spec in t["slots"].values() if isinstance(spec, list) for o in spec]
    choices = [it["choice"] for it in sample["items"]]
    return " ".join(sample["text"].split()) + "\n" + "\n".join(options + choices)


def _assert_no_answer_leak(resp, sample: dict):
    raw = resp.text
    body = resp.json()
    assert not (set(_keys(body)) & FORBIDDEN_KEYS), f"정답 필드 노출: {set(_keys(body)) & FORBIDDEN_KEYS}"
    public = _public_strings(sample)
    for it in sample["items"]:
        assert it["explanation"] not in raw
        for v in it["model_slots"].values():
            # 지문 원문이나 공개된 선택형 보기에 있는 값은 원래 보이는 값이라 제외
            if str(v) not in public:
                assert str(v) not in raw, f"model_slots 값 노출: {v}"
    if isinstance(body, dict):
        for item in body.get("items", []):
            assert "tag" not in item, "항목 정답 태그 노출"


# 1
def test_no_answer_leak_before_submit(client, world):
    sample = yamlutil.load(SAMPLE)
    h, aid = world.h("kim"), world.aid("kim")
    responses = [
        client.get("/student/assignments", headers=h),
        client.get(f"/student/assignments/{aid}", headers=h),
        client.get("/templates?kind=grammar", headers=h),
        client.get("/me", headers=h),
    ]
    detail = responses[1].json()
    first = detail["items"][0]
    responses.append(client.put(f"/student/assignments/{aid}/answers/{first['id']}", headers=h, json={
        "judgement": True, "tag": "병렬", "slots": {"conj": "and", "pair": "x", "word": "y"}, "duration_sec": 5,
    }))
    responses.append(client.post(f"/student/assignments/{aid}/submit", headers=h))  # 미완료로 실패
    responses.append(client.get(f"/student/assignments/{aid}", headers=h))  # 저장 후 재조회
    responses.append(client.get(f"/student/assignments/{aid}/result", headers=h))  # 제출 전 → 거부
    for r in responses:
        _assert_no_answer_leak(r, sample)
    assert responses[-1].status_code == 403


# 2
def test_other_students_assignment_is_404(client, world):
    kim, lee_aid = world.h("kim"), world.aid("lee")
    lee_detail = client.get(f"/student/assignments/{lee_aid}", headers=world.h("lee")).json()
    item_id = lee_detail["items"][0]["id"]
    assert client.get(f"/student/assignments/{lee_aid}", headers=kim).status_code == 404
    assert client.get(f"/student/assignments/{lee_aid}/result", headers=kim).status_code == 404
    assert client.post(f"/student/assignments/{lee_aid}/submit", headers=kim).status_code == 404
    r = client.put(f"/student/assignments/{lee_aid}/answers/{item_id}", headers=kim, json={
        "judgement": True, "tag": "병렬", "slots": {"conj": "a", "pair": "b", "word": "c"},
    })
    assert r.status_code == 404
    assert client.get("/student/assignments/999999", headers=kim).status_code == 404


# 3
def test_submit_requires_completion_and_locks_answers(client, world):
    h, aid = world.h("kim"), world.aid("kim")
    detail = answer_all(client, h, aid, skip={3, 5})
    r = client.post(f"/student/assignments/{aid}/submit", headers=h)
    assert r.status_code == 400
    missing = {it["id"] for it in detail["items"] if it["no"] in (3, 5)}
    assert set(r.json()["incomplete_item_ids"]) == missing

    answer_all(client, h, aid)
    r = client.post(f"/student/assignments/{aid}/submit", headers=h)
    assert r.status_code == 200, r.text
    assert r.json()["is_late"] is False

    item_id = detail["items"][0]["id"]
    r = client.put(f"/student/assignments/{aid}/answers/{item_id}", headers=h, json={
        "judgement": False, "tag": "병렬", "slots": {"conj": "a", "pair": "b", "current": "c", "fixed": "d"},
    })
    assert r.status_code == 409
    assert client.post(f"/student/assignments/{aid}/submit", headers=h).status_code == 409

    res = client.get(f"/student/assignments/{aid}/result", headers=h)
    assert res.status_code == 200
    items = res.json()["passages"][0]["items"]
    assert len(items) == 5
    assert all(it["judgement_ok"] and it["tag_ok"] for it in items)
    assert "diagnosis" not in res.text  # 진단 라벨은 선생님 화면에서만


# 4
def test_rotate_link_invalidates_old_link(client, world, teacher):
    s = world.students["kim"]
    r = client.post(f"/teacher/students/{s['id']}/rotate-link", headers=teacher)
    assert r.status_code == 200
    new = r.json()["link_token"]
    assert client.post("/auth/link-login", json={"token": s["link"]}).status_code == 401
    r = client.post("/auth/link-login", json={"token": new})
    assert r.status_code == 200
    assert r.json()["user"]["id"] == s["id"]
    # 이미 로그인된 기기는 유지된다
    assert client.get("/me", headers=s["headers"]).status_code == 200


def test_revoke_sessions(client, world, teacher):
    s = world.students["kim"]
    r = client.post(f"/teacher/students/{s['id']}/revoke-sessions", headers=teacher)
    assert r.status_code == 200 and r.json()["revoked"] >= 1
    assert client.get("/me", headers=s["headers"]).status_code == 401


# 5
def test_student_token_cannot_call_teacher_api(client, world):
    h = world.h("kim")
    for method, path in [
        ("get", "/teacher/students"), ("get", "/teacher/passages"), ("get", "/teacher/overview"),
        ("get", "/teacher/stats/tags"), ("get", f"/teacher/assignments/{world.aid('kim')}"),
        ("post", "/teacher/question-sets"), ("post", f"/teacher/students/{world.students['lee']['id']}/rotate-link"),
    ]:
        r = getattr(client, method)(path, headers=h)
        assert r.status_code == 403, (path, r.status_code)
    assert client.get("/teacher/students").status_code == 401


# 6
def test_pin_lockout_and_unlock(client, world):
    for _ in range(5):
        assert client.post("/auth/code-login", json={"code": "kim", "pin": "0000"}).status_code == 401
    # 잠김: 맞는 PIN이어도 거부
    assert client.post("/auth/code-login", json={"code": "kim", "pin": "1234"}).status_code == 423
    with SessionLocal() as db:
        db.execute(update(User).where(User.login_code == "kim").values(locked_until=utcnow() - timedelta(seconds=1)))
        db.commit()
    r = client.post("/auth/code-login", json={"code": "kim", "pin": "1234"})
    assert r.status_code == 200
    assert r.json()["user"]["role"] == "student"


# 7
def _broken(**changes) -> str:
    data = yamlutil.load(SAMPLE)
    for path, value in changes.items():
        target = data
        keys = path.split("__")
        for k in keys[:-1]:
            target = target[int(k)] if k.isdigit() else target[k]
        last = keys[-1]
        target[int(last) if last.isdigit() else last] = value
    return yaml.safe_dump(data, allow_unicode=True, sort_keys=False)


def test_upload_validation_errors(client, teacher):
    cases = {
        "marker.yaml": (_broken(text=yamlutil.load(SAMPLE)["text"].replace("[[5]]", "")), "마커 [[5]]"),
        "extra_marker.yaml": (_broken(text=yamlutil.load(SAMPLE)["text"] + " [[6]]"), "[[6]]에 해당하는 항목이 없다"),
        "tag.yaml": (_broken(items__0__tag="없는태그"), "등록되지 않은 태그"),
        "slot.yaml": (_broken(items__2__model_slots={"subject": "x", "number": "단수", "current": "are", "wrong_slot": "is"}), "슬롯"),
        "choice.yaml": (_broken(items__2__model_slots={"subject": "x", "number": "셋", "current": "are", "fixed": "is"}), "보기"),
    }
    r = upload(client, teacher, {name: content for name, (content, _) in cases.items()})
    assert r.status_code == 422
    body = r.json()
    assert body["saved"] is False
    by_file = {res["filename"]: res for res in body["results"]}
    for name, (_, needle) in cases.items():
        res = by_file[name]
        assert res["status"] == "error", name
        assert any(needle in e["message"] for e in res["errors"]), (name, res["errors"])
        assert all(e["line"] for e in res["errors"]), f"{name}: 줄 번호 없음"
    assert client.get("/teacher/passages", headers=teacher).json() == []


def test_upload_is_all_or_nothing(client, teacher):
    r = upload(client, teacher, {"ok.yaml": SAMPLE, "bad.yaml": _broken(passage_id="other", items__0__tag="없는태그")})
    assert r.status_code == 422
    assert {res["filename"]: res["status"] for res in r.json()["results"]} == {"ok.yaml": "skipped", "bad.yaml": "error"}
    assert client.get("/teacher/passages", headers=teacher).json() == []


# 8
def test_locked_passage_changes(client, world, teacher):
    passages = client.get("/teacher/passages", headers=teacher).json()
    assert passages[0]["locked"] is True

    r = upload(client, teacher, {"a.yaml": _broken(items__0__is_correct=False, items__0__model_slots={"role": "접속사", "current": "that", "fixed": "what"})})
    assert r.status_code == 409
    assert any("is_correct" in c for c in r.json()["results"][0]["changes"])

    r = upload(client, teacher, {"a.yaml": _broken(items__1__tag="준동사", items__1__model_slots={"trigger": "x", "form": "to부정사", "word": "Allow"})})
    assert r.status_code == 409
    assert any("tag" in c for c in r.json()["results"][0]["changes"])

    r = upload(client, teacher, {"a.yaml": _broken(items__0__explanation="오탈자를 고친 해설")})
    assert r.status_code == 200, r.text
    res = r.json()["results"][0]
    assert res["status"] == "updated"
    assert res["warnings"]


def test_unlocked_passage_upsert(client, teacher):
    assert upload(client, teacher, {"a.yaml": SAMPLE}).json()["results"][0]["status"] == "created"
    assert upload(client, teacher, {"a.yaml": SAMPLE}).json()["results"][0]["status"] == "unchanged"
    r = upload(client, teacher, {"a.yaml": _broken(items__0__is_correct=False, items__0__model_slots={"role": "접속사", "current": "that", "fixed": "what"})})
    assert r.status_code == 200
    assert r.json()["results"][0]["status"] == "updated"


# 9
def test_relogin_after_session_expiry_keeps_answers(client, world):
    s = world.students["kim"]
    aid = s["assignment"]
    answer_all(client, s["headers"], aid, skip={4, 5})
    with SessionLocal() as db:
        db.execute(update(AuthSession).values(expires_at=utcnow() - timedelta(minutes=1)))
        db.commit()
    assert client.get(f"/student/assignments/{aid}", headers=s["headers"]).status_code == 401
    r = client.post("/auth/link-login", json={"token": s["link"]})
    assert r.status_code == 200
    detail = client.get(f"/student/assignments/{aid}", headers=bearer(r.json()["token"])).json()
    assert detail["answered"] == 3
    assert len(detail["answers"]) == 3


# 선생님 화면 데이터
def test_teacher_detail_overview_review_stats(client, world, teacher):
    h, aid = world.h("kim"), world.aid("kim")
    detail = client.get(f"/student/assignments/{aid}", headers=h).json()
    for it in detail["items"]:
        ans = {
            "judgement": True, "tag": "준동사", "slots": {"trigger": "x", "form": "동명사", "word": it["choice"]},
        } if it["no"] == 3 else None
        from tests.conftest import MODEL_ANSWERS
        body = ans or MODEL_ANSWERS[it["no"]]
        client.put(f"/student/assignments/{aid}/answers/{it['id']}", headers=h, json={**body, "duration_sec": 99999})
    assert client.post(f"/student/assignments/{aid}/submit", headers=h).status_code == 200

    d = client.get(f"/teacher/assignments/{aid}", headers=teacher).json()
    items = {it["no"]: it for it in d["passages"][0]["items"]}
    assert items[3]["answer"]["diagnosis"] == "개념 미습득"
    assert items[1]["answer"]["diagnosis"] == "이해"
    assert items[1]["answer"]["duration_sec"] == 600  # 저장당 상한
    assert d["daily_saves"][0]["count"] == 5

    r = client.put(f"/teacher/answers/{items[3]['answer']['answer_id']}/review", headers=teacher, json={"status": "needs_work"})
    assert r.status_code == 200
    d = client.get(f"/teacher/assignments/{aid}", headers=teacher).json()
    assert {it["no"]: it for it in d["passages"][0]["items"]}[3]["answer"]["review_status"] == "needs_work"

    ov = client.get("/teacher/overview", headers=teacher).json()
    kim = next(s for s in ov["students"] if s["name"] == "kim")
    cells = [c for week in kim["cells"].values() for c in week]
    assert cells and cells[0]["status"] == "done"

    stats = client.get("/teacher/stats/tags", headers=teacher).json()["tags"]
    su = next(t for t in stats if t["tag"] == "수일치")
    assert su["count"] == 1 and su["judgement_error_rate"] == 1.0 and su["tag_mismatch_rate"] == 1.0
    assert json.dumps(stats)  # 직렬화 가능


def test_overdue_and_late_submission(client, world, teacher):
    s = world.students["kim"]
    with SessionLocal() as db:
        from app.models import Assignment
        db.execute(update(Assignment).where(Assignment.id == s["assignment"]).values(due_at=utcnow() - timedelta(days=2)))
        db.commit()
    ov = client.get("/teacher/overview", headers=teacher).json()
    assert [o["assignment_id"] for o in ov["overdue"]] == [s["assignment"]]
    assert ov["overdue"][0]["days_overdue"] >= 1
    answer_all(client, s["headers"], s["assignment"])
    r = client.post(f"/student/assignments/{s['assignment']}/submit", headers=s["headers"])
    assert r.json()["is_late"] is True
    lst = client.get("/student/assignments", headers=s["headers"]).json()
    assert lst[0]["status"] == "late_done"
