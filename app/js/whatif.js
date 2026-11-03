// What if controls, shared by both views: attendance change, special day, weather. Under the controls: the change
// in portions, then what it means dish by dish, for attendance and surplus risk, and the ingredients to have ready.
import { REMOTE, STATIC } from "./api.js";
import { setHTML } from "./fx.js";
import { icon } from "./icons.js";
import { resetOverrides, setOverrides, subscribe } from "./state.js";
import { WEATHER_TYPES, cap, esc, fmt } from "./util.js";

const SNAPSHOT_ONLY = STATIC && !REMOTE;   // no server to ask: the snapshot holds one setting at a time
const SPECIAL = { "": "None", special_day: "Holiday or campus event", exam_week: "Exam week", festival: "Festival" };
const FIRST_INGREDIENTS = 8;
let uid = 0;

const signed = (v, digits = 0) => `${v > 0 ? "+" : v < 0 ? "-" : ""}${digits ? Math.abs(v).toFixed(digits) : fmt(Math.abs(v))}`;
const tone = (v) => (v > 0 ? "up" : v < 0 ? "down" : "");
const kg = (v) => `${v >= 100 ? fmt(v) : v.toFixed(1)} kg`;
const ingredientName = (s) => cap(s.replace(/_/g, " "));
const atRisk = (counts) => (counts?.high ?? 0) + (counts?.medium ?? 0);

// A small bar for a change, scaled to the largest change in the table.
const bar = (v, max) => `<span class="wi-bar ${tone(v)}" aria-hidden="true"><i style="width:${max ? Math.max(4, (Math.abs(v) / max) * 100) : 0}%"></i></span>`;

