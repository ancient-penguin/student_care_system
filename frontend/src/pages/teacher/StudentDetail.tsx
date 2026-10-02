import { useEffect, useState } from "react";
import { Link, useParams } from "react-router";
import { api } from "../../api";
import { LinkBox } from "../../components/LinkBox";
import { fmtDateTime, STATUS_LABEL } from "../../format";
import type { AssignmentSummary } from "../../types";

type Detail = {
  id: number;
  name: string;
  login_code: string;
  link_rotated_at: string | null;
  locked_until: string | null;
  sessions: { id: number; created_at: string; last_used_at: string; expires_at: string; user_agent: string | null }[];
  assignments: AssignmentSummary[];
};

function deviceName(ua: string | null): string {
  if (!ua) return "알 수 없는 기기";
  const inApp = /KAKAOTALK/i.test(ua) ? " (카카오톡)" : "";
  if (/iPhone|iPad/i.test(ua)) return "iPhone/iPad" + inApp;
  if (/Android/i.test(ua)) return "Android" + inApp;
  if (/Windows/i.test(ua)) return "Windows PC";
  if (/Macintosh/i.test(ua)) return "Mac";
  return ua.slice(0, 40);
}

export default function StudentDetail() {
  const id = Number(useParams().id);
  const [data, setData] = useState<Detail | null>(null);
  const [issued, setIssued] = useState<string | null>(null);
  const [error, setError] = useState("");

  const load = () => api<Detail>(`/teacher/students/${id}`).then(setData).catch((e) => setError(e.message));
  useEffect(() => { load(); }, [id]); // eslint-disable-line react-hooks/exhaustive-deps

  async function rotate() {
    if (!confirm("기존 링크는 더 이상 쓸 수 없게 됩니다. 이미 로그인된 기기는 유지됩니다. 새 링크를 만들까요?")) return;
    const r = await api<{ link_token: string }>(`/teacher/students/${id}/rotate-link`, { method: "POST" });
    setIssued(r.link_token);
    load();
  }

  async function revoke() {
    if (!confirm("이 학생의 모든 기기에서 로그아웃시킵니다. 계속할까요?")) return;
    await api(`/teacher/students/${id}/revoke-sessions`, { method: "POST" });
    load();
  }

  if (error) return <p className="error">{error}</p>;
  if (!data) return <p className="muted">불러오는 중…</p>;

  return (
    <div className="stack">
      <div className="card stack-sm">
        <h2 className="h2">{data.name}</h2>
        <div className="kv small">
          <span>코드</span><span>{data.login_code}</span>
          <span>링크 발급</span><span>{fmtDateTime(data.link_rotated_at)}</span>
          {data.locked_until && <><span>PIN 잠금</span><span className="error">{fmtDateTime(data.locked_until)}까지</span></>}
        </div>
        <div className="row wrap">
          <button className="btn" onClick={rotate}>링크 재발급</button>
          <button className="btn danger" onClick={revoke}>모든 세션 종료</button>
        </div>
      </div>

      {issued && <LinkBox name={data.name} token={issued} onClose={() => setIssued(null)} />}

      <section className="stack-sm">
        <h3 className="h3">로그인된 기기 ({data.sessions.length})</h3>
        {data.sessions.length === 0 ? <p className="muted small">없습니다.</p> : (
          <div className="card list">
            {data.sessions.map((s) => (
              <div key={s.id} className="list-row">
                <strong>{deviceName(s.user_agent)}</strong>
                <span className="small muted">마지막 사용 {fmtDateTime(s.last_used_at)} · 로그인 {fmtDateTime(s.created_at)}</span>
              </div>
            ))}
          </div>
        )}
      </section>

      <section className="stack-sm">
        <h3 className="h3">숙제</h3>
        {data.assignments.length === 0 ? <p className="muted small">없습니다.</p> : (
          <div className="card list">
            {data.assignments.map((a) => (
              <Link key={a.id} to={`/t/a/${a.id}`} className="list-row">
                <strong>{a.title}</strong>
                <span className={"badge " + a.status}>{STATUS_LABEL[a.status]}</span>
                <span className="small muted">{a.answered}/{a.total} · 마감 {fmtDateTime(a.due_at)}</span>
              </Link>
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
