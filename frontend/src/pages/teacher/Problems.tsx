import { useEffect, useState, type FormEvent } from "react";
import { api, ApiError } from "../../api";
import { fmtDate } from "../../format";

type PassageRow = { id: string; kind: string; source: string; locked: boolean; item_count: number; created_at: string };
type SetRow = { id: number; title: string; passage_ids: string[]; item_count: number; created_at: string };
type StudentRow = { id: number; name: string };
type Issue = { line: number | null; message: string };
type UploadResult = { filename: string; passage_id: string | null; status: string; errors: Issue[]; warnings: Issue[]; changes: string[] };

const UPLOAD_STATUS: Record<string, string> = {
  created: "새로 추가", updated: "수정됨", unchanged: "변경 없음", error: "오류", conflict: "거부(배정된 지문)", skipped: "저장 안 됨",
};

/** datetime-local 값(시간대 없음)을 KST로 해석한 ISO 문자열 */
const kstIso = (local: string) => `${local}:00+09:00`;

function defaultDue(): string {
  // 오늘(KST)부터 7일 뒤 23:59
  const d = new Date(Date.now() + 9 * 3600 * 1000 + 7 * 86400 * 1000);
  return `${d.toISOString().slice(0, 10)}T23:59`;
}

export default function Problems() {
  const [passages, setPassages] = useState<PassageRow[]>([]);
  const [sets, setSets] = useState<SetRow[]>([]);
  const [students, setStudents] = useState<StudentRow[]>([]);
  const [files, setFiles] = useState<FileList | null>(null);
  const [upload, setUpload] = useState<{ saved: boolean; results: UploadResult[] } | null>(null);
  const [picked, setPicked] = useState<string[]>([]);
  const [title, setTitle] = useState("");
  const [assign, setAssign] = useState({ set_id: 0, student_ids: [] as number[], due: defaultDue() });
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");

  const load = () => Promise.all([
    api<PassageRow[]>("/teacher/passages").then(setPassages),
    api<SetRow[]>("/teacher/question-sets").then(setSets),
    api<StudentRow[]>("/teacher/students").then(setStudents),
  ]).catch((e) => setError(e.message));
  useEffect(() => { load(); }, []);

  async function doUpload(e: FormEvent) {
    e.preventDefault();
    if (!files?.length) return;
    const form = new FormData();
    Array.from(files).forEach((f) => form.append("files", f));
    try {
      setUpload(await api("/teacher/passages/upload", { form }));
      load();
    } catch (err) {
      if (err instanceof ApiError && err.body?.results) setUpload(err.body);
      else setError(err instanceof Error ? err.message : "업로드 실패");
    }
  }

  async function createSet(e: FormEvent) {
    e.preventDefault();
    setError("");
    try {
      const r = await api<{ id: number }>("/teacher/question-sets", { json: { title, passage_ids: picked } });
      setMsg(`세트 "${title}"를 만들었어요.`);
      setPicked([]);
      setTitle("");
      setAssign((a) => ({ ...a, set_id: r.id }));
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "세트 생성 실패");
    }
  }

  async function doAssign(e: FormEvent) {
    e.preventDefault();
    setError("");
    try {
      const r = await api<{ assignment_ids: number[] }>("/teacher/assignments", {
        json: { set_id: assign.set_id, student_ids: assign.student_ids, due_at: kstIso(assign.due) },
      });
      setMsg(`${r.assignment_ids.length}명에게 배정했어요.`);
      setAssign((a) => ({ ...a, student_ids: [] }));
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "배정 실패");
    }
  }

  const toggle = <T,>(list: T[], v: T) => (list.includes(v) ? list.filter((x) => x !== v) : [...list, v]);

  return (
    <div className="stack">
      {msg && <div className="notice" onClick={() => setMsg("")}>{msg}</div>}
      {error && <p className="error" onClick={() => setError("")}>{error}</p>}

      <form className="card stack-sm" onSubmit={doUpload}>
        <h2 className="h2">지문 YAML 업로드</h2>
        <input type="file" accept=".yaml,.yml" multiple onChange={(e) => setFiles(e.target.files)} />
        <span className="small muted">여러 파일을 한 번에 올릴 수 있어요. 하나라도 오류가 있으면 아무것도 저장되지 않아요.</span>
        <button className="btn primary" disabled={!files?.length}>업로드</button>
        {upload && (
          <div className="stack-sm">
            <strong>{upload.saved ? "저장했어요" : "저장하지 않았어요"}</strong>
            {upload.results.map((r) => (
              <div key={r.filename} className={"upload-result " + r.status}>
                <div className="row between">
                  <strong>{r.filename}</strong>
                  <span className="small">{r.passage_id ?? ""} · {UPLOAD_STATUS[r.status] ?? r.status}</span>
                </div>
                {r.errors.map((e, i) => <div key={"e" + i} className="small error">{e.line ? `${e.line}행: ` : ""}{e.message}</div>)}
                {r.changes.length > 0 && r.status === "conflict" && (
                  <ul className="small">{r.changes.map((c) => <li key={c}>{c}</li>)}</ul>
                )}
                {r.warnings.map((w, i) => <div key={"w" + i} className="small warn-text">⚠ {w.line ? `${w.line}행: ` : ""}{w.message}</div>)}
              </div>
            ))}
          </div>
        )}
      </form>

      <form className="card stack-sm" onSubmit={createSet}>
        <h2 className="h2">지문 목록 · 세트 만들기</h2>
        <span className="small muted">체크한 순서대로 세트에 들어가요. 🔒는 배정된 적 있는 지문(정답 수정 불가).</span>
        <div className="list">
          {passages.map((p) => (
            <label key={p.id} className="list-row check-row">
              <input type="checkbox" checked={picked.includes(p.id)} onChange={() => setPicked(toggle(picked, p.id))} />
              <span>
                {picked.includes(p.id) && <span className="badge">{picked.indexOf(p.id) + 1}</span>} {p.locked ? "🔒 " : ""}<strong>{p.source || p.id}</strong>
                <span className="small muted"> · {p.id} · {p.item_count}항목 · {fmtDate(p.created_at)}</span>
              </span>
            </label>
          ))}
          {passages.length === 0 && <p className="muted small">지문이 없습니다.</p>}
        </div>
        <label className="field"><span>세트 이름</span><input value={title} onChange={(e) => setTitle(e.target.value)} placeholder="예: 10월 1주차" required /></label>
        <button className="btn primary" disabled={!picked.length || !title.trim()}>세트 만들기 ({picked.length}지문)</button>
      </form>

      <form className="card stack-sm" onSubmit={doAssign}>
        <h2 className="h2">배정</h2>
        <label className="field">
          <span>세트</span>
          <select value={assign.set_id} onChange={(e) => setAssign({ ...assign, set_id: Number(e.target.value) })} required>
            <option value={0}>선택</option>
            {sets.map((s) => <option key={s.id} value={s.id}>{s.title} ({s.passage_ids.length}지문 · {s.item_count}항목)</option>)}
          </select>
        </label>
        <div className="field">
          <span>학생</span>
          <div className="chips">
            {students.map((s) => (
              <label key={s.id} className={"chip" + (assign.student_ids.includes(s.id) ? " selected" : "")}>
                <input type="checkbox" checked={assign.student_ids.includes(s.id)} onChange={() => setAssign({ ...assign, student_ids: toggle(assign.student_ids, s.id) })} />
                {s.name}
              </label>
            ))}
            {students.length > 0 && (
              <button type="button" className="btn link small" onClick={() => setAssign({ ...assign, student_ids: students.map((s) => s.id) })}>전체 선택</button>
            )}
          </div>
        </div>
        <label className="field"><span>마감 (한국 시간)</span><input type="datetime-local" value={assign.due} onChange={(e) => setAssign({ ...assign, due: e.target.value })} required /></label>
        <button className="btn primary" disabled={!assign.set_id || !assign.student_ids.length}>배정하기</button>
      </form>
    </div>
  );
}
