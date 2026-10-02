# 문법 숙제 웹 — 구현 가이드 (guide.md)

## 0. 이 문서의 사용법

- Claude Code는 이 문서를 구현 기준으로 삼는다.
- 문서와 충돌하거나 모호한 부분은 임의로 정하지 말고, 구현 전에 질문한다.
- `[초안]` 표시는 선생님이 나중에 고칠 데이터(태그, 문장 틀)다. 코드에 하드코딩하지 말고 `data/` 아래 YAML에서 읽어 DB에 적재한다.

## 1. 목적

과외 학생이 노트로 하던 "선지별로 왜 맞고 틀린지 근거 쓰기" 숙제를 웹에서 하게 하고, 선생님이 수행 여부와 내용을 확인한다.

- 핵심 가치는 채점이 아니라 **근거 작성을 강제하고 기록으로 남기는 것**이다.
- 시작은 영어 어법(문법)이고, 이후 리딩과 리스닝으로 확장할 수 있다.
- 사용자: 선생님 1명, 학생 수 명~수십 명. 학생은 주로 폰(카카오톡 인앱 브라우저)으로 접속한다.

## 2. 확정된 결정

| 항목 | 결정 |
|---|---|
| 형태 | 웹. 설치 없이 링크로 접속, **모바일 우선** UI |
| 프론트 | React + Vite + TypeScript, 독립 배포(Cloudflare Pages) |
| 서버 | FastAPI, 독립 배포(Render 무료) |
| DB | PostgreSQL(Neon 무료) |
| 비용 | 전부 무료 플랜. 유료 서비스에 의존하는 설계 금지 |
| 인증 | DB 저장 세션 토큰(`Authorization: Bearer`) + 개인 로그인 링크(재사용형) + 코드/PIN 폴백 |
| 권한 | 학생/선생님을 한 앱에서 role로 분기, **권한 검사는 항상 서버에서** |
| 풀이 단위 | 지문의 밑줄 항목 1개. 항목을 섞어서 하나씩 제시, 지문 전체 보기 버튼 상시 제공 |
| 근거 입력 | 판단(맞다/틀리다) → 태그 선택 → 태그별 문장 틀의 빈칸 채우기 |
| 공개 시점 | **제출 후에** 정답, 정답 태그, 모범 해설 공개 |
| 숙제 분량 | 주 1회 배정, 지문 4개, 항목 20개 기준. 며칠에 나눠 풀 수 있음 |
| 마감 후 | 풀 수 있으나 "지각"으로 기록 |

## 3. 레포 구조 (모노레포, private 레포)

```
grammar-homework/
├─ guide.md
├─ frontend/            # React + Vite + TS
├─ backend/             # FastAPI
│  ├─ app/
│  ├─ alembic/
│  ├─ tests/
│  └─ scripts/          # create_teacher.py, backup.sh
└─ data/
   ├─ templates.yaml    # 근거 문장 틀 [초안]
   └─ passages/         # 지문 YAML
```

- 레포는 반드시 private. `data/`에 정답과 해설이 들어 있다.
- `.env`와 백업 파일은 `.gitignore`에 넣는다.

## 4. 기술 스택

- **Backend**: Python 3.11+, FastAPI, SQLAlchemy 2.x, Alembic, Pydantic v2, psycopg 3, PyYAML, pytest
- **Frontend**: React, Vite, TypeScript, React Router. 라이브러리는 최소화한다(상태관리 라이브러리 불필요, fetch 래퍼 하나).
- 시간은 UTC로 저장하고 화면에는 KST(Asia/Seoul)로 표시한다. 주(week)는 월요일 시작, KST 기준이다.

## 5. 데이터 모델

