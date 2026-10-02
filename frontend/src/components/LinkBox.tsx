import { useState } from "react";
import { copyText, loginLink } from "../format";

/** 평문 링크는 발급 직후 한 번만 보여준다. */
export function LinkBox({ name, token, onClose }: { name: string; token: string; onClose: () => void }) {
  const [copied, setCopied] = useState<boolean | null>(null);
  const link = loginLink(token);
  return (
    <div className="notice stack-sm">
      <strong>{name} 학생 로그인 링크</strong>
      <code className="link-text">{link}</code>
      <div className="row wrap">
        <button className="btn primary small" onClick={async () => setCopied(await copyText(link))}>링크 복사</button>
        <button className="btn small" onClick={onClose}>닫기</button>
        {copied === true && <span className="small">복사했어요</span>}
        {copied === false && <span className="small error">복사 실패 — 위 주소를 길게 눌러 복사하세요</span>}
      </div>
      <span className="small muted">이 링크는 지금 한 번만 표시됩니다. 잃어버리면 '링크 재발급'으로 새로 만드세요.</span>
    </div>
  );
}
