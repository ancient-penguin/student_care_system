import { useEffect, useState, type FormEvent } from "react";
import { Link } from "react-router";
import { api } from "../../api";
import { LinkBox } from "../../components/LinkBox";
import { fmtDateTime } from "../../format";

type Row = { id: number; name: string; login_code: string; is_active: boolean; active_sessions: number; last_used_at: string | null };

export default function Students() {
  const [rows, setRows] = useState<Row[] | null>(null);
  const [form, setForm] = useState({ name: "", login_code: "", pin: "" });
  const [issued, setIssued] = useState<{ name: string; token: string } | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const load = () => api<Row[]>("/teacher/students").then(setRows).catch((e) => setError(e.message));
  useEffect(() => { load(); }, []);

  async function add(e: FormEvent) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      const r = await api<{ name: string; link_token: string }>("/teacher/students", { json: form });
      setIssued({ name: r.name, token: r.link_token });
      setForm({ name: "", login_code: "", pin: "" });
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "추가 실패");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="stack">
      {issued && <LinkBox name={issued.name} token={issued.token} onClose={() => setIssued(null)} />}

      <form className="card stack-sm" onSubmit={add}>
        <h2 className="h2">학생 추가</h2>
        <div className="form-row">
          <label className="field"><span>이름</span><input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required /></label>
          <label className="field"><span>코드</span><input value={form.login_code} onChange={(e) => setForm({ ...form, login_code: e.target.value })} autoCapitalize="none" required /></label>
          <label className="field"><span>PIN (4~6자리)</span><input value={form.pin} onChange={(e) => setForm({ ...form, pin: e.target.value })} inputMode="numeric" pattern="\d{4,6}" required /></label>
        </div>
        {error && <p className="error">{error}</p>}
        <button className="btn primary" disabled={busy}>추가하고 링크 발급</button>
      </form>

      <section className="stack-sm">
        <h2 className="h2">학생 목록</h2>
        {!rows ? <p className="muted">불러오는 중…</p> : rows.length === 0 ? <p className="muted">아직 없습니다.</p> : (
          <div className="card list">
            {rows.map((r) => (
              <Link key={r.id} to={`/t/students/${r.id}`} className="list-row">
                <strong>{r.name}</strong>
                <span className="small muted">코드 {r.login_code}</span>
                <span className="small muted">기기 {r.active_sessions}대 · 최근 {fmtDateTime(r.last_used_at)}</span>
              </Link>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
