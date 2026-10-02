import { useEffect, useState } from "react";
import { Link, useParams } from "react-router";
import { api } from "../../api";
import { FilledSentence, findTemplate } from "../../components/Filled";
import { MarkedText } from "../../components/Passage";
import { circled, fmtDateTime } from "../../format";
import type { StudentResult, Templates } from "../../types";

const J = (b: boolean) => (b ? "맞다" : "틀리다");

export default function Result() {
  const aid = Number(useParams().id);
  const [data, setData] = useState<StudentResult | null>(null);
  const [tpls, setTpls] = useState<Templates | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all([api<StudentResult>(`/student/assignments/${aid}/result`), api<Templates>("/templates?kind=grammar")])
      .then(([d, t]) => { setData(d); setTpls(t); })
      .catch((e) => setError(e.message));
  }, [aid]);

  if (error) return <div className="stack"><p className="error">{error}</p><Link to={`/s/a/${aid}`} className="btn">숙제로 돌아가기</Link></div>;
  if (!data || !tpls) return <p className="muted">불러오는 중…</p>;

  const all = data.passages.flatMap((p) => p.items);
  const sameJudgement = all.filter((it) => it.judgement_ok).length;

  return (
    <div className="stack">
      <div className="card stack-sm">
        <strong>{data.title}</strong>
        <span className="small muted">
          제출 {fmtDateTime(data.submitted_at)}{data.is_late ? " · 지각 제출" : ""}
        </span>
        <span>판단이 정답과 같은 문항 {sameJudgement} / {all.length}</span>
      </div>

      {data.passages.map((p) => {
        const choices = Object.fromEntries(p.items.map((it) => [it.no, it.choice]));
        return (
          <section key={p.id} className="stack">
            <h2 className="h2">{p.source}</h2>
            {p.items.map((it) => (
              <article key={it.id} className="card stack-sm">
                <div className="sentence">
                  <MarkedText text={it.sentence} choices={choices} underline={[it.no]} highlight={it.no} />
                </div>
                <div className="compare">
                  <div className="col">
                    <div className="label">내 근거</div>
                    <div className="small">
                      {circled(it.no)} {J(it.mine.judgement)} · {it.mine.tag}
                    </div>
                    <FilledSentence template={findTemplate(tpls.templates, it.mine.tag, it.mine.judgement)} values={it.mine.slots} />
                  </div>
                  <div className="col model">
                    <div className="label">모범 근거</div>
                    <div className="small">
                      {circled(it.no)} {J(it.correct.is_correct)} · {it.correct.tag}
                    </div>
                    <FilledSentence template={findTemplate(tpls.templates, it.correct.tag, it.correct.is_correct)} values={it.correct.model_slots} />
                  </div>
                </div>
                <div className="row wrap small">
                  <span className={"pill " + (it.judgement_ok ? "ok" : "diff")}>판단 {it.judgement_ok ? "일치" : "다름"}</span>
                  <span className={"pill " + (it.tag_ok ? "ok" : "diff")}>문법 포인트 {it.tag_ok ? "일치" : "다름"}</span>
                </div>
                {it.correct.explanation && <p className="explanation">{it.correct.explanation}</p>}
              </article>
            ))}
          </section>
        );
      })}
      <Link to="/s" className="btn">홈으로</Link>
    </div>
  );
}
