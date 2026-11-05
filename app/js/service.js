// View: Service board. The plan for one meal on one day: the headline and the numbers that matter, the day's
// context, dish by dish tickets to change, the decision (approve, send back, withdraw), the week chart and what if.
// On the side: this meal's plans for the next days and what happened lately, so the board always shows where
// things stand. Questions about the plan go to the Copilot view.
import { bindChart, chartService } from "./charts.js";
import { liquid, replay, rollNumber, setHTML } from "./fx.js";
import { icon } from "./icons.js";
import { feedItem } from "./plans.js";
import { review, setAdjusted, setDate, setEditing, setScope, setSlot, state, subscribe } from "./state.js";
import { SLOTS, cap, esc, fmt, isoDay, parseDay, planKind, reviewStatus, riskLabel, shortDate, statusPill, weekdayName, whenText } from "./util.js";
import { mountWhatIf } from "./whatif.js";

const SKELETON = `
  <header class="sv-top">
    <div class="sv-title">
      <p class="eyebrow">${icon("service")}Service board</p>
      <p class="sv-brand">Main mess kitchen</p>
      <p class="sv-sub" id="sv-sub"></p>
    </div>
    <div class="sv-tools">
      <div class="seg sv-pills" role="group" aria-label="Meal slot">${SLOTS.map((s) => `<button type="button" data-slot="${s}" aria-pressed="false">${cap(s)}</button>`).join("")}</div>
      <div class="sv-date" role="group" aria-label="Forecast day">
        <button type="button" class="icon-btn" id="sv-prev" aria-label="Previous day">${icon("left")}</button>
        <label class="sr-only" for="sv-date">Forecast day</label><input type="date" id="sv-date" class="sv-date-input">
        <button type="button" class="icon-btn" id="sv-next" aria-label="Next day">${icon("right")}</button>
      </div>
    </div>
  </header>
  <section class="sv-hero glass">
    <div class="sv-hero-text" aria-live="polite">
      <div class="sv-hero-meta"><span class="sv-chip" id="sv-chip"></span><span id="sv-review"></span></div>
      <h1 class="sv-headline" id="sv-headline">Loading the forecast</h1>
      <p class="sv-support" id="sv-support"></p>
      <div id="sv-note"></div>
      <ul class="sv-facts" id="sv-facts" aria-label="About this day"></ul>
    </div>
    <div class="sv-kpis" id="sv-kpis"></div>
    <div class="sv-actions">
      <button class="btn btn-primary" id="sv-approve" type="button">${icon("check")}<span id="sv-approve-t">Approve this plan</span></button>
      <button class="btn" id="sv-change" type="button" aria-pressed="false">${icon("edit")}<span id="sv-change-t">Change quantities</span></button>
      <button class="btn btn-danger" id="sv-back" type="button">${icon("back")}Send back</button>
      <button class="btn" id="sv-withdraw" type="button" hidden>${icon("close")}Withdraw decision</button>
      <p class="sv-status" id="sv-status" aria-live="polite"></p>
    </div>
  </section>
  <div class="sv-grid">
    <div class="sv-main">
      <section aria-labelledby="sv-dishes-t">
        <div class="sv-section-head"><h2 id="sv-dishes-t">Dish by dish</h2>
          <p class="sv-legend-text"><i class="k band"></i>Likely range <i class="k tick"></i>Most likely <i class="k usual"></i>Usual plan</p></div>
        <div class="sv-filters" id="sv-filters">
          <div class="sv-search-wrap">${icon("search")}<label class="sr-only" for="sv-search">Find a dish</label>
            <input id="sv-search" class="sv-search" type="search" autocomplete="off" placeholder="Find a dish&hellip;"></div>
          <select id="sv-cat" class="sv-select" aria-label="Filter by category"><option value="all">All categories</option></select>
          <div class="seg sv-pills sv-diet" id="sv-diet" role="group" aria-label="Filter by diet" hidden></div>
        </div>
        <p class="sv-filter-count" id="sv-filter-count" aria-live="polite"></p>
        <div id="sv-tickets" class="tickets"></div>
        <button class="btn show-all" id="sv-showall" type="button" hidden></button>
      </section>
      <section class="weekcard glass" aria-labelledby="sv-week-title">
        <div class="sv-section-head"><h2 id="sv-week-title"></h2><p class="sv-legend-text" id="sv-week-sub"></p></div>
        <div class="chart" id="sv-chart"></div>
        <div class="legend"><span><i class="swatch" style="background:linear-gradient(180deg,#6EE7B7,#99F6E4)"></i>Likely range</span><span><i style="background:#0D2A1E"></i>Most likely</span><span><i class="dash"></i>Usual plan</span><span class="legend-hint">Click a day to open it</span></div>
      </section>
      <section class="whatif glass" aria-labelledby="sv-wi-title">
        <div class="sv-section-head"><h2 id="sv-wi-title">${icon("sliders")}Try a what if</h2><p class="sv-legend-text">Change one thing and watch the plan move.</p></div>
        <div id="sv-whatif"></div>
      </section>
    </div>
    <aside class="sv-side">
      <section class="sv-side-card glass" aria-labelledby="sv-wk-t">
        <h2 id="sv-wk-t">${icon("plans")}<span id="sv-wk-title">This meal, next days</span></h2>
        <ul class="sv-wk" id="sv-wk"></ul>
        <a class="btn btn-small" href="#plans">${icon("plans")}All plans</a>
      </section>
      <section class="sv-side-card glass" aria-labelledby="sv-act-t">
        <h2 id="sv-act-t">${icon("clock")}Latest activity</h2><ul class="feed" id="sv-feed"></ul>
        <a class="btn btn-small" href="#copilot">${icon("copilot")}Ask the copilot about this plan</a>
      </section>
    </aside>
  </div>`;

