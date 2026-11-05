// API client. Every failure becomes an ApiError with a plain message and a way to fix it.
import { staticRequest } from "./static-api.js";

export class ApiError extends Error {
  constructor(status, message, fix) {
    super(message);
    this.status = status;
    this.fix = fix;
  }
}

export const auth = { pin: "", token: "" };   // X-Admin-Pin once the Daily log is unlocked; the account session as a Bearer token

// Static site (GitHub Pages): scripts/build_static_site.py adds <meta name="feedforward-mode" content="static">
// and a prebuilt snapshot under data/. Served by uvicorn, the meta tag is absent and every call goes to /api.
export const STATIC = document.querySelector('meta[name="feedforward-mode"]')?.content === "static";

// On the static site, a deployed FeedForward server (feedforward-api meta tag) answers what the snapshot cannot:
// combined what ifs and other dates, free copilot questions, saved approvals and the Daily log. Add ?remote=off to
// the address to use the snapshot only.
export const REMOTE = STATIC && new URLSearchParams(location.search).get("remote") !== "off"
  ? (document.querySelector('meta[name="feedforward-api"]')?.content || "").replace(/\/+$/, "")
  : "";
const REMOTE_TIMEOUT_MS = 90000;   // a sleeping free server can take about a minute to wake
// A free host restarts after every deploy and sleeps when unused: while it wakes it drops the connection or its proxy
// answers 502, 503 or 504. Those calls are tried again for about two minutes before the page shows an error.
const WAKE_WAITS_MS = [2000, 3000, 5000, 8000, 12000, 15000, 20000, 25000, 30000];
const WAKING = new Set([0, 502, 503, 504]);
let wakeNotice = 0;

async function fetchApi(base, path, options, asText, unreachable) {
  if (!base) return fetchOnce(base, path, options, asText, unreachable);
  for (let i = 0; ; i++) {
    try {
      return await fetchOnce(base, path, options, asText, unreachable);
    } catch (e) {
      if (!e.waking || i >= WAKE_WAITS_MS.length) throw e;
      if (Date.now() - wakeNotice > 60000) {
        wakeNotice = Date.now();
        import("./fx.js").then(({ toast }) => toast("Waking the FeedForward server. This can take up to a minute; the page carries on by itself.", "warn", 6000));
      }
      await new Promise((r) => setTimeout(r, WAKE_WAITS_MS[i]));
    }
  }
}

async function fetchOnce(base, path, options, asText, unreachable) {
  let res;
  const ctrl = new AbortController();
  const timer = base ? setTimeout(() => ctrl.abort(), REMOTE_TIMEOUT_MS) : null;
  try {
    res = await fetch(`${base}/api${path}`, { ...options, signal: ctrl.signal,
      headers: { ...(options.headers || {}), ...(auth.pin ? { "X-Admin-Pin": auth.pin } : {}), ...(auth.token ? { Authorization: `Bearer ${auth.token}` } : {}) } });
  } catch {
    throw Object.assign(new ApiError(0, ...unreachable), { waking: true });
  } finally {
    clearTimeout(timer);
  }
  if (res.ok && asText) return res.text();
  const body = await res.json().catch(() => ({}));
  if (res.ok) return body;
  const d = body.detail;
  if (base && WAKING.has(res.status) && !(d && typeof d === "object")) {   // the host's proxy, not FeedForward, answered
    throw Object.assign(new ApiError(res.status, ...unreachable), { waking: true });
  }
  if (d && typeof d === "object" && !Array.isArray(d)) { const e = new ApiError(res.status, d.message, d.fix); e.fields = d.fields; throw e; }
  if (res.status === 404) throw new ApiError(404, "This feature is not available on the server yet.", "Update the server code and restart it.");
  throw new ApiError(res.status, "The server could not answer this request.", "Try again, or check the server window for the error.");
}

const LOCAL_DOWN = ["Could not reach the FeedForward server.",
  "Start it with: uvicorn api.main:app --reload (from the project folder), then refresh this page."];
const REMOTE_DOWN = ["Could not reach the FeedForward server.",
  "It sleeps when nobody has used it for a while and takes up to a minute to wake. Try again in a moment."];

// The server is unreachable or failing (as opposed to answering "no" to a valid request).
const serverDown = (e) => e.status === 0 || e.status >= 500;
// Calls that should reach the server whenever it is up: answers there are live and saved for everyone.
const serverFirst = (method, path) => ["/chat", "/review", "/plans/review", "/events/approve"].includes(path)
  || ["/admin", "/activity", "/auth", "/accounts", "/knowledge", "/donations"].some((p) => path.startsWith(p));

async function staticWithServer(path, options, asText) {
  const url = new URL(path, "https://feedforward.invalid");
  const method = options.method || "GET";
  const local = () => staticRequest(method, url.pathname, Object.fromEntries(url.searchParams), options.body ? JSON.parse(options.body) : {});
  const remote = () => fetchApi(REMOTE, path, options, asText, REMOTE_DOWN);
  if (!REMOTE) return local();
  if (serverFirst(method, url.pathname)) {
    try {
      return await remote();
    } catch (e) {
      if (serverDown(e) && !url.pathname.startsWith("/admin")) return local();   // copilot and approvals still answer offline
      throw e;
    }
  }
  try {
    return await local();
  } catch (e) {
    if (e.miss) return remote();   // not in the snapshot (a combined what if, another week, the catalogue): ask the server
    throw e;
  }
}

async function request(path, options = {}, asText = false) {
  return STATIC ? staticWithServer(path, options, asText) : fetchApi("", path, options, asText, LOCAL_DOWN);
}

// Start waking the deployed server as soon as the page opens, so it is ready by the time someone needs it.
if (REMOTE) fetch(`${REMOTE}/api/health`, { mode: "cors" }).catch(() => {});

const query = (params) => {
  const q = new URLSearchParams(Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== ""));
  return q.toString() ? `?${q}` : "";
};

export const api = {
  get: (path, params = {}) => request(path + query(params)),
  post: (path, body) => request(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
  del: (path, body) => request(path, { method: "DELETE", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
  text: (path, params = {}) => request(path + query(params), {}, true),
};
