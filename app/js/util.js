// Small helpers shared by every view.
import { icon } from "./icons.js";

export const fmt = (n) => Math.round(n).toLocaleString("en-US");
export const cap = (s) => s.charAt(0).toUpperCase() + s.slice(1);
export const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

export const SLOTS = ["breakfast", "lunch", "snacks", "dinner"];
export const WEATHER_TYPES = ["Mist", "Haze", "Fair", "Partly Cloudy", "Fog", "Smoke", "Showers in the Vicinity",
  "Drizzle", "Light Drizzle", "Light Rain", "Rain", "Heavy Rain", "Thunder", "Light Rain with Thunder"];

export const debounce = (fn, ms = 350) => {
  let t;
  return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); };
};

export const dayMs = 86400000;
export const parseDay = (iso) => new Date(`${iso}T00:00:00`);
// Local calendar date as YYYY-MM-DD (toISOString would shift it by the time zone).
export const isoDay = (d) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
export const weekdayName = (iso) => parseDay(iso).toLocaleDateString("en-US", { weekday: "long" });
export const shortDate = (iso) => parseDay(iso).toLocaleDateString("en-US", { weekday: "short", day: "numeric", month: "short" });

// Round tick values for a chart axis covering lo..hi.
export function niceTicks(lo, hi, count = 4) {
  const raw = Math.max(hi - lo, 1) / count;
  const mag = 10 ** Math.floor(Math.log10(raw));
  const norm = raw / mag;
  const step = (norm <= 1 ? 1 : norm <= 2 ? 2 : norm <= 5 ? 5 : 10) * mag;
  const ticks = [];
  for (let v = Math.floor(lo / step) * step; v <= Math.ceil(hi / step) * step + 1e-9; v += step) ticks.push(v);
  return ticks;
}

export function riskLabel(level, long = false) {
  const word = cap(level);
  return long ? `${word} surplus risk` : word;
}

// Groups consecutive true flags: [false,true,true,false] -> [[1,2]]
export function runs(flags) {
  const out = [];
  flags.forEach((f, i) => {
    if (f && (i === 0 || !flags[i - 1])) out.push([i, i]);
    else if (f) out[out.length - 1][1] = i;
  });
  return out;
}

// A shared tooltip element for charts.
let tip;
export function showTip(evt, html) {
  tip = tip || Object.assign(document.body.appendChild(document.createElement("div")), { className: "tooltip" });
  tip.innerHTML = html;
  tip.hidden = false;
  tip.style.left = `${Math.max(8, Math.min(evt.clientX + 16, window.innerWidth - tip.offsetWidth - 12))}px`;
  tip.style.top = `${Math.min(evt.clientY + 16, window.innerHeight - tip.offsetHeight - 12)}px`;
}
export function hideTip() { if (tip) tip.hidden = true; }

// Where an answer came from, in plain words (shown under copilot answers that did not come from the language model).
export const SOURCE_NOTE = {
  template: "Standard wording from the figures on this page (language model not used).",
  demo: "Online demo note (the copilot itself runs on the FeedForward server).",
};

// The note for one answer, saying why the standard wording was used when the language model was not.
export function sourceNote(m) {
  if (m.source !== "template" || !m.reason) return SOURCE_NOTE[m.source] ?? "";
  if (m.reason.includes("could not be reached")) return "Standard wording from the figures on this page: the language model was busy or unreachable, so ask again in a moment for its wording.";
  if (m.reason.includes("not in the data")) return "Standard wording from the figures on this page: the language model's answer quoted a figure that is not in the data, so it was not used.";
  if (m.reason.includes("not set")) return "Standard wording from the figures on this page (no language model key on this server).";
  return SOURCE_NOTE.template;
}

// ---------- plan status, shown the same way on every view

export function reviewStatus(r) {
  if (!r) return { key: "pending", label: "Waiting for review", short: "Waiting", icon: "clock" };
  if (r.decision === "approve") {
    return r.automatic ? { key: "approve", label: "Approved automatically", short: "Auto approved", icon: "auto" }
      : { key: "approve", label: "Approved", short: "Approved", icon: "check" };
  }
  return { key: "send_back", label: "Sent back", short: "Sent back", icon: "back" };
}

export const statusPill = (r, short = false) => {
  const s = reviewStatus(r);
  return `<span class="status-pill ${s.key}">${icon(s.icon)}${short ? s.short : s.label}</span>`;
};

// What kind of plan was approved: a rare event plan, a what if, or the plain forecast.
export function planKind(r) {
  if (!r) return "";
  if (r.note && r.note.startsWith("Rare event plan:")) return r.note.replace("Rare event plan: ", "").replace(/\.$/, "") + " plan";
  if (r.overrides && Object.keys(r.overrides).length) return "What if plan";
  return "";
}

// "5 Nov, 21:03" from an ISO timestamp.
export const whenText = (iso) => {
  if (!iso) return "";
  const d = new Date(iso);
  return `${d.toLocaleDateString("en-US", { day: "numeric", month: "short" })}, ${d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" })}`;
};

export const SLOT_ICON = { breakfast: "sun", lunch: "service", snacks: "leaf", dinner: "star" };
