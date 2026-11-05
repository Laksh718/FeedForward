// View: Calendar. The project's academic calendar (real TN public holidays, festivals, exam phases)
// cross-checked against a live public holiday feed, with the status of each day's plans. Click a day to open its
// plan on the Service board; "Plan for it" opens Rare events for a festival, holiday or exam week coming up.
import { api } from "./api.js";
import { replay } from "./fx.js";
import { icon } from "./icons.js";
import { openEvent, openPlan, state as mainState, subscribe } from "./state.js";
import { esc } from "./util.js";

const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const MONTH_NAME = (m) => new Date(`${m}-01T00:00:00`).toLocaleDateString("en-US", { month: "long", year: "numeric" });
const addMonths = (m, n) => { const [y, mo] = m.split("-").map(Number); const d = new Date(y, mo - 1 + n, 1); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`; };

const SKELETON = `
  <header class="cal-top">
    <div><p class="eyebrow">${icon("calendar")}Calendar</p><h1 class="cal-brand">What's on the mess calendar</h1>
      <p class="cal-sub">Real public holidays, festivals and exam phases, cross-checked against a live calendar. Click a day to open its plan.</p></div>
    <div class="cal-nav" role="group" aria-label="Choose a month">
      <button type="button" class="icon-btn" id="cal-prev" aria-label="Previous month">${icon("left")}</button>
      <h2 id="cal-month-label" aria-live="polite"></h2>
      <button type="button" class="icon-btn" id="cal-next" aria-label="Next month">${icon("right")}</button>
      <button type="button" class="btn" id="cal-today">Jump to today</button>
    </div>
  </header>
  <p class="cal-live" id="cal-live"></p>
  <div class="cal-body">
    <section class="cal-card glass">
      <div class="cal-grid-head">${WEEKDAYS.map((d) => `<span>${d}</span>`).join("")}</div>
      <div class="cal-grid" id="cal-grid"></div>
      <div class="legend cal-legend">
        <span><i class="dot holiday"></i>Public holiday</span>
        <span><i class="dot festival"></i>Festival</span>
        <span><i class="dot exam"></i>Exam / test week</span>
        <span><i class="dot rain"></i>Rain holiday (past)</span>
        <span><i class="dot live"></i>Confirmed by a live calendar</span>
        <span><i class="plan-mark approve"></i>Plans approved</span>
        <span><i class="plan-mark send_back"></i>A plan sent back</span>
      </div>
    </section>
    <aside class="cal-card glass cal-upcoming" aria-labelledby="cal-up-title">
      <h2 id="cal-up-title">${icon("star")}Coming up</h2>
      <ul id="cal-upcoming-list" class="cal-up-list"></ul>
    </aside>
  </div>`;

// The plans of a day as small marks: one per reviewed meal, green when approved, red when sent back.
function planMarks(reviews) {
  if (!reviews) return "";
  const list = Object.entries(reviews);
  const back = list.filter(([, r]) => r.decision === "send_back").length;
  const ok = list.length - back;
  const title = `${ok} meal${ok === 1 ? "" : "s"} approved${back ? `, ${back} sent back` : ""}`;
  return `<span class="cal-plans" title="${title}">${list.map(([, r]) => `<i class="plan-mark ${r.decision}"></i>`).join("")}</span>`;
}

function dayCell(d, i, reviews) {
  if (!d) return `<div class="cal-cell empty" aria-hidden="true"></div>`;
  const tags = [];
  if (d.holiday) tags.push(`<i class="dot holiday" title="Public holiday"></i>`);
  if (d.festival) tags.push(`<i class="dot festival" title="Festival"></i>`);
  if (d.exam_week || d.formative_test) tags.push(`<i class="dot exam" title="${d.exam_week ? "University exam" : "Formative test"} week"></i>`);
  if (d.rain_holiday) tags.push(`<i class="dot rain" title="Rain holiday"></i>`);
  const label = d.holiday_name || d.event_note || (d.festival ? "Festival" : d.exam_week ? "Exam week" : d.formative_test ? "Test week" : "");
  const selected = d.date === mainState.date;
  const classes = ["cal-cell", d.is_today && "today", selected && "selected", d.is_weekend && "weekend",
    (d.holiday || d.festival) && "flagged", (d.exam_week || d.formative_test) && "exam"].filter(Boolean).join(" ");
  return `<button type="button" class="${classes}" style="--i:${i}" data-date="${d.date}" aria-label="${esc(d.weekday)} ${d.date}${label ? `, ${esc(label)}` : ""}${d.is_today ? ", today" : ""}">
    <span class="cal-daynum">${Number(d.date.slice(-2))}</span>
    ${d.live_confirmed ? `<i class="dot live" title="Confirmed by a live calendar: ${esc(d.live_holiday_name)}"></i>` : ""}
    <span class="cal-dots">${tags.join("")}</span>
    ${label ? `<span class="cal-label">${esc(label)}</span>` : ""}
    ${planMarks(reviews)}
  </button>`;
}

export function mountCalendar(root) {
  root.innerHTML = SKELETON;
  const q = (s) => root.querySelector(s);
  const cache = new Map();   // month -> response
  const reviewCache = new Map();   // month -> {date: {slot: decision}}, cleared whenever a decision is saved
  let month = null;

  async function todayMonth() {
    const health = mainState.health || await api.get("/health").catch(() => null);
    return (health?.today || health?.default_plan_date || new Date().toISOString().slice(0, 10)).slice(0, 7);
  }

  async function load(m) {
    if (!cache.has(m)) cache.set(m, api.get("/calendar", { month: m }).catch((e) => ({ days: [], error: e })));
    return cache.get(m);
  }
  async function loadReviews(m) {
    if (!reviewCache.has(m)) {
      const [y, mo] = m.split("-").map(Number);
      const end = `${m}-${String(new Date(y, mo, 0).getDate()).padStart(2, "0")}`;
      reviewCache.set(m, api.get("/reviews", { start: `${m}-01`, end }).then((r) => r.reviews).catch(() => ({})));
    }
    return reviewCache.get(m);
  }

  async function render(direction = "") {
    const shown = month;
    q("#cal-month-label").textContent = MONTH_NAME(month);
    const [data, reviews] = await Promise.all([load(month), loadReviews(month)]);
    if (shown !== month) return;   // a newer month was asked for while this one loaded
    if (data.error) {
      q("#cal-grid").innerHTML = `<div class="empty" style="grid-column:1/-1">Could not load the calendar. ${esc(data.error.message || "")}</div>`;
      q("#cal-live").textContent = "";
      return;
    }
    q("#cal-live").innerHTML = data.live_checked
      ? `<span class="cal-live-ok"><i></i>Cross-checked with ${esc(data.live_source)}.</span>`
      : `<span class="cal-live-off"><i></i>Showing the project's own calendar only (live check unavailable right now).</span>`;
    const lead = new Date(`${month}-01T00:00:00`).getDay();
    const cells = Array(lead).fill(null).concat(data.days);
    const grid = q("#cal-grid");
    grid.innerHTML = cells.map((d, i) => dayCell(d, i, d && reviews[d.date])).join("");
    replay(grid, direction ? `slide-${direction}` : "fade-in", 800);

    // Coming up: this month plus next, from today onward. Multi day runs (an exam week, a test week)
    // are collapsed to their first day, so one event shows once rather than once per day.
    const next = await load(addMonths(month, 1));
    if (shown !== month) return;
    const today = mainState.health?.today;
    const all = [...data.days, ...(next.days || [])];
    const startsRun = (d, i, key) => d[key] && !all[i - 1]?.[key];
    const upcoming = all.filter((d, i) => (!today || d.date >= today) &&
      (d.holiday || d.festival || startsRun(d, i, "exam_week") || startsRun(d, i, "formative_test"))).slice(0, 7);
    const kind = (d) => (d.holiday ? "holiday" : d.festival ? "festival" : "exam");
    const event = (d) => (d.festival ? "festival" : d.holiday ? "holiday" : "exam_week");
    q("#cal-upcoming-list").innerHTML = upcoming.length ? upcoming.map((d, i) => {
      const day = new Date(`${d.date}T00:00:00`);
      return `<li style="--i:${i}"><button type="button" class="cal-up-item" data-date="${d.date}">
        <span class="cal-up-date ${kind(d)}"><b>${day.getDate()}</b>${day.toLocaleDateString("en-US", { month: "short" })}</span>
        <span class="cal-up-what">${esc(d.holiday_name || (d.festival ? "Festival" : d.exam_week ? "University exam week begins" : "Test week begins"))}
          <small>${day.toLocaleDateString("en-US", { weekday: "long" })}</small></span>
        ${d.live_confirmed ? `<i class="dot live" title="Confirmed online"></i>` : ""}</button>
        <button type="button" class="btn btn-small cal-up-plan" data-plan-event="${event(d)}" data-plan-date="${d.date}">${icon("bolt")}Plan for it</button></li>`;
    }).join("") : `<li class="cal-up-empty">Nothing flagged in the next two months.</li>`;
  }

  const open = (e) => {
    const ev = e.target.closest("[data-plan-event]");
    if (ev) { openEvent(ev.dataset.planDate, ev.dataset.planEvent); return; }
    const btn = e.target.closest("[data-date]");
    if (btn) openPlan(btn.dataset.date);
  };
  q("#cal-prev").addEventListener("click", () => { month = addMonths(month, -1); render("prev"); });
  q("#cal-next").addEventListener("click", () => { month = addMonths(month, 1); render("next"); });
  q("#cal-today").addEventListener("click", async () => { const m = await todayMonth(); const dir = m < month ? "prev" : m > month ? "next" : ""; month = m; render(dir); });
  q("#cal-grid").addEventListener("click", open);
  q("#cal-upcoming-list").addEventListener("click", open);

  todayMonth().then((m) => { month = m; render(); });
  // keep the highlighted day in step with the day open on the other views, and the plan marks with every decision
  let lastVersion = mainState.dataVersion;
  subscribe((s) => {
    q("#cal-grid").querySelectorAll("[data-date]").forEach((c) => c.classList.toggle("selected", c.dataset.date === s.date));
    if (s.dataVersion !== lastVersion && month) { lastVersion = s.dataVersion; reviewCache.clear(); render(); }
  });
}
