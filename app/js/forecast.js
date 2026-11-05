// View: Forecast. What the model expects for the next 7 days of one meal slot: a card per day, the week next to the
// demand of the week before, every dish on every day, and the detail of the day picked. It shows predictions only;
// decisions are made on the Service board and on Plans, and their status shows here.
import { api } from "./api.js";
import { bindChart, chartDesk } from "./charts.js";
import { liquid, replay, setHTML } from "./fx.js";
import { icon } from "./icons.js";
import { openPlan, state, subscribe } from "./state.js";
import { SLOTS, cap, esc, fmt, isoDay, parseDay, planKind, riskLabel, shortDate, statusPill } from "./util.js";

const shift = (iso, n) => { const d = parseDay(iso); d.setDate(d.getDate() + n); return isoDay(d); };
const RAIN = ["", "Light rain", "Rain", "Heavy rain"];

const SKELETON = `
  <header class="fc-top glass">
    <div class="fc-head"><p class="eyebrow">${icon("desk")}Forecast</p><h1 class="fc-title" id="fc-title">Forecast</h1>
      <p class="fc-sub">What the model expects for each of the next seven days, dish by dish, as a range. Pick a day to see its detail.</p></div>
    <div class="fc-tools">
      <div class="seg" id="fc-slot" role="group" aria-label="Meal slot">${SLOTS.map((s) => `<button type="button" data-slot="${s}" aria-pressed="false">${cap(s)}</button>`).join("")}</div>
      <div class="fc-week" role="group" aria-label="Choose the week">
        <button type="button" class="icon-btn" id="fc-prev" aria-label="Previous seven days">${icon("left")}</button>
        <span class="fc-week-label" id="fc-week-label"></span>
        <button type="button" class="icon-btn" id="fc-next" aria-label="Next seven days">${icon("right")}</button>
        <button type="button" class="btn btn-small" id="fc-now">From tomorrow</button>
      </div>
      <div class="seg" id="fc-scope" role="group" aria-label="Which dishes"><button type="button" data-scope="core" aria-pressed="true">Main dishes</button><button type="button" data-scope="all" aria-pressed="false">All dishes</button></div>
    </div>
  </header>
  <div id="fc-error"></div>
  <section class="fc-days" id="fc-days" aria-label="The next seven days"></section>
  <section class="dk-card glass" aria-labelledby="fc-chart-t">
    <div class="fc-card-head"><h2 id="fc-chart-t">${icon("desk")}Demand over the week</h2><div class="dishpick" id="fc-pick" role="group" aria-label="Choose a dish for the chart"></div></div>
    <div class="chart" id="fc-chart"></div>
    <div class="legend"><span><i style="background:#8AA094"></i>Wanted the week before</span><span><i class="swatch" style="background:linear-gradient(180deg,#6EE7B7,#99F6E4)"></i>Likely range</span>
      <span><i style="background:#0D2A1E"></i>Most likely</span><span><i style="background:#C8432A"></i>Recommended to cook</span><span class="legend-hint">Click a day to pick it</span></div>
  </section>
  <section class="dk-card glass" aria-labelledby="fc-matrix-t">
    <h2 id="fc-matrix-t">${icon("grid")}Every dish, every day</h2>
    <p class="dk-panel-note">Portions recommended to cook. A tinted cell has a medium or high surplus risk; a dash means the dish is not on that day's menu.</p>
    <div class="tablewrap" id="fc-matrix"></div>
  </section>
  <section class="dk-card glass" id="fc-detail" aria-labelledby="fc-detail-t">
    <div class="fc-card-head"><h2 id="fc-detail-t">The day</h2><div class="fc-detail-actions" id="fc-detail-actions"></div></div>
    <p class="fc-headline" id="fc-headline"></p>
    <div class="tablewrap" id="fc-table"></div>
    <div class="fc-risk" id="fc-risk"></div>
  </section>`;

function factBadges(f) {
  const out = [];
  if (f.festival) out.push(["star", "Festival"]);
  if (f.holiday) out.push(["star", "Holiday"]);
  if (f.exam_week) out.push(["book", "Exams"]); else if (f.formative_test) out.push(["book", "Tests"]);
  if (f.rain_level > 0) out.push(["rain", RAIN[f.rain_level] || "Rain"]);
  if (f.students_mostly_away) out.push(["users", "Many away"]);
  return out.map(([ic, t]) => `<span class="fc-fact">${icon(ic)}${t}</span>`).join("");
}

