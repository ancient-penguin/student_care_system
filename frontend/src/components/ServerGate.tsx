// 앱이 열리면 즉시 /health를 호출해 잠든 서버와 DB를 깨운다.
// 2초 안에 응답이 없으면 안내를 띄우고, 백오프로 최대 약 90초 재시도한다.
import { useEffect, useState, type ReactNode } from "react";
import { API_URL } from "../api";

const SHOW_NOTICE_AFTER = 2000;
const GIVE_UP_AFTER = 90_000;

export function ServerGate({ children }: { children: ReactNode }) {
  const [state, setState] = useState<"checking" | "waking" | "ready" | "failed">("checking");
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;
    const started = Date.now();
    const notice = setTimeout(() => !cancelled && setState((s) => (s === "checking" ? "waking" : s)), SHOW_NOTICE_AFTER);

    async function run() {
      let delay = 1000;
      while (!cancelled) {
        try {
          const ctrl = new AbortController();
          const t = setTimeout(() => ctrl.abort(), 20_000);
          const res = await fetch(API_URL + "/health", { signal: ctrl.signal });
          clearTimeout(t);
          if (res.ok) {
            if (!cancelled) setState("ready");
            return;
          }
        } catch {
          /* 아직 깨어나는 중 */
        }
        if (Date.now() - started > GIVE_UP_AFTER) {
          if (!cancelled) setState("failed");
          return;
        }
        await new Promise((r) => setTimeout(r, delay));
        delay = Math.min(delay * 2, 8000);
      }
    }
    run();
    return () => {
      cancelled = true;
      clearTimeout(notice);
    };
  }, [attempt]);

  if (state === "ready") return <>{children}</>;
  if (state === "checking") return null;
  return (
    <div className="center-screen">
      {state === "waking" ? (
        <>
          <div className="spinner" aria-hidden />
          <p>서버 준비 중…</p>
          <p className="muted small">잠시 쉬고 있던 서버를 깨우고 있어요. 최대 1분 정도 걸릴 수 있어요.</p>
        </>
      ) : (
        <>
          <p>서버에 연결하지 못했어요.</p>
          <button className="btn primary" onClick={() => { setState("checking"); setAttempt((a) => a + 1); }}>
            다시 시도
          </button>
        </>
      )}
    </div>
  );
}
