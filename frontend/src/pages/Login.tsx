import { useEffect, useRef, useState, type FormEvent } from "react";
import { useNavigate } from "react-router";
import { api, ApiError, takeReturnTo } from "../api";
import { useAuth } from "../auth";
import type { User } from "../types";

type LoginRes = { token: string; user: User };

export default function Login() {
  const { signIn } = useAuth();
  const navigate = useNavigate();
  const [mode, setMode] = useState<"student" | "teacher">("student");
  const [linkState, setLinkState] = useState<"none" | "trying" | "invalid">("none");
  const [code, setCode] = useState("");
  const [secret, setSecret] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const tried = useRef(false);

  function done(res: LoginRes) {
    signIn(res.token, res.user);
    const back = takeReturnTo();
    const home = res.user.role === "teacher" ? "/t" : "/s";
    navigate(back && back.startsWith(home) ? back : home, { replace: true });
  }

  // 개인 로그인 링크: /login#<토큰> → POST로 교환하고 주소창에서 토큰을 지운다.
  useEffect(() => {
    if (tried.current) return;
    tried.current = true;
    const token = location.hash.slice(1);
    if (!token) return;
    history.replaceState(null, "", location.pathname);
    setLinkState("trying");
    api<LoginRes>("/auth/link-login", { json: { token } })
      .then(done)
      .catch(() => setLinkState("invalid"));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setError("");
    setBusy(true);
    try {
      const res = mode === "student"
        ? await api<LoginRes>("/auth/code-login", { json: { code, pin: secret } })
        : await api<LoginRes>("/auth/teacher-login", { json: { code, password: secret } });
      done(res);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "연결에 실패했어요. 잠시 뒤 다시 시도하세요.");
    } finally {
      setBusy(false);
    }
  }

  if (linkState === "trying") {
    return <div className="center-screen"><div className="spinner" aria-hidden /><p>로그인 중…</p></div>;
  }

  return (
    <div className="page narrow">
      <h1 className="title">문법 숙제</h1>
      {linkState === "invalid" && (
        <div className="notice warn">링크가 만료되었습니다. 선생님께 새 링크를 요청하세요.<br />또는 아래에 코드와 PIN을 입력하세요.</div>
      )}
      <form className="card stack" onSubmit={submit}>
        <div className="seg" role="tablist">
          {(["student", "teacher"] as const).map((m) => (
            <button
              key={m}
              type="button"
              role="tab"
              aria-selected={mode === m}
              className={"btn" + (mode === m ? " selected" : "")}
              onClick={() => { setMode(m); setError(""); setSecret(""); }}
            >
              {m === "student" ? "학생" : "선생님"}
            </button>
          ))}
        </div>
        <label className="field">
          <span>{mode === "student" ? "학생 코드" : "선생님 코드"}</span>
          <input value={code} onChange={(e) => setCode(e.target.value)} autoCapitalize="none" autoComplete="username" required />
        </label>
        <label className="field">
          <span>{mode === "student" ? "PIN (숫자 4~6자리)" : "비밀번호"}</span>
          <input
            type="password"
            value={secret}
            onChange={(e) => setSecret(e.target.value)}
            inputMode={mode === "student" ? "numeric" : undefined}
            autoComplete="current-password"
            required
          />
        </label>
        {error && <p className="error">{error}</p>}
        <button className="btn primary block" disabled={busy}>{busy ? "확인 중…" : "로그인"}</button>
      </form>
    </div>
  );
}
