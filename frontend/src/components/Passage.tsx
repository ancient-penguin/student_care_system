// 지문 텍스트의 [[n]] 마커를 React 요소로 바꾼다. HTML 문자열 렌더링(dangerouslySetInnerHTML)은 쓰지 않는다.
import type { ReactNode } from "react";
import { circled } from "../format";

const MARKER = /\[\[(\d+)\]\]/g;

type Props = {
  text: string;
  choices: Record<number, string>;
  /** 밑줄로 보여줄 항목. "all"이면 전부 */
  underline: number[] | "all";
  /** 강조할 항목(현재 풀이 중) */
  highlight?: number;
};

export function MarkedText({ text, choices, underline, highlight }: Props) {
  const parts: ReactNode[] = [];
  let last = 0;
  for (const m of text.matchAll(MARKER)) {
    const no = Number(m[1]);
    parts.push(text.slice(last, m.index));
    const choice = choices[no] ?? "";
    if (underline === "all" || underline.includes(no)) {
      parts.push(
        <span key={m.index} className={"mark" + (highlight === no ? " mark-current" : "")}>
          <span className="mark-no">{circled(no)}</span>
          <u>{choice}</u>
        </span>,
      );
    } else {
      parts.push(choice);
    }
    last = m.index! + m[0].length;
  }
  parts.push(text.slice(last));
  return <>{parts}</>;
}