const RAIN = ["Dry", "Light rain", "Rain", "Heavy rain"];
// Where the day's weather came from: the dataset, Open-Meteo (observed or forecast), the admin, or last year's average.
const WEATHER_TAG = { observed: " (observed)", forecast: " (forecast)", entered: " (entered)", assumed: " (assumed)" };
const WEATHER_TITLE = {
  recorded: "Recorded weather from the dataset",
  observed: "Recorded weather from Open-Meteo, refreshed every hour",
  forecast: "Live forecast from Open-Meteo, refreshed every hour",
  entered: "Entered in the Daily log",
  assumed: "Last year's monthly average: no live forecast reaches this far ahead",
};
const DIET_LABEL = { veg: "Veg", nonveg: "Non-veg", egg: "Egg" };
const CATEGORY_LABEL = (c) => c.replace(/_/g, " ").replace(/\b\w/g, (m) => m.toUpperCase());
const setText = (el, text) => { if (el.textContent !== text) el.textContent = text; };

function rangeBar(d, rec) {
  const max = Math.max(d.p90, d.usual_plan, rec) * 1.12 || 1;
  const pos = (v) => `${(v / max) * 100}%`;
  return `<div class="rangebar" aria-hidden="true"><div class="band" style="left:${pos(d.p10)};width:${((d.p90 - d.p10) / max) * 100}%"></div>` +
    `<div class="tick" style="left:${pos(d.p50)}"></div>${d.usual_plan ? `<div class="usual" style="left:${pos(d.usual_plan)}"></div>` : ""}</div>`;
}

function ticket(d, s, meta, i) {
  const qty = s.adjusted[d.dish_id] ?? d.recommended;
  const big = s.editing
    ? `<input type="number" min="0" step="5" value="${qty}" data-dish="${d.dish_id}" aria-label="Portions to cook for ${esc(d.dish_name)}">`
    : `<span class="big num" data-v="${qty}">${fmt(qty)}</span>`;
  const usual = d.usual_plan ? `Usual plan is ${fmt(d.usual_plan)}.` : "No usual plan yet for this dish.";
  const diff = d.usual_plan ? qty - d.usual_plan : 0;
  const delta = d.usual_plan && diff ? `<span class="ticket-delta ${diff > 0 ? "up" : "down"}" title="Compared with the usual plan">${diff > 0 ? "+" : "-"}${fmt(Math.abs(diff))} vs usual</span>` : "";
  const m = meta[d.dish_id];
  const tags = m ? `<p class="ticket-tags">${m.category ? `<span class="tag">${esc(CATEGORY_LABEL(m.category))}</span>` : ""}${m.diet ? `<span class="tag diet-${esc(m.diet)}">${esc(DIET_LABEL[m.diet] ?? m.diet)}</span>` : ""}</p>` : "";
  return `<article class="ticket glass-lite" style="--i:${i}" data-dish-id="${d.dish_id}"><div class="ticket-head"><h3 class="ticket-name">${esc(d.dish_name)}</h3><span class="pill ${d.surplus_risk}">${riskLabel(d.surplus_risk, true)}</span></div>
    ${tags}
    <div class="ticket-qty">${big}<span class="unit">portions to cook</span>${delta}</div>${rangeBar(d, qty)}
    <p class="ticket-cap num">Likely ${fmt(d.p10)} to ${fmt(d.p90)}. ${usual}</p></article>`;
}