| 테이블 | 주요 필드 |
|---|---|
| users | id, role(`student`/`teacher`), name, login_code(unique), pin_hash(학생), password_hash(선생님), link_token_hash(학생, nullable), link_rotated_at, failed_count, locked_until, is_active, created_at |
| sessions | id, user_id, token_hash, created_at, last_used_at, expires_at, user_agent, revoked_at |
| passages | id(= passage_id 문자열), kind, source, text, locked(bool), created_at |
| items | id, passage_id, no, choice, is_correct, tag, model_slots(JSON), explanation, context(nullable) |
| templates | id, kind, tag, judgement(`wrong`/`right`), body, slots(JSON). unique(kind, tag, judgement) |
| question_sets | id, title, mode(`shuffle`, 나중에 `passage`), created_at |
| question_set_passages | set_id, passage_id, order |
| assignments | id, student_id, set_id, assigned_at, due_at, submitted_at(nullable), is_late, item_order(JSON: item id 목록, 배정 시 1회 셔플) |
| answers | id, assignment_id, item_id, judgement(bool: 문법상 맞다=true), tag, slots(JSON), saved_at, duration_sec(누적), judgement_ok, tag_ok, slots_check(JSON). unique(assignment_id, item_id) |
| reviews | id, answer_id, status(`ok`/`needs_work`), comment(2차), reviewed_at |

- `judgement_ok`, `tag_ok`, `slots_check`은 **제출 시점에 서버가 계산**해서 저장한다.
- 세트가 한 번이라도 배정되면 그 세트의 지문은 `locked = true`가 된다.

## 6. 문제 데이터

### 6.1 지문 YAML 형식

- 지문 1개 = 파일 1개. 업로드는 여러 파일을 한 번에 받을 수 있다.
- `text`의 `[[번호]]`는 밑줄의 위치이고, 화면에서는 해당 항목의 `choice` 값을 밑줄로 렌더링한다(원문자 ①~⑤ 번호 포함).
- 예시는 부록 참고.

필드

- 지문: `passage_id`, `kind`(MVP는 `grammar`만), `source`, `text`, `items[]`
- 항목: `no`, `choice`, `is_correct`, `tag`, `model_slots`, `explanation`, 선택적으로 `context`(문장 자동 분리 덮어쓰기)

### 6.2 업로드 검증 규칙 (실패 시 줄 단위로 오류 보고)

1. `passage_id`는 비어 있지 않은 문자열, `kind`는 허용 목록 안에 있어야 한다.
2. `text`에 `[[n]]` 마커가 각 `no`마다 정확히 한 번 있어야 하고, 마커가 없는 항목이나 항목이 없는 마커가 있으면 오류다.
3. `tag`는 해당 `kind`에 등록된 태그여야 한다.
4. `model_slots` 키는 해당 (kind, tag, judgement) 틀의 슬롯 이름과 일치해야 하고, 선택형 슬롯 값은 보기 안에 있어야 한다. `judgement`는 `is_correct`로 결정한다(true면 `right`, false면 `wrong`).
5. 한 문장 안에 마커가 2개 이상이면 경고한다(`context`로 해결 가능).

### 6.3 문장 분리

- 학생 화면에 보여줄 `sentence`는 서버가 `text`를 문장 단위로 잘라서 만든다(마침표/물음표/느낌표 뒤 공백 + 대문자 기준, 약어 오분리 방지).
- 항목에 `context`가 있으면 그것을 우선 사용한다.
- 문장 보기에서는 해당 항목의 마커만 밑줄로 표시하고, 같은 문장의 다른 마커는 `choice` 텍스트만 일반 글자로 보여준다.

### 6.4 수정 제한 (locked 지문)

배정된 적 있는 지문을 다시 업로드할 때:

- `is_correct`, `tag`, `choice`, `text`가 바뀌면 **409로 거부**하고 변경 목록을 알려준다(이미 계산된 정오가 소급해서 달라지기 때문).
- `explanation`, `model_slots`의 변경은 허용하되 경고를 표시한다(오탈자 수정용).
- 같은 `passage_id`로 locked가 아닌 지문을 올리면 전체 갱신(upsert)한다.

## 7. 근거 문장 틀 (templates) [초안]

### 7.1 태그 목록 [초안]

수일치 / 관계사 / 접속사·명사절 / 준동사 / 분사 / 본동사 유무 / 대명사 / 형용사·부사 / 병렬 / 태(능동·수동)

- 학생에게는 항상 **전체 태그를 고정된 순서로** 보여준다(지문별로 줄이지 않는다).

### 7.2 틀 정의 (`data/templates.yaml`)

슬롯 값이 **리스트이면 선택형**, `text`이면 입력형이다.

```yaml
- kind: grammar
  tag: 수일치
  judgement: wrong
  body: "이 문장의 주어는 {subject}이고 {number}이므로, 동사는 {current}가 아니라 {fixed}가 되어야 한다."
  slots:
    subject: text
    number: [단수, 복수]
    current: text
    fixed: text
```

