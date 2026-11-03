// What if controls, shared by both views: attendance change, special day, weather.
import { STATIC } from "./api.js";
import { icon } from "./icons.js";
import { resetOverrides, setOverrides, subscribe } from "./state.js";
import { WEATHER_TYPES, esc, fmt } from "./util.js";

const SPECIAL = { "": "None", special_day: "Holiday or campus event", exam_week: "Exam week", festival: "Festival" };
let uid = 0;

export function mountWhatIf(root, { gridClass, fieldClass = "field", showSummary = true }) {
  const id = `wi${uid++}`;
  root.innerHTML = `
    <div class="${gridClass}">
      <div class="${fieldClass} wi-att"><label for="${id}-att">Attendance change</label>
        <input id="${id}-att" type="range" min="-30" max="30" step="5" value="0">
        <div class="wi-scale" aria-hidden="true"><span>-30%</span><span>0</span><span>+30%</span></div>
        <div class="hint" id="${id}-att-hint" aria-live="polite">0% from the usual</div></div>
      <div class="${fieldClass}"><label for="${id}-special">Special day</label>
        <select id="${id}-special">${Object.entries(SPECIAL).map(([v, t]) => `<option value="${v}">${t}</option>`).join("")}</select></div>
      <div class="${fieldClass}"><label for="${id}-weather">Weather</label>
        <select id="${id}-weather"><option value="">As forecast</option><option value="Dry">Dry</option>
        ${WEATHER_TYPES.map((w) => `<option value="${esc(w)}">${esc(w)}</option>`).join("")}</select></div>
    </div>
    ${STATIC ? `<p class="hint wi-demo">${icon("info")}Online demo: one setting at a time, for the next 7 days. Run FeedForward locally to combine settings.</p>` : ""}
    <div class="whatif-foot wi-result" id="${id}-foot" aria-live="polite" hidden></div>`;
  const q = (s) => root.querySelector(`#${id}-${s}`);
  const att = q("att"), special = q("special"), weather = q("weather"), hint = q("att-hint"), foot = q("foot");
  const label = (v) => (Number(v) === 0 ? "0% from the usual" : `${v > 0 ? "+" : ""}${v}% from the usual`);
  // Fill the track from 0% to the chosen change, so the direction reads at a glance.
  const paint = () => {
    const pct = ((Number(att.value) + 30) / 60) * 100;
    att.style.setProperty("--lo", `${Math.min(50, pct)}%`);
    att.style.setProperty("--hi", `${Math.max(50, pct)}%`);
    hint.textContent = label(att.value);
    hint.classList.toggle("on", Number(att.value) !== 0);
  };

  const apply = (changed) => {
    if (STATIC) {   // the demo snapshot holds one setting at a time, so changing one resets the others
      if (changed !== att) att.value = 0;
      if (changed !== special) special.value = "";
      if (changed !== weather) weather.value = "";
      paint();
    }
    const o = {};
    if (Number(att.value) !== 0) o.attendance_change_pct = Number(att.value);
    if (special.value) o[special.value] = true;
    if (weather.value) o.weather_type = weather.value;
    return setOverrides(o);
  };
  att.addEventListener("input", paint);
  att.addEventListener("change", () => apply(att));
  special.addEventListener("change", () => apply(special));
  weather.addEventListener("change", () => apply(weather));
  foot.addEventListener("click", (e) => { if (e.target.closest("button")) resetOverrides(); });

  let footKey = "";
  subscribe((s) => {
    const o = s.overrides;
    if (document.activeElement !== att) att.value = o.attendance_change_pct ?? 0;
    paint();
    special.value = o.special_day ? "special_day" : o.exam_week ? "exam_week" : o.festival ? "festival" : "";
    weather.value = o.weather_type ?? "";
    [special, weather].forEach((sel) => sel.classList.toggle("on", Boolean(sel.value)));
    if (!showSummary) return;
    const active = Object.keys(o).length > 0 && s.whatif && s.plan;
    foot.hidden = !active;
    if (!active) { footKey = ""; return; }
    const d = s.whatif.difference.recommended, now = s.plan.totals.recommended;
    const key = `${now}|${d}`;
    if (key === footKey) return;
    footKey = key;
    foot.innerHTML = `<span class="wi-delta ${d > 0 ? "up" : d < 0 ? "down" : ""}">${d >= 0 ? "+" : "-"}${fmt(Math.abs(d))}</span>` +
      `<span class="wi-text">Cooking would change from ${fmt(now - d)} to ${fmt(now)} portions (${d >= 0 ? "+" : "-"}${fmt(Math.abs(d))}). Not saved until you approve.</span>` +
      `<button class="btn" type="button" id="${id}-reset">${icon("back")}Back to the normal plan</button>`;
  });
}