const skeletonTickets = () => Array.from({ length: 4 }, (_, i) => `<div class="ticket-skel skel" style="--i:${i}">` +
  `<span class="skel-line" style="width:55%"></span><span class="skel-line" style="width:35%;height:30px;margin-top:18px"></span>` +
  `<span class="skel-line" style="width:100%;margin-top:18px"></span><span class="skel-line" style="width:70%;margin-top:12px"></span></div>`).join("");

function kpis(p, s) {
  const t = p.totals;
  const total = p.dishes.reduce((a, d) => a + (s.adjusted[d.dish_id] ?? d.recommended), 0);
  const max = Math.max(t.p90, t.usual_plan || 0, total) * 1.08 || 1;
  const pct = (v) => `${((v / max) * 100).toFixed(2)}%`;
  const edited = s.editing && total !== t.recommended;
  return `<div class="sv-kpi-main"><span class="sv-kpi-label">${edited ? "To cook, with your changes" : "To cook"}</span>
      <span class="sv-kpi-big num" data-roll="${total}">${fmt(total)}</span><span class="sv-kpi-unit">portions</span></div>
    <div class="sv-kpi-range" aria-hidden="true"><i class="band" style="left:${pct(t.p10)};width:${pct(t.p90 - t.p10)}"></i>
      <i class="tick" style="left:${pct(t.p50)}"></i>${t.usual_plan ? `<i class="usual" style="left:${pct(t.usual_plan)}"></i>` : ""}<i class="cook" style="left:${pct(total)}"></i></div>
    <p class="sv-kpi-cap num" title="${esc(p.totals_note || "")}">Likely ${fmt(t.p10)} to ${fmt(t.p90)}</p>
    <dl class="sv-kpi-grid">
      <div><dt>Most likely</dt><dd class="num">${fmt(t.p50)}</dd></div>
      <div><dt>Usual plan</dt><dd class="num">${t.usual_plan ? fmt(t.usual_plan) : "none"}</dd></div>
      <div><dt>Expected</dt><dd class="num">${fmt(p.expected_attendance)}</dd></div>
    </dl>`;
}

function facts(p) {
  const f = p.day_facts || {}, out = [];
  if (f.temp_max_c != null) out.push(["thermo", `${Math.round(f.temp_max_c)}&deg; / ${Math.round(f.temp_min_c)}&deg;C`]);
  if (f.rain_level != null) {
    const src = f.weather_source || (f.weather_is_assumed ? "assumed" : "recorded");
    const label = src === "assumed" ? (RAIN[f.rain_level] ?? "Rain") : (f.weather_condition || RAIN[f.rain_level] || "Rain");
    out.push([f.rain_level > 0 ? "rain" : "sun", `<span title="${esc(WEATHER_TITLE[src] || "")}">${esc(label)}${WEATHER_TAG[src] || ""}</span>`]);
  }
  if (f.exam_week) out.push(["book", "Exam week"]); else if (f.formative_test) out.push(["book", "Test week"]);
  if (f.holiday) out.push(["star", "Holiday"]);
  if (f.festival) out.push(["star", "Festival"]);
  if (f.students_mostly_away) out.push(["users", "Students mostly away"]);
  return out.map(([ic, t]) => `<li class="fact">${icon(ic)}${t}</li>`).join("");
}