### 7.3 태그별 틀 [초안]

| 태그 | 틀리다(wrong) | 맞다(right) |
|---|---|---|
| 수일치 | 이 문장의 주어는 {subject}이고 {number}이므로, 동사는 {current}가 아니라 {fixed}가 되어야 한다. | 이 문장의 주어는 {subject}이고 {number}이므로, 동사 {verb}가 맞다. |
| 관계사 | 밑줄 뒤의 절이 {completeness}한 문장이므로, {current}가 아니라 {fixed}가 와야 한다. | 밑줄 뒤의 절이 {completeness}한 문장이므로, {word}가 맞다. |
| 접속사·명사절 | 이 자리에는 {role}이(가) 필요하므로, {current}가 아니라 {fixed}가 되어야 한다. | 이 자리에는 {role}이(가) 필요하므로, {word}가 맞다. |
| 준동사 | {trigger}와(과) 연결되는 형태는 {form}이므로, {current}가 아니라 {fixed}가 되어야 한다. | {trigger}와(과) 연결되는 형태는 {form}이므로, {word}가 맞다. |
| 분사 | 수식받는 {noun}과(와) 분사의 관계가 {relation}이므로, {current}가 아니라 {fixed}가 되어야 한다. | 수식받는 {noun}과(와) 분사의 관계가 {relation}이므로, {word}가 맞다. |
| 본동사 유무 | 이 문장의 주어는 {subject}인데 본동사가 {exists}. 따라서 {current}는 {fixed}가 되어야 한다. | 이 문장의 주어는 {subject}이고 본동사는 {verb}이므로 맞다. |
| 대명사 | {current}는 {referent}을(를) 가리키고 {number}이므로, {fixed}가 되어야 한다. | {word}는 {referent}을(를) 가리키고 {number}이므로 맞다. |
| 형용사·부사 | {current}는 {target}을(를) 꾸미는 말인데 그 자리는 {role}이 오는 자리이므로, {fixed}가 되어야 한다. | {word}는 {target}을(를) 꾸미는 말이고 그 자리는 {role}이 오는 자리이므로 맞다. |
| 병렬 | {conj} 앞뒤로 {pair}이(가) 병렬되므로, {current}가 아니라 {fixed}가 되어야 한다. | {conj} 앞뒤로 {pair}이(가) 병렬되므로, {word}가 맞다. |
| 태(능동·수동) | 주어 {subject}와 동사의 관계가 {relation}이므로, {current}가 아니라 {fixed}가 되어야 한다. | 주어 {subject}와 동사의 관계가 {relation}이므로, {word}가 맞다. |

슬롯 타입

- 입력형(`text`): subject, verb, current, fixed, word, trigger, noun, referent, target, conj, pair
- 선택형 보기
  - number: [단수, 복수]
  - completeness: [완전, 불완전]
  - relation: [능동, 수동]
  - exists: [있다, 없다]
  - form: [to부정사, 동명사, 원형부정사]
  - role(접속사·명사절): [접속사, 전치사, 명사절을 이끄는 접속사, 의문사]
  - role(형용사·부사): [형용사, 부사]

## 8. 인증과 세션

### 8.1 로그인 수단

1. **개인 로그인 링크 (학생 기본)**
   - 형식: `https://<프론트 주소>/login#<토큰>`. 토큰은 `#` 뒤에 둔다(서버 로그와 Referer에 남지 않음).
   - 프론트가 `#` 뒤 값을 읽어 `POST /auth/link-login`으로 교환하고, 성공하면 주소창에서 토큰을 지운다.
   - **로그인은 GET으로 처리하지 않는다**(메신저 링크 미리보기에 링크가 소모되는 것을 막기 위함).
   - 링크는 **재사용 가능**하고, 학생당 유효한 링크는 항상 1개다.
2. **학생 코드 + PIN (폴백)**: PIN은 4~6자리. 5회 연속 실패 시 5분 잠금(`failed_count`, `locked_until`).
3. **선생님**: 코드 + 비밀번호. 학생 링크와 무관하게 별도로 로그인한다.

### 8.2 세션 토큰

