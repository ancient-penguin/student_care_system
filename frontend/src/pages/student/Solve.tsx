import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router";
import { api, ApiError, setBeforeUnauthorized, storage } from "../../api";
import { findTemplate } from "../../components/Filled";
import { MarkedText } from "../../components/Passage";
import { RadioGroup } from "../../components/RadioRow";
import { circled, fmtDateTime } from "../../format";
import type { StudentAssignment, StudentItem, Template, Templates } from "../../types";

type Form = { judgement: boolean | null; tag: string | null; slots: Record<string, string> };
const EMPTY: Form = { judgement: null, tag: null, slots: {} };

const draftKey = (aid: number, itemId: number) => `draft:${aid}:${itemId}`;

function readDraft(aid: number, itemId: number): Form | null {
  const raw = storage.get(draftKey(aid, itemId));
  if (!raw) return null;
  try {
    return JSON.parse(raw) as Form;
  } catch {
    return null;
  }
}

function isComplete(form: Form, tpl: Template | undefined): boolean {
  if (form.judgement === null || !form.tag || !tpl) return false;
  return Object.keys(tpl.slots).every((k) => (form.slots[k] ?? "").trim() !== "");
}

/** 화면이 보이는 동안만 시간을 잰다. */
function useVisibleTimer() {
  const acc = useRef(0);
  const start = useRef<number | null>(document.visibilityState === "visible" ? Date.now() : null);
  useEffect(() => {
    const onChange = () => {
      if (document.visibilityState === "hidden" && start.current !== null) {
        acc.current += Date.now() - start.current;
        start.current = null;
      } else if (document.visibilityState === "visible" && start.current === null) {
        start.current = Date.now();
      }
    };
    document.addEventListener("visibilitychange", onChange);
    return () => document.removeEventListener("visibilitychange", onChange);
  }, []);
  const take = useCallback(() => {
    const ms = acc.current + (start.current !== null ? Date.now() - start.current : 0);
    acc.current = 0;
    start.current = document.visibilityState === "visible" ? Date.now() : null;
    return Math.round(ms / 1000);
  }, []);
  return take;
}

