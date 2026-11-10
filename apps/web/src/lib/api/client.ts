// Thin wrapper around the client generated from FastAPI's OpenAPI schema (schema.d.ts is generated: do not edit).
import createClient, { type Middleware } from "openapi-fetch";
import type { paths, components } from "./schema";

export type Schemas = components["schemas"];
export type JobCard = Schemas["JobCard"];
export type JobDetail = Schemas["JobDetail"];
export type SystemStatus = Schemas["SystemStatus"];
export type SettingsOut = Schemas["SettingsOut"];
export type UserOut = Schemas["UserOut"];
export type ConversationCard = Schemas["ConversationCard"];

const BASE = (import.meta as unknown as { env: Record<string, string> }).env.VITE_API_URL || "";
const TOKEN_KEY = "gigbid.token";

export const tokenStore = {
  get: () => { try { return localStorage.getItem(TOKEN_KEY); } catch { return null; } },
  set: (t: string | null) => { try { t ? localStorage.setItem(TOKEN_KEY, t) : localStorage.removeItem(TOKEN_KEY); } catch { /* private mode */ } },
};

export function newTraceId(): string {
  return Array.from(crypto.getRandomValues(new Uint8Array(16))).map((b) => b.toString(16).padStart(2, "0")).join("");
}

const auth: Middleware = {
  async onRequest({ request }) {
    const t = tokenStore.get();
    if (t) request.headers.set("Authorization", `Bearer ${t}`);
    if (!request.headers.get("X-Trace-Id")) request.headers.set("X-Trace-Id", newTraceId());
    return request;
  },
  async onResponse({ response }) {
    if (response.status === 401 && !response.url.includes("/auth/login")) {
      tokenStore.set(null);
      if (!location.pathname.startsWith("/login")) location.assign("/login");
    }
    return response;
  },
};

export const api = createClient<paths>({ baseUrl: BASE });
api.use(auth);

export class ApiError extends Error {
  constructor(public status: number, public detail: string) { super(detail); }
}

/** Unwrap an openapi-fetch result or throw a readable ApiError. */
export async function call<T>(p: Promise<{ data?: T; error?: unknown; response: Response }>): Promise<T> {
  const { data, error, response } = await p;
  if (error || !response.ok) {
    const e = error as { detail?: unknown; message?: string } | undefined;
    const d = typeof e?.detail === "string" ? e.detail : e?.message || JSON.stringify(e?.detail ?? e ?? response.statusText);
    throw new ApiError(response.status, d);
  }
  return data as T;
}

export type StreamEvent = { kind: string; node: string; payload: Record<string, unknown>; ts?: string; id?: string };

/** Server-Sent Events over fetch (EventSource cannot send the Authorization header). Resumes with Last-Event-ID. */
export async function streamRun(runId: string, onEvent: (e: StreamEvent) => void, signal: AbortSignal): Promise<Record<string, unknown> | null> {
  let lastId = "0";
  for (let attempt = 0; attempt < 20 && !signal.aborted; attempt++) {
    try {
      const res = await fetch(`${BASE}/api/runs/${runId}/stream`, {
        headers: { Authorization: `Bearer ${tokenStore.get()}`, "Last-Event-ID": lastId, Accept: "text/event-stream" }, signal,
      });
      if (!res.ok || !res.body) throw new Error(`stream ${res.status}`);
      const reader = res.body.getReader();
      const dec = new TextDecoder();
      let buf = "";
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += dec.decode(value, { stream: true }).replace(/\r\n/g, "\n"); // sse-starlette uses CRLF
        let idx;
        while ((idx = buf.indexOf("\n\n")) >= 0) {
          const block = buf.slice(0, idx); buf = buf.slice(idx + 2);
          let ev = "message", data = "", id = "";
          for (const line of block.split(/\r?\n/)) {
            if (line.startsWith("event:")) ev = line.slice(6).trim();
            else if (line.startsWith("data:")) data += line.slice(5).trim();
            else if (line.startsWith("id:")) id = line.slice(3).trim();
          }
          if (!data) continue;
          if (id) lastId = id;
          const parsed = JSON.parse(data);
          if (ev === "end") return parsed;
          onEvent({ ...parsed, id });
        }
      }
    } catch (e) {
      if (signal.aborted) return null;
      await new Promise((r) => setTimeout(r, 1500));
    }
  }
  return null;
}