- 토큰은 `secrets.token_urlsafe(32)`로 생성하고, DB에는 SHA-256 해시만 저장한다. 링크 토큰도 같은 방식이다.
- 만료는 **사용할 때마다 연장(sliding)**: 학생 90일, 선생님 30일. 설정값은 환경변수로 뺀다.
- 프론트는 토큰을 localStorage에 저장하고 요청마다 `Authorization: Bearer`로 보낸다. 쿠키는 쓰지 않는다.
- 비밀번호와 PIN은 argon2 또는 bcrypt로 해시한다.

### 8.3 유출 대응 (선생님 화면)

- **링크 재발급**: 기존 링크를 무효화하고 새 링크를 발급한다. 평문 토큰은 발급 응답에서 한 번만 보여주고(복사 버튼 제공), 이미 로그인된 기기는 유지된다.
- **모든 세션 종료**: 해당 학생의 모든 세션을 `revoked_at` 처리한다.
- 학생별 활성 세션 목록(기기 정보, 마지막 사용 시각)을 보여준다.

### 8.4 세션 만료 시 입력 보존

- 요청이 401이면 작성 중이던 입력을 localStorage(`draft:{assignmentId}:{itemId}`)에 임시 보관하고 로그인 화면으로 보낸다. 재로그인 후 해당 항목으로 복귀해 입력을 복원한다.

## 9. API

모든 경로에서 role 검사는 서버 의존성(dependency)으로 처리한다. 학생은 **본인 배정만** 접근할 수 있고, 남의 리소스는 404로 응답한다.

### 공통

| 메서드 | 경로 | 설명 |
|---|---|---|
| GET | `/health` | 서버와 DB를 함께 깨우는 용도. DB에 `SELECT 1` 실행. 인증 불필요 |
| POST | `/auth/link-login` | `{token}` → 세션 토큰, 사용자 정보 |
| POST | `/auth/code-login` | `{code, pin}` |
| POST | `/auth/teacher-login` | `{code, password}` |
| POST | `/auth/logout` | 현재 세션 폐기 |
| GET | `/me` | 현재 사용자(role 포함) |
| GET | `/templates?kind=grammar` | 태그 목록, 틀, 슬롯 정의. **정답 정보 없음** |

### 학생 (role = student)

| 메서드 | 경로 | 설명 |
|---|---|---|
| GET | `/student/assignments` | 내 숙제 목록(진행률, 마감, 상태) |
| GET | `/student/assignments/{id}` | 숙제 정보, `item_order`, 진행 상태, 지문 텍스트(마커 포함), 항목별 `choice`와 `sentence`. **`is_correct`, 정답 태그, `model_slots`, `explanation` 제외** |
| PUT | `/student/assignments/{id}/answers/{item_id}` | `{judgement, tag, slots, duration_sec}` 저장(upsert). 제출 후에는 거부. `duration_sec`는 서버에서 누적하고 저장당 상한(600초)을 둔다 |
| POST | `/student/assignments/{id}/submit` | 모든 항목이 완료됐는지 검증(미완료 항목 목록 반환) → 잠금 → 정오 계산 → `submitted_at`, `is_late` 기록 |
| GET | `/student/assignments/{id}/result` | **제출 후에만**. 항목별 내 답, 정답 판단, 정답 태그, `model_slots`, `explanation` |

### 선생님 (role = teacher)

| 메서드 | 경로 | 설명 |
|---|---|---|
| GET/POST | `/teacher/students` | 목록/추가(이름, 코드, PIN) |
| GET | `/teacher/students/{id}` | 상세, 활성 세션 목록 |
| POST | `/teacher/students/{id}/rotate-link` | 링크 재발급(평문 토큰 1회 반환) |
| POST | `/teacher/students/{id}/revoke-sessions` | 모든 세션 종료 |
| POST | `/teacher/passages/upload` | YAML 여러 개. 검증 결과를 파일별로 반환 |
| GET | `/teacher/passages` | 지문 목록(locked 표시) |
| GET/POST | `/teacher/question-sets` | 세트 목록/생성(지문 선택, 순서) |
| POST | `/teacher/assignments` | `{student_ids, set_id, due_at}` |
| GET | `/teacher/overview?week=` | 학생 × 주차 표 + 마감 지난 미제출 목록 |
| GET | `/teacher/assignments/{id}` | 항목별 학생 답, 모범, 진단, 리뷰 상태, 저장 시각, 소요 시간 |
| PUT | `/teacher/answers/{answer_id}/review` | `{status}` |
| GET | `/teacher/stats/tags` | 태그별 판단 오류율, 태그 불일치율(학생 필터) |