export default function Solve() {
  const aid = Number(useParams().id);
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const [data, setData] = useState<StudentAssignment | null>(null);
  const [tpls, setTpls] = useState<Templates | null>(null);
  const [error, setError] = useState("");
  const [idx, setIdx] = useState<number | "submit" | null>(null);
  const [form, setForm] = useState<Form>(EMPTY);
  const [saving, setSaving] = useState(false);
  const [showPassage, setShowPassage] = useState(false);
  const [incomplete, setIncomplete] = useState<number[] | null>(null);
  const pending = useRef<Record<number, Form>>({});
  const formRef = useRef(form);
  formRef.current = form;
  const takeSeconds = useVisibleTimer();

  useEffect(() => {
    Promise.all([api<StudentAssignment>(`/student/assignments/${aid}`), api<Templates>("/templates?kind=grammar")])
      .then(([d, t]) => {
        if (d.submitted_at) {
          navigate(`/s/a/${aid}/result`, { replace: true });
          return;
        }
        setData(d);
        setTpls(t);
        const wanted = Number(params.get("item"));
        const at = d.item_order.indexOf(wanted);
        const firstOpen = d.item_order.findIndex((id) => !d.answers[String(id)]);
        setIdx(at >= 0 ? at : firstOpen >= 0 ? firstOpen : "submit");
      })
      .catch((e) => setError(e.message));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [aid]);

  const items = useMemo(() => new Map((data?.items ?? []).map((it) => [it.id, it])), [data]);
  const itemId = data && typeof idx === "number" ? data.item_order[idx] : null;
  const item: StudentItem | undefined = itemId !== null ? items.get(itemId) : undefined;

  // 항목에 들어갈 때 입력 복원: 화면 이동 중 보관분 → 세션 만료 시 보관분 → 서버에 저장된 답
  useEffect(() => {
    if (!data || itemId === null) return;
    const saved = data.answers[String(itemId)];
    const restored = pending.current[itemId] ?? readDraft(aid, itemId) ?? (saved ? { judgement: saved.judgement, tag: saved.tag, slots: { ...saved.slots } } : EMPTY);
    setForm(restored);
    takeSeconds();
    setParams({ item: String(itemId) }, { replace: true });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data, itemId]);

  // 401이면 작성 중 입력을 보관
  useEffect(() => {
    if (itemId === null) return;
    setBeforeUnauthorized(() => storage.set(draftKey(aid, itemId), JSON.stringify(formRef.current)));
    return () => setBeforeUnauthorized(null);
  }, [aid, itemId]);

  if (error) return <p className="error">{error}</p>;
  if (!data || !tpls || idx === null) return <p className="muted">불러오는 중…</p>;

  const total = data.item_order.length;
  const answeredCount = data.item_order.filter((id) => data.answers[String(id)]).length;
  const tpl = form.tag && form.judgement !== null ? findTemplate(tpls.templates, form.tag, form.judgement) : undefined;
  const complete = isComplete(form, tpl);
  const overdue = new Date(data.due_at) < new Date();

  function go(next: number | "submit") {
    if (itemId !== null) pending.current[itemId] = formRef.current;
    setError("");
    setIncomplete(null);
    setIdx(next);
    window.scrollTo(0, 0);
  }

  async function saveAndGo(next: number | "submit") {
    if (itemId === null || !tpl || form.judgement === null || !form.tag) return;
    setSaving(true);
    setError("");
    try {
      await api(`/student/assignments/${aid}/answers/${itemId}`, {
        method: "PUT",
        json: { judgement: form.judgement, tag: form.tag, slots: pick(form.slots, Object.keys(tpl.slots)), duration_sec: takeSeconds() },
      });
      storage.set(draftKey(aid, itemId), null);
      delete pending.current[itemId];
      setData({ ...data!, answers: { ...data!.answers, [String(itemId)]: { judgement: form.judgement, tag: form.tag, slots: form.slots, saved_at: new Date().toISOString() } } });
      go(next);
    } catch (e) {
      if (e instanceof ApiError && e.status === 409) navigate(`/s/a/${aid}/result`, { replace: true });
      else setError(e instanceof Error ? e.message : "저장하지 못했어요");
    } finally {
      setSaving(false);
    }
  }

  async function submit() {
    setSaving(true);
    setError("");
    try {
      await api(`/student/assignments/${aid}/submit`, { method: "POST" });
      navigate(`/s/a/${aid}/result`, { replace: true });
    } catch (e) {
      if (e instanceof ApiError && e.status === 400) setIncomplete(e.body.incomplete_item_ids ?? []);
      else if (e instanceof ApiError && e.status === 409) navigate(`/s/a/${aid}/result`, { replace: true });
      else setError(e instanceof Error ? e.message : "제출하지 못했어요");
    } finally {
      setSaving(false);
    }
  }

  const header = (
    <div className="solve-head">
      <div className="row between">
        <strong>{data.title}</strong>
        <span className="small muted">마감 {fmtDateTime(data.due_at)}</span>
      </div>
      <div className="progress" role="progressbar" aria-valuemin={0} aria-valuemax={total} aria-valuenow={answeredCount}>
        <div style={{ width: `${(answeredCount / total) * 100}%` }} />
      </div>
      <div className="progress-meta">
        <span>{answeredCount} / {total} 완료</span>
        {typeof idx === "number" && <span>{idx + 1}번째 문항</span>}
      </div>
      {overdue && <div className="notice warn small">마감이 지났어요. 지금 제출하면 지각으로 기록돼요.</div>}
    </div>
  );

  // ----- 제출 화면 -----
  if (idx === "submit") {
    const open = incomplete ?? data.item_order.filter((id) => !data.answers[String(id)]);
    return (
      <div className="stack">
        {header}
        <div className="card stack">
          <h2 className="h2">제출하기</h2>
          {open.length > 0 ? (
            <>
              <p>아직 끝내지 않은 문항이 {open.length}개 있어요.</p>
              <div className="chips">
                {open.map((id) => (
                  <button key={id} className="btn" onClick={() => go(data.item_order.indexOf(id))}>
                    {data.item_order.indexOf(id) + 1}번 문항
                  </button>
                ))}
              </div>
            </>
          ) : (
            <>
              <p>{total}문항을 모두 마쳤어요.</p>
              <p className="notice">제출하면 답을 고칠 수 없어요. 제출 후에 정답과 해설을 볼 수 있어요.</p>
              <button className="btn primary block" onClick={submit} disabled={saving}>{saving ? "제출 중…" : "제출하기"}</button>
            </>
          )}
          {error && <p className="error">{error}</p>}
        </div>
        <button className="btn" onClick={() => go(total - 1)}>← 마지막 문항으로</button>
      </div>
    );
  }

  if (!item) return <p className="error">문항을 찾을 수 없어요.</p>;
  const passage = data.passages.find((p) => p.id === item.passage_id)!;
  const passageChoices = Object.fromEntries(data.items.filter((it) => it.passage_id === item.passage_id).map((it) => [it.no, it.choice]));

  function setJudgement(j: boolean) {
    setForm((f) => ({ ...f, judgement: j }));
  }

  return (
    <div className="stack">
      {header}
      <div className="solve-split">
        <aside className="card passage-pane" aria-label="지문">
          <p className="pane-label">{passage.source}</p>
          <p className="passage">
            <MarkedText text={passage.text} choices={passageChoices} underline="all" highlight={item.no} />
          </p>
        </aside>

        <div className="solve-panel">
          <div className="row between small muted">
            <span>{idx + 1} / {total}번째 문항 · {passage.source} {circled(item.no)}</span>
            <button className="btn link small only-narrow" onClick={() => setShowPassage(true)}>지문 전체 보기</button>
          </div>

          <div className="card sentence">
            <MarkedText text={item.sentence} choices={passageChoices} underline={[item.no]} highlight={item.no} />
          </div>

          <section className="stack-sm">
            <h3 className="step-title"><span className="step-no">1</span>밑줄 친 부분은 문법상</h3>
            <RadioGroup
              name="judgement"
              className="cols-2"
              options={[{ value: true, label: "맞다" }, { value: false, label: "틀리다" }]}
              value={form.judgement}
              onChange={setJudgement}
            />
          </section>

          {form.judgement !== null && (
            <section className="stack-sm">
              <h3 className="step-title"><span className="step-no">2</span>근거가 되는 문법 포인트</h3>
              <RadioGroup
                name="tag"
                className="tags"
                options={tpls.tags.map((t) => ({ value: t, label: t }))}
                value={form.tag}
                onChange={(t) => setForm((f) => ({ ...f, tag: t }))}
              />
            </section>
          )}

          {tpl && (
            <section className="stack-sm">
              <h3 className="step-title"><span className="step-no">3</span>근거 문장 완성하기</h3>
              <div className="card template-fill">
                <TemplateInputs template={tpl} values={form.slots} onChange={(name, v) => setForm((f) => ({ ...f, slots: { ...f.slots, [name]: v } }))} />
              </div>
            </section>
          )}

          {error && <p className="error">{error}</p>}

          <div className="row between nav-buttons">
            <button className="btn" disabled={idx === 0 || saving} onClick={() => (complete ? saveAndGo(idx - 1) : go(idx - 1))}>← 이전</button>
            <button className="btn primary" disabled={!complete || saving} onClick={() => saveAndGo(idx + 1 < total ? idx + 1 : "submit")}>
              {saving ? "저장 중…" : idx + 1 < total ? "다음 →" : "다 풀었어요 →"}
            </button>
          </div>
        </div>
      </div>

      {showPassage && (
        <div className="modal" role="dialog" aria-modal="true" onClick={() => setShowPassage(false)}>
          <div className="modal-body" onClick={(e) => e.stopPropagation()}>
            <div className="row between">
              <strong>{passage.source}</strong>
              <button className="btn link" onClick={() => setShowPassage(false)}>닫기</button>
            </div>
            <p className="passage">
              <MarkedText text={passage.text} choices={passageChoices} underline="all" highlight={item.no} />
            </p>
          </div>
        </div>
      )}
    </div>
  );
}

function pick(obj: Record<string, string>, keys: string[]): Record<string, string> {
  return Object.fromEntries(keys.map((k) => [k, (obj[k] ?? "").trim()]));
}

const SLOT = /\{(\w+)\}/g;

function TemplateInputs({ template, values, onChange }: { template: Template; values: Record<string, string>; onChange: (name: string, v: string) => void }) {
  const parts: React.ReactNode[] = [];
  let last = 0;
  for (const m of template.body.matchAll(SLOT)) {
    parts.push(<span key={`t${m.index}`}>{template.body.slice(last, m.index)}</span>);
    const name = m[1];
    const spec = template.slots[name];
    const v = values[name] ?? "";
    parts.push(
      Array.isArray(spec) ? (
        <select key={name} className={"slot" + (v ? "" : " empty")} value={v} onChange={(e) => onChange(name, e.target.value)}>
          <option value="">선택</option>
          {spec.map((o) => <option key={o} value={o}>{o}</option>)}
        </select>
      ) : (
        <input
          key={name}
          className={"slot" + (v.trim() ? "" : " empty")}
          value={v}
          onChange={(e) => onChange(name, e.target.value)}
          placeholder="입력"
          autoCapitalize="none"
          autoCorrect="off"
          spellCheck={false}
          size={Math.max(4, Math.min(v.length + 1, 30))}
        />
      ),
    );
    last = m.index! + m[0].length;
  }
  parts.push(<span key="end">{template.body.slice(last)}</span>);
  return <>{parts}</>;
}
