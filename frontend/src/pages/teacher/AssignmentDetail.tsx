import { useEffect, useState } from "react";
import { Link, useParams } from "react-router";
import { api } from "../../api";
import { FilledSentence, findTemplate } from "../../components/Filled";
import { MarkedText } from "../../components/Passage";
import { circled, fmtDateTime, fmtDuration, STATUS_LABEL } from "../../format";
import type { AssignmentSummary, Correct, Templates } from "../../types";

type TAnswer = {
  answer_id: number;
  judgement: boolean;
  tag: string;
  slots: Record<string, string>;
  created_at: string;
  saved_at: string;
  duration_sec: number;
  judgement_ok: boolean | null;
  tag_ok: boolean | null;
  slots_check: Record<string, boolean> | null;
  diagnosis: string | null;
  review_status: "ok" | "needs_work" | null;
};

type Detail = AssignmentSummary & {
  student: { id: number; name: string };
  started_at: string | null;
  total_duration_sec: number;
  daily_saves: { date: string; count: number }[];
  passages: { id: string; source: string; text: string; items: { id: number; no: number; choice: string; sentence: string; correct: Correct; answer: TAnswer | null }[] }[];
};

const J = (b: boolean) => (b ? "맞다" : "틀리다");
const DIAG_CLASS: Record<string, string> = { "이해": "ok", "찍기 의심 / 개념 오인": "warn", "적용 실패": "warn", "개념 미습득": "bad" };

export default function AssignmentDetail() {
  const id = Number(useParams().id);
  const [data, setData] = useState<Detail | null>(null);
  const [tpls, setTpls] = useState<Templates | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all([api<Detail>(`/teacher/assignments/${id}`), api<Templates>("/templates?kind=grammar")])
      .then(([d, t]) => { setData(d); setTpls(t); })
      .catch((e) => setError(e.message));
  }, [id]);

  async function review(answerId: number, status: "ok" | "needs_work") {
    try {
      await api(`/teacher/answers/${answerId}/review`, { method: "PUT", json: { status } });
      setData((d) => d && {
        ...d,
        passages: d.passages.map((p) => ({
          ...p,
          items: p.items.map((it) => (it.answer?.answer_id === answerId ? { ...it, answer: { ...it.answer, review_status: status } } : it)),
        })),
      });
    } catch (e) {
      alert(e instanceof Error ? e.message : "저장 실패");
    }
  }

  if (error) return <p className="error">{error}</p>;
  if (!data || !tpls) return <p className="muted">불러오는 중…</p>;
  const submitted = !!data.submitted_at;

  return (
    <div className="stack">
      <div className="card stack-sm">
        <div className="row between">
          <strong><Link to={`/t/students/${data.student.id}`}>{data.student.name}</Link> · {data.title}</strong>
          <span className={"badge " + data.status}>{STATUS_LABEL[data.status]}</span>
        </div>
        <div className="kv small">
          <span>배정</span><span>{fmtDateTime(data.assigned_at)}</span>
          <span>마감</span><span>{fmtDateTime(data.due_at)}</span>
          <span>시작</span><span>{fmtDateTime(data.started_at)}</span>
          <span>제출</span><span>{fmtDateTime(data.submitted_at)}{data.is_late ? " (지각)" : ""}</span>
          <span>진행</span><span>{data.answered} / {data.total} · 총 {fmtDuration(data.total_duration_sec)}</span>
          <span>일자별</span>
          <span>{data.daily_saves.length ? data.daily_saves.map((d) => `${d.date.slice(5).replace("-", "/")} ${d.count}건`).join(" · ") : "-"}</span>
        </div>
      </div>

      {data.passages.map((p) => {
        const choices = Object.fromEntries(p.items.map((it) => [it.no, it.choice]));
        return (
          <section key={p.id} className="stack">
            <details>
              <summary className="h2 summary">{p.source} <span className="small muted">({p.id})</span></summary>
              <p className="passage card"><MarkedText text={p.text} choices={choices} underline="all" /></p>
            </details>
            {p.items.map((it) => {
              const a = it.answer;
              return (
                <article key={it.id} className="card stack-sm">
                  <div className="sentence small">
                    <MarkedText text={it.sentence} choices={choices} underline={[it.no]} highlight={it.no} />
                  </div>
                  <div className="compare">
                    <div className="col">
                      <div className="label">학생</div>
                      {a ? (
                        <>
                          <div className="small">{circled(it.no)} {J(a.judgement)} · {a.tag}</div>
                          <FilledSentence template={findTemplate(tpls.templates, a.tag, a.judgement)} values={a.slots} check={a.slots_check} />
                        </>
                      ) : <span className="muted small">미작성</span>}
                    </div>
                    <div className="col model">
                      <div className="label">모범</div>
                      <div className="small">{circled(it.no)} {J(it.correct.is_correct)} · {it.correct.tag}</div>
                      <FilledSentence template={findTemplate(tpls.templates, it.correct.tag, it.correct.is_correct)} values={it.correct.model_slots} />
                    </div>
                  </div>
                  {it.correct.explanation && <p className="explanation small">{it.correct.explanation}</p>}
                  {a && (
                    <div className="row between wrap">
                      <div className="row wrap small">
                        {a.diagnosis && <span className={"pill " + (DIAG_CLASS[a.diagnosis] ?? "")}>{a.diagnosis}</span>}
                        <span className="muted">저장 {fmtDateTime(a.saved_at)} · {fmtDuration(a.duration_sec)}</span>
                      </div>
                      {submitted && (
                        <div className="seg small-seg">
                          <button className={"btn small" + (a.review_status === "ok" ? " selected" : "")} onClick={() => review(a.answer_id, "ok")}>적절</button>
                          <button className={"btn small" + (a.review_status === "needs_work" ? " selected warn" : "")} onClick={() => review(a.answer_id, "needs_work")}>보완 필요</button>
                        </div>
                      )}
                    </div>
                  )}
                </article>
              );
            })}
          </section>
        );
      })}
    </div>
  );
}
