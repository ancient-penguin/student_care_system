# 문법 숙제 웹

구현 기준은 [guide.md](guide.md)를 따른다. 이 문서는 실행과 배포 방법만 다룬다.

## 로컬 개발

준비물: Python 3.11+, Node 20+, PostgreSQL 16

```bash
# 1) DB
createdb -U postgres grammar
createdb -U postgres grammar_test

# 2) 백엔드
cd backend
python -m venv .venv
.venv/Scripts/activate            # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env               # 필요하면 값을 고친다
alembic upgrade head
python -m scripts.load_templates   # data/templates.yaml → DB
python -m scripts.create_teacher --name 선생님 --code teacher   # 비밀번호는 프롬프트로 입력
uvicorn app.main:app --reload --port 8000

# 3) 테스트(TEST_DATABASE_URL의 DB를 지우고 다시 만든다)
python -m pytest -q

# 4) 프론트엔드
cd ../frontend
npm install
npm run dev                        # http://localhost:5173
```

## 데이터 수정

- 근거 문장 틀/태그: `data/templates.yaml`을 고친 뒤 `python -m scripts.load_templates`. 파일 순서가 학생 화면의 태그 순서다.
- 지문: 선생님 화면 > 문제 > YAML 업로드. 형식은 `data/passages/g1-2021-29-a.yaml` 참고.

## 배포 (전부 무료 플랜)

무료 플랜의 한도와 정책은 자주 바뀐다. 배포할 때 각 서비스의 공식 가격 페이지를 다시 확인한다.

1. **Neon**: 프로젝트를 만들고 연결 주소(`postgresql://...?sslmode=require`)를 복사한다.
2. **Render** (Web Service, Free)
   - Root Directory: `backend`
   - Build: `pip install -r requirements.txt`
   - Start: `alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT`
   - 환경변수: `DATABASE_URL`(Neon 주소), `CORS_ORIGINS`(예: `https://xxx.pages.dev`), `APP_ENV=production`,
     필요하면 `SESSION_TTL_STUDENT_DAYS`, `SESSION_TTL_TEACHER_DAYS`
3. **초기 데이터**: 로컬에서 Neon 주소로 한 번 실행한다.
   ```bash
   cd backend
   DATABASE_URL='<Neon 주소>' python -m scripts.load_templates
   DATABASE_URL='<Neon 주소>' python -m scripts.create_teacher --name 선생님 --code teacher
   ```
4. **Cloudflare Pages**
   - Root: `frontend`, Build: `npm run build`, Output: `dist`
   - 환경변수: `VITE_API_URL`(Render 주소, 예: `https://xxx.onrender.com`)
   - SPA 라우팅은 `frontend/public/_redirects`가 처리한다.

## 백업

```bash
DATABASE_URL='<Neon 주소>' ./backend/scripts/backup.sh   # backups/ 아래 덤프 생성 (git 제외)
```

주 1회 실행한다. 복원 명령은 스크립트 출력에 나온다.