// Food item filter: search text, one category, one diet. Local to this view; recomputed from the day's menu.
const foodFilter = { q: "", category: "all", diet: "all" };
function matchesFilter(d, meta) {
  const m = meta[d.dish_id];
  if (foodFilter.diet !== "all" && m?.diet !== foodFilter.diet) return false;
  if (foodFilter.category !== "all" && m?.category !== foodFilter.category) return false;
  if (foodFilter.q && !d.dish_name.toLowerCase().includes(foodFilter.q)) return false;
  return true;
}

const planRange = (h) => [h?.first_plan_date ?? h?.demo?.first_date, h?.last_plan_date ?? h?.demo?.last_date];
const shiftDay = (iso, n) => { const d = parseDay(iso); d.setDate(d.getDate() + n); return isoDay(d); };

export function mountService(root) {
  root.innerHTML = SKELETON;
  const q = (s) => root.querySelector(s);
  mountWhatIf(q("#sv-whatif"), { gridClass: "whatif-grid" });
  root.querySelectorAll(".seg").forEach(liquid);

  root.querySelectorAll("[data-slot]").forEach((b) => b.addEventListener("click", () => setSlot(b.dataset.slot)));
  q("#sv-approve").addEventListener("click", () => review("approve"));
  q("#sv-back").addEventListener("click", () => review("send_back"));
  q("#sv-withdraw").addEventListener("click", () => review("withdraw"));
  q("#sv-wk").addEventListener("click", (e) => { const b = e.target.closest("[data-date]"); if (b && b.dataset.date !== state.date) setDate(b.dataset.date); });
  q("#sv-change").addEventListener("click", () => setEditing(!state.editing));
  q("#sv-showall").addEventListener("click", () => setScope(state.scope === "core" ? "all" : "core"));
  q("#sv-tickets").addEventListener("input", (e) => {
    if (e.target.dataset.dish) setAdjusted(e.target.dataset.dish, Math.max(0, Math.round(Number(e.target.value) || 0)));
  });
  const go = (iso) => {
    const [lo, hi] = planRange(state.health);
    if (iso && iso !== state.date && (!lo || iso >= lo) && (!hi || iso <= hi)) setDate(iso);
  };
  q("#sv-prev").addEventListener("click", () => state.date && go(shiftDay(state.date, -1)));
  q("#sv-next").addEventListener("click", () => state.date && go(shiftDay(state.date, 1)));
  q("#sv-date").addEventListener("change", (e) => go(e.target.value));

  let lastState = null;
  const rerender = () => { if (lastState) render(lastState); };
  q("#sv-search").addEventListener("input", (e) => { foodFilter.q = e.target.value.trim().toLowerCase(); rerender(); });
  q("#sv-cat").addEventListener("change", (e) => { foodFilter.category = e.target.value; rerender(); });
  q("#sv-diet").addEventListener("click", (e) => {
    const b = e.target.closest("[data-diet]");
    if (!b) return;
    foodFilter.diet = b.dataset.diet;
    rerender();
  });

  function renderFilterBar(s) {
    const meta = Object.fromEntries(s.menu.map((m) => [m.dish_id, m]));
    const cats = [...new Set(s.menu.map((m) => m.category).filter(Boolean))].sort();
    if (!foodFilter.category || (foodFilter.category !== "all" && !cats.includes(foodFilter.category))) foodFilter.category = "all";
    const catSel = q("#sv-cat");
    if (catSel.dataset.built !== cats.join(",")) {
      catSel.innerHTML = `<option value="all">All categories</option>` + cats.map((c) => `<option value="${esc(c)}">${esc(CATEGORY_LABEL(c))}</option>`).join("");
      catSel.dataset.built = cats.join(",");
    }
    catSel.value = foodFilter.category;
    const diets = [...new Set(s.menu.map((m) => m.diet).filter(Boolean))];
    if (foodFilter.diet !== "all" && !diets.includes(foodFilter.diet)) foodFilter.diet = "all";
    const diet = q("#sv-diet");
    diet.hidden = diets.length < 2;
    setHTML(diet, diets.length < 2 ? "" : [["all", "All"], ...diets.map((d) => [d, DIET_LABEL[d] ?? d])]
      .map(([v, label]) => `<button type="button" data-diet="${v}" aria-pressed="${String(v === foodFilter.diet)}">${label}</button>`).join(""));
    return meta;
  }

  const shownQty = new Map();     // dish id -> the number last shown, so a change rolls to its new value
  let shownTotal = null, ticketsKey = "", chartFor = null;

  function render(s) {
    lastState = s;
    const meta = renderFilterBar(s);
    const p = s.plan;
    root.classList.toggle("is-loading", s.loading);
    root.querySelectorAll("[data-slot]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.slot === s.slot)));
    setText(q("#sv-chip"), s.health?.data_source_short ?? "");
    q("#sv-chip").title = s.health?.data_source_chip ?? "";
    setText(q("#sv-sub"), s.date ? `Forecast for ${weekdayName(s.date)}, ${shortDate(s.date).replace(/^\w+, /, "")}` : "Loading the forecast day");

    // the day picker
    const [lo, hi] = planRange(s.health);
    const dateInput = q("#sv-date");
    if (lo) dateInput.min = lo;
    if (hi) dateInput.max = hi;
    if (s.date && dateInput.value !== s.date && document.activeElement !== dateInput) dateInput.value = s.date;
    q("#sv-prev").disabled = !s.date || (lo && s.date <= lo);
    q("#sv-next").disabled = !s.date || (hi && s.date >= hi);

    const tickets = q("#sv-tickets");
    if (s.error) {
      setText(q("#sv-headline"), "The forecast could not be loaded");
      setText(q("#sv-support"), "");
      setHTML(q("#sv-kpis"), "");
      setHTML(q("#sv-facts"), "");
      setHTML(tickets, `<div class="glass-lite empty" style="grid-column:1/-1">${icon("alert")}<strong>${esc(s.error.message)}</strong>${esc(s.error.fix || "")}</div>`);
      ticketsKey = "";
    } else if (!p) {
      setHTML(tickets, skeletonTickets());
      setHTML(q("#sv-kpis"), `<div class="skel" style="height:100%;min-height:150px"></div>`);
    } else if (!p.dishes.length) {
      setText(q("#sv-headline"), `No ${s.slot} is planned for ${weekdayName(s.date)}`);
      setText(q("#sv-support"), "");
      setHTML(q("#sv-kpis"), "");
      setHTML(q("#sv-facts"), facts(p));
      setHTML(tickets, `<div class="glass-lite empty" style="grid-column:1/-1"><strong>No dishes are on the menu for this slot.</strong>Pick another meal slot or day above.</div>`);
      ticketsKey = "";
    } else {
      const total = p.dishes.reduce((a, d) => a + (s.adjusted[d.dish_id] ?? d.recommended), 0);
      const changed = s.editing && total !== p.totals.recommended;
      setText(q("#sv-headline"), p.headline);
      setText(q("#sv-support"), changed
        ? `With your changes the total is ${fmt(total)} portions, ${fmt(Math.abs(total - p.totals.recommended))} ${total > p.totals.recommended ? "more" : "fewer"} than recommended.`
        : p.supporting);
      setHTML(q("#sv-facts"), facts(p));
      if (setHTML(q("#sv-kpis"), kpis(p, s))) {
        const big = q("#sv-kpis [data-roll]");
        rollNumber(big, shownTotal ?? Math.round(total * 0.7), total, shownTotal === null ? 900 : 600);
        shownTotal = total;
      }
      const typing = s.editing && document.activeElement?.tagName === "INPUT" && tickets.contains(document.activeElement);
      const shown = p.dishes.filter((d) => matchesFilter(d, meta));
      const filterActive = foodFilter.q || foodFilter.category !== "all" || foodFilter.diet !== "all";
      setText(q("#sv-filter-count"), filterActive ? `Showing ${shown.length} of ${p.dishes.length} dishes.` : "");
      if (!typing) {
        const key = `${s.slot}|${s.date}|${s.scope}|${shown.map((d) => d.dish_id).join(",")}`;
        const replaced = setHTML(tickets, shown.length ? shown.map((d, i) => ticket(d, s, meta, i)).join("")
          : `<div class="glass-lite empty" style="grid-column:1/-1">${icon("search")}<strong>No dish matches that search.</strong>Try a different word or clear the filters.</div>`);
        if (key !== ticketsKey) { replay(tickets, "entering", 1100); ticketsKey = key; }
        if (replaced) {
          tickets.querySelectorAll(".big[data-v]").forEach((el) => {
            const id = el.closest("[data-dish-id]").dataset.dishId, to = Number(el.dataset.v);
            if (shownQty.has(id) && shownQty.get(id) !== to) rollNumber(el, shownQty.get(id), to);
            shownQty.set(id, to);
          });
        }
      }
    }
    const hasWhatIf = Object.keys(s.overrides).length > 0;
    setHTML(q("#sv-note"), hasWhatIf ? `<p class="sv-note">${icon("sliders")}This is a what if, not the saved plan. Approving saves it with your changes listed.</p>` : "");
    const all = s.scope === "all", hidden = p?.dishes_hidden ?? 0;
    const btn = q("#sv-showall");
    btn.hidden = !p || (!all && hidden === 0);
    setHTML(btn, `${icon("list")}${all ? "Show main dishes only" : `Show all dishes (${hidden} more)`}`);
    q("#sv-change").setAttribute("aria-pressed", String(s.editing));
    setText(q("#sv-change-t"), s.editing ? "Done changing" : "Change quantities");
    const r = p?.review, st = reviewStatus(r), kind = planKind(r);
    const approvedNote = r?.decision === "approve" && r.approved_total != null
      ? ` ${fmt(r.approved_total)} portions of the main dishes approved${r.edited_dishes ? `, ${r.edited_dishes} quantit${r.edited_dishes === 1 ? "y" : "ies"} changed by hand` : ""}.` : "";
    setText(q("#sv-status"), r ? `${st.label} ${whenText(r.reviewed_at)}${r.reviewer && !r.automatic ? ` by ${r.reviewer}` : ""}.${approvedNote}${kind ? ` ${kind}.` : ""}` : "Nobody has decided on this plan yet.");
    setHTML(q("#sv-review"), r ? statusPill(r) + (kind ? `<span class="sv-chip">${esc(kind)}</span>` : "") : statusPill(null));
    const noDishes = !p || !p.dishes.length;
    q("#sv-approve").disabled = q("#sv-back").disabled = noDishes;
    setText(q("#sv-approve-t"), r?.decision === "approve" ? "Approve again" : "Approve this plan");
    q("#sv-withdraw").hidden = !r;

    setText(q("#sv-week-title"), `${cap(s.slot)} demand this week`);
    setText(q("#sv-week-sub"), s.scope === "all" ? "Total portions across all dishes" : "Total portions across the main dishes");
    const chart = q("#sv-chart");
    if (s.week && (chartFor?.week !== s.week || chartFor.date !== s.date)) {
      chart.classList.toggle("static", chartFor?.week === s.week);   // same data, new day: no redraw animation
      chart.innerHTML = chartService(s.week, s.date);
      bindChart(chart, s.week, (d) => d !== s.date && setDate(d));
      chartFor = { week: s.week, date: s.date };
    }

    // this meal over the next days (the shared plans list) and the latest activity
    setText(q("#sv-wk-title"), `${cap(s.slot)}, next days`);
    const days = s.plans?.days ?? [];
    setHTML(q("#sv-wk"), days.length ? days.map((d) => {
      const sl = d.slots.find((x) => x.meal_slot === s.slot);
      if (!sl?.has_menu) return `<li class="sv-wk-off"><span>${esc(shortDate(d.date))}</span><span>No menu</span></li>`;
      const rv = sl.review, total = rv?.decision === "approve" ? rv.approved_total : sl.totals.recommended;
      return `<li><button type="button" class="sv-wk-row ${d.date === s.date ? "on" : ""}" data-date="${d.date}"><span class="sv-wk-day">${esc(shortDate(d.date))}${d.is_today ? " <small>today</small>" : ""}</span>
        <span class="sv-wk-n num">${fmt(total)}</span>${statusPill(rv, true)}</button></li>`;
    }).join("") : `<li class="feed-empty">The plans of the next days appear here.</li>`);
    setHTML(q("#sv-feed"), s.activity.length ? s.activity.slice(0, 6).map(feedItem).join("") : `<li class="feed-empty">No decisions or log entries yet.</li>`);
  }

  subscribe(render);
}