function impactHTML(im, totals, difference, showAllIng) {
  const before = totals.recommended - difference.recommended, after = totals.recommended;
  const pct = before ? (100 * difference.recommended) / before : 0;
  const ing = im.ingredient_totals, att = im.attendance;
  const riskBefore = atRisk(im.risk.before), riskAfter = atRisk(im.risk.after);
  const kpis = [
    ["Portions to cook", `${fmt(before)} &rarr; ${fmt(after)}`, `${signed(difference.recommended)} (${signed(pct, 1)}%)`, tone(difference.recommended)],
    ["Expected attendance", `${fmt(att.before)} &rarr; ${fmt(att.after)}`, `${signed(att.after - att.before)} students`, tone(att.after - att.before)],
    ["Ingredients to have ready", `${kg(ing.before_kg)} &rarr; ${kg(ing.after_kg)}`,
      `${signed(ing.change_kg, 1)} kg${ing.packs_change ? `, ${signed(ing.packs_change)} supplier packs` : ""}`, tone(ing.change_kg)],
    ["Dishes at medium or high surplus risk", `${riskBefore} &rarr; ${riskAfter}`,
      riskAfter === riskBefore ? "no change" : `${signed(riskAfter - riskBefore)} dish${Math.abs(riskAfter - riskBefore) === 1 ? "" : "es"}`, tone(riskAfter - riskBefore)],
  ].map(([label, value, change, t]) => `<div class="wi-kpi"><span class="wi-kpi-l">${label}</span><span class="wi-kpi-v num">${value}</span>` +
    `<span class="wi-kpi-c ${t}">${change}</span></div>`).join("");

  const maxDish = Math.max(0, ...im.dishes.map((d) => Math.abs(d.change)));
  const dishRows = im.dishes.map((d) => `<tr><th scope="row">${esc(d.dish_name)}${d.risk_after && d.risk_after !== "low" ? ` <span class="pill ${d.risk_after}">${cap(d.risk_after)}</span>` : ""}</th>` +
    `<td class="num">${fmt(d.before)}</td><td class="num">${fmt(d.after)}</td>` +
    `<td class="num wi-chg ${tone(d.change)}">${bar(d.change, maxDish)}${signed(d.change)}${d.change_pct != null && d.change ? ` <small>(${signed(d.change_pct, 1)}%)</small>` : ""}</td></tr>`).join("");

  const shown = showAllIng ? im.ingredients : im.ingredients.slice(0, FIRST_INGREDIENTS);
  const maxIng = Math.max(0, ...im.ingredients.map((r) => Math.abs(r.change_kg)));
  const ingRows = shown.map((r) => `<tr><th scope="row">${esc(ingredientName(r.ingredient))}<small>${esc(r.storage_type ?? "")}</small></th>` +
    `<td class="num">${kg(r.before_kg)}</td><td class="num">${kg(r.after_kg)}</td>` +
    `<td class="num wi-chg ${tone(r.change_kg)}">${bar(r.change_kg, maxIng)}${signed(r.change_kg, 1)} kg` +
    `${r.change_pct_of_daily_use != null && r.change_kg ? ` <small title="Change as a share of a normal day's use of ${esc(ingredientName(r.ingredient))}">(${signed(r.change_pct_of_daily_use, 1)}% of a day)</small>` : ""}</td>` +
    `<td class="num">${r.pack_kg ? `${r.packs_before} &rarr; ${r.packs_after} <small>&times; ${fmt(r.pack_kg)} kg</small>` : "&ndash;"}</td></tr>`).join("");
  const more = im.ingredients.length - FIRST_INGREDIENTS;
  const scopeNote = im.scope === "core" ? " The tables cover the main dishes on the page; show all dishes to include the support dishes." : "";

  return `<div class="wi-kpis">${kpis}</div>
    <div class="wi-cols">
      <section class="wi-block"><h3>${icon("service")}Dish by dish</h3>
        <div class="tablewrap"><table class="wi-table"><thead><tr><th scope="col">Dish</th><th scope="col">Now</th><th scope="col">With this change</th><th scope="col">Change</th></tr></thead>
        <tbody>${dishRows}</tbody></table></div></section>
      <section class="wi-block"><h3>${icon("list")}Ingredients to have ready</h3>
        ${im.ingredients.length ? `<div class="tablewrap"><table class="wi-table"><thead><tr><th scope="col">Ingredient</th><th scope="col">Now</th><th scope="col">With this change</th><th scope="col">Change</th><th scope="col">Supplier packs</th></tr></thead>
        <tbody>${ingRows}</tbody></table></div>
        ${more > 0 ? `<button class="btn wi-more" type="button" data-wi="ingredients">${showAllIng ? "Show the biggest changes only" : `Show all ${im.ingredients.length} ingredients`}</button>` : ""}`
          : `<p class="hint">No recipe data for these dishes.</p>`}</section>
    </div>
    <p class="wi-note">${icon("info")}<span>${im.notes.map(esc).join(" ")}${scopeNote}</span></p>`;
}

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
    ${SNAPSHOT_ONLY ? `<p class="hint wi-demo">${icon("info")}Online demo: one setting at a time, for the next 7 days. Run FeedForward locally to combine settings.</p>` : ""}
    <div class="whatif-foot wi-result" id="${id}-foot" aria-live="polite" hidden></div>
    <div class="wi-impact" id="${id}-impact" hidden></div>`;
  const q = (s) => root.querySelector(`#${id}-${s}`);
  const att = q("att"), special = q("special"), weather = q("weather"), hint = q("att-hint"), foot = q("foot"), panel = q("impact");
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
    if (SNAPSHOT_ONLY) {   // the snapshot holds one setting at a time, so changing one resets the others
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
  let showAllIng = false, last = null;
  panel.addEventListener("click", (e) => {
    if (!e.target.closest("[data-wi=ingredients]") || !last) return;
    showAllIng = !showAllIng;
    setHTML(panel, impactHTML(last.whatif.impact, last.plan.totals, last.whatif.difference, showAllIng));
  });

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
    panel.hidden = !(active && s.whatif.impact);
    if (!active) { footKey = ""; last = null; showAllIng = false; return; }
    last = s;
    if (s.whatif.impact) setHTML(panel, impactHTML(s.whatif.impact, s.plan.totals, s.whatif.difference, showAllIng));
    const d = s.whatif.difference.recommended, now = s.plan.totals.recommended;
    const key = `${now}|${d}`;
    if (key === footKey) return;
    footKey = key;
    foot.innerHTML = `<span class="wi-delta ${d > 0 ? "up" : d < 0 ? "down" : ""}">${d >= 0 ? "+" : "-"}${fmt(Math.abs(d))}</span>` +
      `<span class="wi-text">Cooking would change from ${fmt(now - d)} to ${fmt(now)} portions (${d >= 0 ? "+" : "-"}${fmt(Math.abs(d))}). Not saved until you approve.</span>` +
      `<button class="btn" type="button" id="${id}-reset">${icon("back")}Back to the normal plan</button>`;
  });
}