## 10. 학생 화면

1. **홈**: 이번 주 숙제 카드(진행률, 마감일, 상태). 지난 미완료 숙제도 위쪽에 표시한다(지각 표시).
2. **풀이**(항목 하나씩, 이어 풀기는 첫 미완료 항목부터)
   - 해당 문장을 보여주고 밑줄 항목을 강조한다. "지문 전체 보기" 버튼은 항상 제공한다.
   - 순서: 맞다/틀리다 선택 → 태그 선택(전체 목록) → 틀이 나타나고 빈칸 채우기(선택형은 드롭다운, 입력형은 입력칸)
   - 모든 슬롯이 채워져야 "다음"이 활성화되고, 다음으로 넘어갈 때 서버에 저장한다.
   - 이전 항목으로 돌아가 수정할 수 있다(제출 전까지).
   - 항목별 체류 시간은 화면이 보이는 동안만 측정한다(`visibilitychange` 사용).
3. **제출 확인**: 미완료 항목이 있으면 목록으로 이동시킨다. 제출하면 되돌릴 수 없다는 안내를 보여준다.
4. **결과**: 지문 단위로 묶어서 항목별로 내 근거(완성된 문장)와 모범 근거를 나란히 보여준다. 정답 판단, 정답 태그, 해설을 표시하고 질책성 문구는 쓰지 않는다.
5. **로그인 화면**: 링크로 들어오면 자동 로그인. 링크가 무효면 "링크가 만료되었습니다. 선생님께 새 링크를 요청하세요"와 코드/PIN 입력을 보여준다.
6. 카카오톡 인앱 브라우저에서 동작해야 한다(모바일 우선, 작은 화면에서 입력 편의 확보).

### 완성 문장 렌더링

- 틀의 `{slot}`을 학생 입력값으로 치환해서 하나의 문장으로 보여준다.
- 치환된 값은 강조 표시한다. 선생님 화면에서는 모범 값을 나란히 보여준다.

## 11. 선생님 화면

1. **홈**: 맨 위에 "마감 지난 미제출"(학생, 숙제, 지난 일수). 아래에 학생 × 주차 표. 칸 상태는 미시작 / 진행 중 / 완료 / 지각 완료 / 미제출(마감 후) 중 하나이고, 제출 시각을 함께 표시한다. 칸을 누르면 상세로 이동한다.
2. **숙제 상세**(학생 × 배정)
   - 지문별로 항목 5개를 보여준다. 항목마다 학생의 판단, 태그, 완성 문장과 모범(정답 판단, 정답 태그, 모범 문장, 해설)을 나란히 둔다.
   - 진단 라벨, 저장 시각, 소요 시간을 표시하고 "적절 / 보완 필요" 버튼을 둔다.
   - 상단 요약: 시작 시각, 제출 시각, 일자별 저장 건수(몰아서 풀었는지, 나눠서 풀었는지 확인).
3. **학생 관리**: 학생 추가, 로그인 링크 복사, 링크 재발급, 모든 세션 종료, 세션 목록
4. **문제 관리**: YAML 업로드(검증 결과 표시), 지문 목록(locked 표시), 세트 만들기, 배정(학생 다중 선택, 마감일)
5. **통계**: 태그별 판단 오류율, 태그 불일치율. MVP는 전체 기간과 학생 필터만 지원한다.

## 12. 채점과 진단

- `judgement_ok` = 학생 판단 == `is_correct`
- `tag_ok` = 학생이 고른 태그 == 항목의 `tag`
- `slots_check` = 선택형 슬롯만 `model_slots`와 비교한 슬롯별 일치 여부
- 입력형 슬롯은 자동 판정하지 않는다. 학생 입력과 모범 값을 나란히 보여주고 선생님이 확인한다.
- 진단 라벨은 **선생님 화면에서만** 표시하고, 학생에게는 정오와 정답 태그만 공개한다.

| judgement_ok | tag_ok | 라벨 |
|---|---|---|
| ✓ | ✓ | 이해 |
| ✓ | ✗ | 찍기 의심 / 개념 오인 |
| ✗ | ✓ | 적용 실패 |
| ✗ | ✗ | 개념 미습득 |

