// 틀의 {slot}을 값으로 치환한 완성 문장. 치환된 값은 강조한다.
import type { ReactNode } from "react";
import type { Template } from "../types";

const SLOT = /\{(\w+)\}/g;

export function findTemplate(templates: Template[], tag: string, judgement: boolean): Template | undefined {
  const j = judgement ? "right" : "wrong";
  return templates.find((t) => t.tag === tag && t.judgement === j);
}

type Props = {
  template: Template | undefined;
  values: Record<string, string>;
  /** 선택형 슬롯 일치 여부(선생님 화면) */
  check?: Record<string, boolean> | null;
};

export function FilledSentence({ template, values, check }: Props) {
  if (!template) return <span className="muted">(틀 없음)</span>;
  const parts: ReactNode[] = [];
  let last = 0;
  for (const m of template.body.matchAll(SLOT)) {
    parts.push(template.body.slice(last, m.index));
    const name = m[1];
    const ok = check?.[name];
    parts.push(
      <strong key={m.index} className={"fill" + (ok === false ? " fill-bad" : ok === true ? " fill-ok" : "")}>
        {values[name] || "____"}
      </strong>,
    );
    last = m.index! + m[0].length;
  }
  parts.push(template.body.slice(last));
  return <span className="filled">{parts}</span>;
}
