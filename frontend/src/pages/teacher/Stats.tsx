import { useEffect, useState } from "react";
import { api } from "../../api";
import { pct } from "../../format";

type TagStat = { tag: string; count: number; judgement_error_rate: number | null; tag_mismatch_rate: number | null };

function Bar({ rate }: { rate: number | null }) {
  return (
    <div className="bar-cell">
      <div className="bar"><div style={{ width: `${(rate ?? 0) * 100}%` }} /></div>
      <span className="small">{pct(rate)}</span>
    </div>
  );
}

export default function Stats() {
  const [students, setStudents] = useState<{ id: number; name: string }[]>([]);
  const [studentId, setStudentId] = useState<string>("");
  const [rows, setRows] = useState<TagStat[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => { api("/teacher/students").then(setStudents).catch(() => {}); }, []);
  useEffect(() => {
    setRows(null);
    api<{ tags: TagStat[] }>(`/teacher/stats/tags${studentId ? `?student_id=${studentId}` : ""}`)
      .then((r) => setRows(r.tags))
      .catch((e) => setError(e.message));
  }, [studentId]);

  return (
    <div className="stack">
      <div className="row between wrap">
        <h2 className="h2">태그별 통계 (제출된 답, 전체 기간)</h2>
        <select value={studentId} onChange={(e) => setStudentId(e.target.value)}>
          <option value="">전체 학생</option>
          {students.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
        </select>
      </div>
      <p className="small muted">판단 오류율: 맞다/틀리다를 잘못 고른 비율 · 태그 불일치율: 정답 태그와 다른 태그를 고른 비율 (태그는 항목의 정답 태그 기준)</p>
      {error && <p className="error">{error}</p>}
      {!rows ? <p className="muted">불러오는 중…</p> : (
        <div className="table-wrap">
          <table className="grid stats">
            <thead><tr><th>태그</th><th>답 수</th><th>판단 오류율</th><th>태그 불일치율</th></tr></thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.tag}>
                  <th>{r.tag}</th>
                  <td>{r.count}</td>
                  <td><Bar rate={r.judgement_error_rate} /></td>
                  <td><Bar rate={r.tag_mismatch_rate} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