function dayCard(d, selected, i) {
  const t = d.totals;
  if (!t.recommended) {
    return `<button type="button" class="fc-day glass-lite empty-day ${d.date === selected ? "on" : ""}" style="--i:${i}" data-date="${d.date}">
      <span class="fc-day-name">${esc(d.weekday.slice(0, 3))} <b>${Number(d.date.slice(8))}</b></span><span class="fc-day-none">No menu for this meal</span></button>`;
  }
  const diff = t.usual_plan ? t.recommended - t.usual_plan : 0;
  const risky = (d.risk_counts?.high ?? 0) + (d.risk_counts?.medium ?? 0);
  return `<button type="button" class="fc-day glass-lite ${d.date === selected ? "on" : ""}" style="--i:${i}" data-date="${d.date}" aria-pressed="${d.date === selected}">
    <span class="fc-day-name">${esc(d.weekday.slice(0, 3))} <b>${Number(d.date.slice(8))}</b> ${esc(parseDay(d.date).toLocaleDateString("en-US", { month: "short" }))}</span>
    <span class="fc-day-big num">${fmt(t.recommended)}</span><span class="fc-day-unit">portions to cook</span>
    <span class="fc-day-range num">Likely ${fmt(t.p10)} to ${fmt(t.p90)}</span>
    ${diff ? `<span class="fc-day-delta ${diff > 0 ? "up" : "down"}">${diff > 0 ? "+" : "-"}${fmt(Math.abs(diff))} vs usual</span>` : `<span class="fc-day-delta">Same as usual</span>`}
    <span class="fc-day-meta">${icon("users")}${fmt(d.expected_attendance)} expected${risky ? ` <span class="risk-dot ${d.risk_counts.high ? "high" : "medium"}"></span>${risky} at risk` : ""}</span>
    <span class="fc-day-facts">${factBadges(d.facts || {})}</span>
    ${statusPill(d.review, true)}</button>`;
}

function matrix(data, selected) {
  const days = data.days;
  const head = `<th scope="col">Dish</th>` + days.map((d) => `<th scope="col" class="${d.date === selected ? "on" : ""}">${esc(d.weekday.slice(0, 3))}<small>${Number(d.date.slice(8))}</small></th>`).join("");
  const body = data.dishes.map((r) => `<tr><th scope="row">${esc(r.dish_name)}</th>` + days.map((d) => {
    const c = r.days[d.date];
    if (!c) return `<td class="none ${d.date === selected ? "on" : ""}">&ndash;</td>`;
    return `<td class="num risk-${c.surplus_risk} ${d.date === selected ? "on" : ""}" title="Likely ${fmt(c.p10)} to ${fmt(c.p90)}, most likely ${fmt(c.p50)}, usual plan ${c.usual_plan ? fmt(c.usual_plan) : "none"}, ${riskLabel(c.surplus_risk, true).toLowerCase()}">${fmt(c.recommended)}</td>`;
  }).join("") + "</tr>").join("");
  const total = `<tr class="total"><th scope="row">Total</th>${days.map((d) => `<td class="num ${d.date === selected ? "on" : ""}">${d.totals.recommended ? fmt(d.totals.recommended) : "&ndash;"}</td>`).join("")}</tr>`;
  return data.dishes.length ? `<table class="fc-matrix"><thead><tr>${head}</tr></thead><tbody>${body}${total}</tbody></table>`
    : `<div class="empty"><strong>No dishes on the menu for this meal in these days.</strong></div>`;
}

