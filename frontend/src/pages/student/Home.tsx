import { useEffect, useState } from "react";
import { Link } from "react-router";
import { api } from "../../api";
import { fmtDateTime, kstWeekStart } from "../../format";
import type { AssignmentSummary } from "../../types";

function Card({ a }: { a: AssignmentSummary }) {
  const submitted = !!a.submitted_at;
  const to = submitted ? `/s/a/${a.id}/result` : `/s/a/${a.id}`;
  const label = submitted
    ? a.is_late ? "지각 제출" : "제출 완료"
    : a.status === "overdue" ? "마감 지남 · 지금 풀면 지각" : a.answered ? "이어 풀기" : "시작하기";
  return (
    <Link to={to} className={"card hw-card" + (a.status === "overdue" ? " overdue" : "")}>
      <div className="row between">
        <strong>{a.title}</strong>
        <span className={"badge " + a.status}>{label}</span>
      </div>
      <div className="progress"><div style={{ width: `${(a.answered / a.total) * 100}%` }} /></div>
      <div className="row between small muted">
        <span>{a.answered} / {a.total}</span>
        <span>마감 {fmtDateTime(a.due_at)}</span>
      </div>
    </Link>
  );
}

export default function StudentHome() {
  const [list, setList] = useState<AssignmentSummary[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api<AssignmentSummary[]>("/student/assignments").then(setList).catch((e) => setError(e.message));
  }, []);

  if (error) return <p className="error">{error}</p>;
  if (!list) return <p className="muted">불러오는 중…</p>;

  const thisWeek = kstWeekStart();
  const weekOf = (iso: string) => kstWeekStart(new Date(iso));
  const overdue = list.filter((a) => a.status === "overdue");
  const current = list.filter((a) => a.status !== "overdue" && (weekOf(a.assigned_at) === thisWeek || !a.submitted_at));
  const past = list.filter((a) => !overdue.includes(a) && !current.includes(a));

  return (
    <div className="stack">
      {overdue.length > 0 && (
        <section className="stack">
          <h2 className="h2">밀린 숙제</h2>
          {overdue.map((a) => <Card key={a.id} a={a} />)}
        </section>
      )}
      <section className="stack">
        <h2 className="h2">이번 주 숙제</h2>
        {current.length ? current.map((a) => <Card key={a.id} a={a} />) : <p className="muted">이번 주 숙제가 아직 없어요.</p>}
      </section>
      {past.length > 0 && (
        <details>
          <summary className="h2 summary">지난 숙제 ({past.length})</summary>
          <div className="stack">{past.map((a) => <Card key={a.id} a={a} />)}</div>
        </details>
      )}
    </div>
  );
}
