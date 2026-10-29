import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router";
import { api } from "../../api";
import { addDays, fmtDate, fmtDateTime, kstWeekStart, STATUS_LABEL } from "../../format";
import type { AssignmentSummary } from "../../types";

type Overview = {
  weeks: string[];
  students: { id: number; name: string; cells: Record<string, AssignmentSummary[]> }[];
  overdue: { assignment_id: number; student_name: string; title: string; due_at: string; days_overdue: number; answered: number; total: number }[];
};

function WeekOverview() {
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

type Dashboard = {
  metrics: { total_students: number; accuracy: number | null; pending_reviews: number; overdue: number };
  students: {
    id: number;
    name: string;
    latest: AssignmentSummary | null;
    accuracy: number | null;
    pending_reviews: number;
    last_activity_at: string | null;
  }[];
  assignments_chart: { set_id: number; title: string; submitted: number; accuracy: number | null; tag_accuracy: number | null }[];
};

const pct = (v: number | null) => (v === null ? "–" : `${Math.round(v * 100)}%`);

function Bar({ value, series }: { value: number | null; series: "a" | "b" }) {
  return (
    <div className="hbar">
      <div className="track"><div className={"fill series-" + series} style={{ width: `${(value ?? 0) * 100}%` }} /></div>
      <span className="val">{pct(value)}</span>
    </div>
  );
}

export default function TeacherHome() {
  const navigate = useNavigate();
  const [data, setData] = useState<Dashboard | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api<Dashboard>("/teacher/dashboard").then(setData).catch((e) => setError(e.message));
  }, []);

  if (error) return <p className="error">{error}</p>;
  if (!data) return <p className="muted">불러오는 중…</p>;
  const m = data.metrics;

  return (
    <div className="stack">
      <section className="metrics">
        <div className="card metric">
          <span className="label">전체 학생</span>
          <span className="value">{m.total_students}</span>
          <span className="sub">활성 계정 기준</span>
        </div>
        <div className="card metric">
          <span className="label">평균 판단 정답률</span>
          <span className="value">{pct(m.accuracy)}</span>
          <span className="sub">제출된 답 기준</span>
        </div>
        <div className={"card metric" + (m.pending_reviews ? " attention" : "")}>
          <span className="label">검토 대기</span>
          <span className="value">{m.pending_reviews}</span>
          <span className="sub">적절/보완 필요 미선택 답</span>
        </div>
        <div className={"card metric" + (m.overdue ? " attention" : "")}>
          <span className="label">마감 지난 미제출</span>
          <span className="value">{m.overdue}</span>
          <span className="sub">숙제 수</span>
        </div>
      </section>

      <section className="stack-sm">
        <div className="section-head">
          <h2 className="h2">학생</h2>
          <Link to="/t/students" className="small">학생 관리</Link>
        </div>
        {data.students.length === 0 ? (
          <p className="muted">학생이 없습니다. <Link to="/t/students">학생 추가</Link></p>
        ) : (
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th>이름</th>
                  <th>최근 숙제</th>
                  <th>상태</th>
                  <th>진행</th>
                  <th className="num">정답률</th>
                  <th className="num">검토 대기</th>
                  <th>최근 활동</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {data.students.map((s) => {
                  const a = s.latest;
                  return (
                    <tr key={s.id} className={a ? "clickable" : ""} onClick={() => a && navigate(`/t/a/${a.id}`)}>
                      <td><Link to={`/t/students/${s.id}`} onClick={(e) => e.stopPropagation()}><strong>{s.name}</strong></Link></td>
                      <td>{a ? a.title : <span className="muted">배정 없음</span>}</td>
                      <td>{a && <span className={"badge " + a.status}>{STATUS_LABEL[a.status]}</span>}</td>
                      <td>
                        {a && (
                          <div className="mini-progress">
                            <div className="progress"><div style={{ width: `${(a.answered / a.total) * 100}%` }} /></div>
                            <span className="tiny muted">{a.answered}/{a.total}</span>
                          </div>
                        )}
                      </td>
                      <td className="num">{pct(s.accuracy)}</td>
                      <td className="num">{s.pending_reviews || <span className="muted">0</span>}</td>
                      <td className="small muted">{s.last_activity_at ? fmtDateTime(s.last_activity_at) : "–"}</td>
                      <td>{a && s.pending_reviews > 0 && <Link to={`/t/a/${a.id}`} className="small" onClick={(e) => e.stopPropagation()}>검토하기</Link>}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="card stack">
        <div className="section-head">
          <h2 className="h2">세트별 성과</h2>
          <div className="legend">
            <span><i className="series-a" />판단 정답률</span>
            <span><i className="series-b" />태그 일치율</span>
          </div>
        </div>
        {data.assignments_chart.length === 0 ? (
          <p className="muted small">아직 배정한 세트가 없습니다.</p>
        ) : (
          <div className="chart">
            {data.assignments_chart.map((c) => (
              <div key={c.set_id} className="chart-row">
                <div className="chart-label" title={c.title}>
                  {c.title}
                  <span className="tiny">제출 {c.submitted}명</span>
                </div>
                <div className="chart-bars">
                  <Bar value={c.accuracy} series="a" />
                  <Bar value={c.tag_accuracy} series="b" />
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      <details className="fold">
        <summary>미제출 목록 · 학생 × 주차 표</summary>
        <div style={{ marginTop: 12 }}><WeekOverview /></div>
      </details>
    </div>
  );
}
