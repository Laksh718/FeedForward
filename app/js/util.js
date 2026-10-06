// Small helpers shared by every view.

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
  tip.style.left = `${Math.min(evt.clientX + 14, window.innerWidth - 250)}px`;
  tip.style.top = `${evt.clientY + 14}px`;
}
export function hideTip() { if (tip) tip.hidden = true; }
