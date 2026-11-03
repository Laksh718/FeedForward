// API client. Every failure becomes an ApiError with a plain message and a way to fix it.
import { staticRequest } from "./static-api.js";

export class ApiError extends Error {
  constructor(status, message, fix) {
    super(message);
    this.status = status;
    this.fix = fix;
  }
}

export const auth = { pin: "" };   // sent as X-Admin-Pin on every request once the admin has unlocked the Daily log

// Static demo (GitHub Pages): scripts/build_static_site.py adds <meta name="feedforward-mode" content="static">
// and a prebuilt snapshot under data/, so there is no server to call. Served by uvicorn, the meta tag is absent.
export const STATIC = document.querySelector('meta[name="feedforward-mode"]')?.content === "static";

async function request(path, options = {}, asText = false) {
  if (STATIC) {
    const url = new URL(path, "https://feedforward.invalid");
    return staticRequest(options.method || "GET", url.pathname, Object.fromEntries(url.searchParams),
      options.body ? JSON.parse(options.body) : {});
  }
  let res;
  try {
    res = await fetch(`/api${path}`, { ...options, headers: { ...(options.headers || {}), ...(auth.pin ? { "X-Admin-Pin": auth.pin } : {}) } });
  } catch {
    throw new ApiError(0, "Could not reach the FeedForward server.",
      "Start it with: uvicorn api.main:app --reload (from the project folder), then refresh this page.");
  }
  if (res.ok && asText) return res.text();
  const body = await res.json().catch(() => ({}));
  if (res.ok) return body;
  const d = body.detail;
  if (d && typeof d === "object" && !Array.isArray(d)) { const e = new ApiError(res.status, d.message, d.fix); e.fields = d.fields; throw e; }
  if (res.status === 404) throw new ApiError(404, "This feature is not available on the server yet.", "Update the server code and restart it.");
  throw new ApiError(res.status, "The server could not answer this request.", "Try again, or check the server window for the error.");
}

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
