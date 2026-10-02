// fetch 래퍼 하나. 토큰은 localStorage에 두고 Authorization: Bearer로 보낸다(쿠키 미사용).

export const API_URL = (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, "") ?? "http://localhost:8000";

const TOKEN_KEY = "token";
const RETURN_KEY = "returnTo";

function storageGet(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

function storageSet(key: string, value: string | null) {
  try {
    if (value === null) localStorage.removeItem(key);
    else localStorage.setItem(key, value);
  } catch {
    /* 저장소를 못 쓰는 환경: 무시 */
  }
}

export const storage = { get: storageGet, set: storageSet };

export const getToken = () => storageGet(TOKEN_KEY);
export const setToken = (t: string | null) => storageSet(TOKEN_KEY, t);

export function takeReturnTo(): string | null {
  const v = storageGet(RETURN_KEY);
  storageSet(RETURN_KEY, null);
  return v;
}

export class ApiError extends Error {
  constructor(public status: number, public body: any) {
    super(typeof body?.detail === "string" ? body.detail : body?.detail?.message ?? `요청 실패 (${status})`);
  }
}

// 401 직전에 작성 중 입력을 보관하는 훅(풀이 화면이 등록)
let beforeUnauthorized: (() => void) | null = null;
export function setBeforeUnauthorized(fn: (() => void) | null) {
  beforeUnauthorized = fn;
}

type Options = { method?: string; json?: unknown; form?: FormData; signal?: AbortSignal };

export async function api<T = any>(path: string, opts: Options = {}): Promise<T> {
  const headers: Record<string, string> = {};
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  let body: BodyInit | undefined;
  if (opts.json !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(opts.json);
  } else if (opts.form) {
    body = opts.form;
  }
  const res = await fetch(API_URL + path, { method: opts.method ?? (body ? "POST" : "GET"), headers, body, signal: opts.signal });
  const text = await res.text();
  let data: any = null;
  try {
    data = text ? JSON.parse(text) : null;
  } catch {
    data = { detail: text };
  }
  if (res.status === 401 && !path.startsWith("/auth/")) {
    try {
      beforeUnauthorized?.();
    } finally {
      setToken(null);
      storageSet(RETURN_KEY, location.pathname + location.search);
      location.assign("/login");
    }
  }
  if (!res.ok) throw new ApiError(res.status, data);
  return data as T;
}
