import { useEffect, useState } from "react";
import { Link } from "react-router";
import { api } from "../../api";
import { addDays, fmtDate, fmtDateTime, kstWeekStart, STATUS_LABEL } from "../../format";
import type { AssignmentSummary } from "../../types";

type Overview = {
  weeks: string[];
  students: { id: number; name: string; cells: Record<string, AssignmentSummary[]> }[];
  overdue: { assignment_id: number; student_name: string; title: string; due_at: string; days_overdue: number; answered: number; total: number }[];
};

export default function TeacherHome() {
  const [week, setWeek] = useState(kstWeekStart());
  const [data, setData] = useState<Overview | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api<Overview>(`/teacher/overview?week=${week}&weeks=6`).then(setData).catch((e) => setError(e.message));
  }, [week]);

  if (error) return <p className="error">{error}</p>;
  if (!data) return <p className="muted">불러오는 중…</p>;

  return (
    <div className="stack">
      <section className="stack-sm">
        <h2 className="h2">마감 지난 미제출 {data.overdue.length > 0 && <span className="badge overdue">{data.overdue.length}</span>}</h2>
        {data.overdue.length === 0 ? (
          <p className="muted small">없습니다.</p>
        ) : (
          <div className="card list">
            {data.overdue.map((o) => (
              <Link key={o.assignment_id} to={`/t/a/${o.assignment_id}`} className="list-row">
                <strong>{o.student_name}</strong>
                <span>{o.title}</span>
                <span className="small muted">{o.answered}/{o.total} · 마감 {fmtDate(o.due_at)} · {o.days_overdue}일 지남</span>
              </Link>
            ))}
          </div>
        )}
      </section>

      <section className="stack-sm">
        <div className="row between">
          <h2 className="h2">학생 × 주차 (배정일 기준)</h2>
          <div className="row">
            <button className="btn small" onClick={() => setWeek(addDays(week, -7))}>←</button>
            <button className="btn small" onClick={() => setWeek(kstWeekStart())}>이번 주</button>
            <button className="btn small" onClick={() => setWeek(addDays(week, 7))}>→</button>
          </div>
        </div>
        {data.students.length === 0 ? (
          <p className="muted">학생이 없습니다. <Link to="/t/students">학생 추가</Link></p>
        ) : (
          <div className="table-wrap">
            <table className="grid">
              <thead>
                <tr>
                  <th>학생</th>
                  {data.weeks.map((w) => <th key={w}>{w.slice(5).replace("-", "/")}~</th>)}
                </tr>
              </thead>
              <tbody>
                {data.students.map((s) => (
                  <tr key={s.id}>
                    <th><Link to={`/t/students/${s.id}`}>{s.name}</Link></th>
                    {data.weeks.map((w) => (
                      <td key={w}>
                        {s.cells[w].map((a) => (
                          <Link key={a.id} to={`/t/a/${a.id}`} className={"cell " + a.status}>
                            <span>{STATUS_LABEL[a.status]}</span>
                            <span className="tiny">
                              {a.submitted_at ? fmtDateTime(a.submitted_at) : `${a.answered}/${a.total}`}
                            </span>
                          </Link>
                        ))}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