function detailTable(data, date, scope) {
  const rows = data.dishes.filter((r) => r.days[date]).map((r) => ({ name: r.dish_name, ...r.days[date] }));
  if (!rows.length) return `<div class="empty"><strong>No dishes are on the menu for this meal on this day.</strong>Pick another day above.</div>`;
  rows.sort((a, b) => b.recommended - a.recommended);
  const head = ["Dish", "Low end", "Most likely", "High end", "Usual plan", "Cook", "Surplus risk"].map((h) => `<th scope="col">${h}</th>`).join("");
  const body = rows.map((d) => `<tr><td>${esc(d.name)}</td><td>${fmt(d.p10)}</td><td>${fmt(d.p50)}</td><td>${fmt(d.p90)}</td>
    <td>${d.usual_plan ? fmt(d.usual_plan) : "none"}</td><td class="cook">${fmt(d.recommended)}</td><td><span class="pill ${d.surplus_risk}">${riskLabel(d.surplus_risk)}</span></td></tr>`).join("");
  const t = data.days.find((x) => x.date === date).totals;
  return `<table class="dishes"><thead><tr>${head}</tr></thead><tbody>${body}<tr class="total"><td>${scope === "all" ? "All dishes" : "Main dishes"}</td><td>${fmt(t.p10)}</td>
    <td>${fmt(t.p50)}</td><td>${fmt(t.p90)}</td><td>${fmt(t.usual_plan)}</td><td class="cook">${fmt(t.recommended)}</td><td></td></tr></tbody></table>`;
}

function riskGroups(data, date) {
  const rows = data.dishes.filter((r) => r.days[date]).map((r) => ({ name: r.dish_name, ...r.days[date] }));
  return ["high", "medium"].map((lvl) => {
    const list = rows.filter((d) => d.surplus_risk === lvl);
    return list.length ? `<div class="riskgroup"><h3><span class="pill ${lvl}">${riskLabel(lvl)}</span>${list.length} dish${list.length === 1 ? "" : "es"} may be left over</h3>` +
      `<ul>${list.map((d) => `<li><span>${esc(d.name)}</span><span class="num">Usual plan ${d.usual_plan ? fmt(d.usual_plan) : "none"}, likely ${fmt(d.p10)} to ${fmt(d.p90)}</span></li>`).join("")}</ul></div>` : "";
  }).join("") || `<p class="dk-panel-note">${icon("check")} No dish has a medium or high surplus risk on this day.</p>`;
}