## 13. 보안 규칙

1. 학생용 API 응답에는 제출 전에 `is_correct`, 정답 태그, `model_slots`, `explanation`이 **어떤 경로로도** 포함되지 않아야 한다.
2. 학생은 본인 배정만 접근할 수 있다. 다른 학생의 리소스는 404로 응답한다.
3. 제출 후에는 답을 수정할 수 없다(서버에서 거부).
4. 지문 텍스트를 HTML로 직접 렌더링하지 않는다(`dangerouslySetInnerHTML` 금지). 마커는 JS에서 파싱해 React 요소로 만든다. 외부 스크립트는 넣지 않는다.
5. CORS 허용 주소는 환경변수(`CORS_ORIGINS`, 쉼표 구분)로 지정한다. 토큰은 헤더로 보내므로 `allow_credentials`는 끈다. 로컬 개발 주소와 배포 주소를 함께 넣을 수 있게 한다.
6. 비밀값(`DATABASE_URL`, 선생님 초기 비밀번호 등)은 환경변수로만 다룬다. 프론트 환경변수에는 `VITE_API_URL` 같은 공개 가능한 값만 둔다.
7. 선생님 계정은 `scripts/create_teacher.py`로만 생성한다(회원가입 API 없음).

## 14. 배포와 운영

### 구성

| 구성요소 | 서비스 | 설정 |
|---|---|---|
| 프론트 | Cloudflare Pages | 루트 `frontend`, 빌드 `npm run build`, 출력 `dist`, SPA 라우팅용 `public/_redirects`에 `/* /index.html 200` |
| 서버 | Render 무료 웹 서비스 | 루트 `backend`, 빌드 `pip install -r requirements.txt`, 시작 `alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT` |
| DB | Neon 무료 | SSL 필수. `DATABASE_URL`을 Render 환경변수에 입력 |

- 무료 플랜의 한도와 정책은 자주 바뀐다. 배포 시점에 각 서비스의 공식 가격 페이지를 다시 확인한다.
- DB 접속은 `DATABASE_URL` 하나로만 의존해서 다른 호스트로 옮기기 쉽게 한다.

### 환경변수

- Backend: `DATABASE_URL`, `CORS_ORIGINS`, `SESSION_TTL_STUDENT_DAYS`(기본 90), `SESSION_TTL_TEACHER_DAYS`(기본 30), `APP_ENV`
- Frontend: `VITE_API_URL`

### 무료 환경 대응

1. 서버와 DB는 유휴 시 잠들 수 있고, 첫 요청에 재기동 시간(서버는 최대 1분 안팎)이 걸린다.
   - 프론트는 앱이 열릴 때 즉시 `GET /health`를 호출한다.
   - 2초 안에 응답이 없으면 "서버 준비 중…" 안내를 표시하고, 응답이 올 때까지 백오프로 재시도한다(최대 약 90초).
   - 서버에 외부 핑을 보내 계속 깨워 두는 기능은 MVP에서 만들지 않는다.
2. SQLAlchemy 엔진은 `pool_pre_ping=True`, 작은 풀(`pool_size` 3 이하), `pool_recycle`(예: 300초)을 설정한다. DB가 유휴 시 연결을 끊을 수 있기 때문이다.
3. 서버 디스크에 영구 데이터를 쓰지 않는다(재배포 시 초기화됨). 모든 상태는 DB에 둔다.
4. 백업: `backend/scripts/backup.sh`가 `pg_dump`로 덤프를 만든다. 주 1회 로컬에 받는다. 덤프 파일은 레포에 올리지 않는다.

## 15. 구현 순서

1. 레포 스캐폴딩, 환경설정, `/health`, 프론트의 서버 준비 대기 화면
2. DB 모델, Alembic 마이그레이션, 시드(`templates.yaml` 적재, `create_teacher.py`)
3. 인증(링크 로그인, 코드/PIN, 선생님 로그인, 세션, role 의존성, 잠금)
4. YAML 업로드, 검증, upsert, 문장 분리, locked 처리
5. 세트와 배정 API
6. 학생 API(조회, 저장, 제출, 결과) + 정답 비노출 테스트
7. 학생 화면
8. 선생님 화면(학생 관리와 링크, 업로드, 배정, 학생×주차 표, 숙제 상세와 리뷰, 태그 통계)
9. 배포(Neon, Render, Cloudflare Pages), 백업 스크립트
10. 학생 1명으로 시범 운용 후 수정

## 16. 수용 기준 (pytest로 자동 검증)

1. 제출 전 학생용 API 응답 어디에도 `is_correct`, 정답 태그, `model_slots`, `explanation`이 없다.
2. 다른 학생의 배정을 조회하거나 저장하면 404다.
3. 제출 후 `PUT answers`는 거부된다. 미완료 상태의 `submit`은 미완료 목록과 함께 실패한다.
4. 링크 재발급 후 이전 링크는 `link-login`에서 실패하고, 새 링크는 성공한다.
5. 학생 토큰으로 `/teacher/*`를 호출하면 거부된다.
6. PIN을 5회 연속 틀리면 잠기고, 잠금이 풀린 뒤에는 로그인된다.
7. 업로드 검증: 마커와 항목 불일치, 알 수 없는 태그, 잘못된 슬롯, 선택 보기 밖의 값이 각각 오류로 보고된다.
8. locked 지문에서 `is_correct`나 `tag`를 바꾼 업로드는 409이고, `explanation`만 바뀐 업로드는 통과한다.
9. 세션 만료 후 같은 링크로 재로그인하면 기존 답이 그대로 유지된다.

## 17. MVP 제외 (2차)

- 선생님 코멘트, 틀린 항목 재작성, 오답 재출제
- 지문 전체를 한 번에 푸는 방식(`mode: passage`)
- 입력형 빈칸의 부분 일치 자동 판정, Claude API를 이용한 근거 1차 판정
- 리딩과 리스닝(오디오 저장소 필요), 알림, 서버 깨우기용 외부 핑

## 부록 A. 샘플 지문 YAML

```yaml
passage_id: g1-2021-29-a
kind: grammar
source: 고1 2021 / 29번
text: >
  Although there is usually a correct way of holding and playing musical
  instruments, the most important instruction to begin with is [[1]] they are
  not toys and that they must be looked after. [[2]] children time to explore
  ways of handling and playing the instruments for themselves before showing
  them. Finding different ways to produce sounds [[3]] an important stage of
  musical exploration. Correct playing comes from the desire [[4]] the most
  appropriate sound quality and find the most comfortable playing position so
  that one can play with control over time. As instruments and music become
  more complex, learning appropriate playing techniques becomes [[5]] relevant.
items:
  - no: 1
    choice: that
    is_correct: true
    tag: 접속사·명사절
    model_slots: { role: 명사절을 이끄는 접속사, word: that }
    explanation: is의 보어 자리에 완전한 절(they are not toys ...)이 이어지므로 명사절을 이끄는 접속사 that이 맞다.
  - no: 2
    choice: Allow
    is_correct: true
    tag: 본동사 유무
    model_slots: { subject: 생략된 you(명령문), verb: Allow }
    explanation: 명령문의 동사원형으로서 문장의 본동사 역할을 하므로 Allow가 맞다.
  - no: 3
    choice: are
    is_correct: false
    tag: 수일치
    model_slots: { subject: Finding different ways to produce sounds, number: 단수, current: are, fixed: is }
    explanation: 주어는 sounds가 아니라 동명사구 Finding ... sounds이므로 단수로 취급해 is가 되어야 한다.
  - no: 4
    choice: to find
    is_correct: true
    tag: 준동사
    model_slots: { trigger: desire, form: to부정사, word: to find }
    explanation: 명사 desire를 수식하는 to부정사이고, and 뒤의 find와 병렬을 이루므로 to find가 맞다.
  - no: 5
    choice: increasingly
    is_correct: true
    tag: 형용사·부사
    model_slots: { target: relevant, role: 부사, word: increasingly }
    explanation: increasingly는 형용사 relevant를 수식하는 부사이므로 맞다.
```

## 부록 B. 나머지 샘플 지문의 정답 (YAML은 별도 변환)

| passage_id | 틀린 항목 | 고친 형태 | 태그 |
|---|---|---|---|
| g1-2021-29-b (미소) | ⑤ are | is | 수일치 (주어 the skin) |
| g1-2021-29-c (세이의 법칙) | ② which | where | 관계사 (뒤 절이 완전) |
| g1-2021-29-d (토양) | ④ occurring | occur | 본동사 유무 |