export function mountForecast(root) {
  root.innerHTML = SKELETON;
  const q = (s) => root.querySelector(s);
  root.querySelectorAll(".seg").forEach(liquid);
  const V = { slot: null, start: null, scope: "core", selected: null, dishId: null, data: null, week: null, weekDish: null, error: null, loading: false };
  let seq = 0, mounted = false, lastVersion = -1;

  async function load() {
    const mine = ++seq;
    V.loading = true;
    render();
    try {
      const [data, week] = await Promise.all([
        api.get("/forecast/days", { slot: V.slot, start: V.start, scope: V.scope, days: 7 }),
        api.get("/week", { slot: V.slot, start: V.start, scope: V.scope }),
      ]);
      const weekDish = V.dishId ? await api.get("/week", { slot: V.slot, start: V.start, dish_id: V.dishId }) : null;
      if (mine !== seq) return;
      Object.assign(V, { data, week, weekDish, error: null });
      if (!data.days.some((d) => d.date === V.selected)) V.selected = (data.days.find((d) => d.totals.recommended) ?? data.days[0])?.date ?? null;
    } catch (e) {
      if (mine === seq) V.error = e;
    }
    if (mine === seq) { V.loading = false; render(); }
  }

  root.querySelectorAll("[data-slot]").forEach((b) => b.addEventListener("click", () => { V.slot = b.dataset.slot; V.dishId = null; load(); }));
  root.querySelectorAll("[data-scope]").forEach((b) => b.addEventListener("click", () => { V.scope = b.dataset.scope; load(); }));
  q("#fc-prev").addEventListener("click", () => { V.start = shift(V.start, -7); load(); });
  q("#fc-next").addEventListener("click", () => { V.start = shift(V.start, 7); load(); });
  q("#fc-now").addEventListener("click", () => { V.start = state.health.default_plan_date; load(); });
  q("#fc-days").addEventListener("click", (e) => { const b = e.target.closest("[data-date]"); if (b) { V.selected = b.dataset.date; render(); } });
  q("#fc-matrix").addEventListener("click", (e) => { const th = e.target.closest("th.on, th[scope=col]"); if (th && th.cellIndex > 0) { V.selected = V.data.days[th.cellIndex - 1].date; render(); } });
  q("#fc-pick").addEventListener("click", async (e) => {
    const b = e.target.closest("button[data-dish]");
    if (!b) return;
    V.dishId = b.dataset.dish || null;
    V.weekDish = V.dishId ? await api.get("/week", { slot: V.slot, start: V.start, dish_id: V.dishId }).catch(() => null) : null;
    render();
  });
  q("#fc-detail-actions").addEventListener("click", (e) => {
    const b = e.target.closest("[data-open]");
    if (b) openPlan(V.selected, V.slot);
  });

  const [first, last] = [() => state.health?.first_plan_date, () => state.health?.last_plan_date];
  let chartFor = null;
  function render() {
    root.classList.toggle("is-loading", V.loading);
    root.querySelectorAll("[data-slot]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.slot === V.slot)));
    root.querySelectorAll("[data-scope]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.scope === V.scope)));
    if (V.start) {
      q("#fc-week-label").textContent = `${shortDate(V.start)} to ${shortDate(shift(V.start, 6))}`;
      q("#fc-title").textContent = `${cap(V.slot)} forecast, next 7 days`;
      q("#fc-prev").disabled = first() && shift(V.start, -7) < first();
      q("#fc-next").disabled = last() && shift(V.start, 13) > last();
    }
    setHTML(q("#fc-error"), V.error ? `<div class="banner" style="margin:16px 0 0;width:auto"><strong>${esc(V.error.message)}</strong>${esc(V.error.fix || "")}</div>` : "");
    const data = V.data;
    if (!data) {
      setHTML(q("#fc-days"), Array.from({ length: 7 }, (_, i) => `<div class="fc-day skel" style="--i:${i};min-height:220px"></div>`).join(""));
      return;
    }
    if (setHTML(q("#fc-days"), data.days.map((d, i) => dayCard(d, V.selected, i)).join(""))) replay(q("#fc-days"), "entering", 900);
    setHTML(q("#fc-matrix"), matrix(data, V.selected));

    // chart: the slot total or one dish; dish buttons for the biggest dishes of the week
    const top = data.dishes.slice(0, 5);
    setHTML(q("#fc-pick"), `<button type="button" data-dish="" aria-pressed="${!V.dishId}">${V.scope === "all" ? "All dishes" : "Main dishes"}</button>` +
      top.map((d) => `<button type="button" data-dish="${d.dish_id}" aria-pressed="${V.dishId === d.dish_id}">${esc(d.dish_name)}</button>`).join(""));
    const series = V.dishId && V.weekDish ? V.weekDish : V.week;
    if (series && (chartFor?.series !== series || chartFor.sel !== V.selected)) {
      const chart = q("#fc-chart");
      chart.classList.toggle("static", chartFor?.series === series);
      chart.innerHTML = chartDesk(series, V.selected);
      bindChart(chart, series, (d) => { V.selected = d; render(); }, (d) => `<br>Recommended to cook ${fmt(d.recommended)}`);
      chartFor = { series, sel: V.selected };
    }

    const day = data.days.find((d) => d.date === V.selected);
    if (!day) return;
    q("#fc-detail-t").innerHTML = `${icon("service")}${esc(day.weekday)} ${esc(V.slot)}, ${esc(shortDate(day.date).replace(/^\w+, /, ""))}`;
    const kind = planKind(day.review);
    setHTML(q("#fc-detail-actions"), `${statusPill(day.review)}${kind ? `<span class="sv-chip">${esc(kind)}</span>` : ""}` +
      (day.totals.recommended ? `<button class="btn btn-primary btn-small" type="button" data-open>${icon("check")}${day.review ? "Open the plan" : "Review this plan"}</button>` : ""));
    q("#fc-headline").textContent = day.review?.decision === "approve" && day.review.approved_total != null
      ? `${day.headline} Approved: ${fmt(day.review.approved_total)} portions of the main dishes.` : day.headline;
    setHTML(q("#fc-table"), detailTable(data, V.selected, V.scope));
    setHTML(q("#fc-risk"), riskGroups(data, V.selected));
  }

  function start() {
    if (mounted || !state.health) return;
    mounted = true;
    V.slot = state.slot;
    V.start = state.health.default_plan_date;
    lastVersion = state.dataVersion;
    load();
  }
  window.addEventListener("ff:view", (e) => { if (e.detail === "forecast") start(); });
  subscribe((s) => {
    if (location.hash.slice(1) === "forecast" || location.hash.slice(1) === "desk") start();
    if (mounted && s.dataVersion !== lastVersion) { lastVersion = s.dataVersion; load(); }   // a decision was saved somewhere
  });
}
