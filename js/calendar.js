// View: Calendar. The project's academic calendar (real TN public holidays, festivals, exam phases)
// cross-checked against a live public holiday feed. Click a day to open the Service board for it.
import { api } from "./api.js";
import { setDate, state as mainState } from "./state.js";
import { esc } from "./util.js";

const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const MONTH_NAME = (m) => new Date(`${m}-01T00:00:00`).toLocaleDateString("en-US", { month: "long", year: "numeric" });
const addMonths = (m, n) => { const [y, mo] = m.split("-").map(Number); const d = new Date(y, mo - 1 + n, 1); return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`; };

const SKELETON = `
  <header class="cal-top">
    <div><p class="cal-kicker">Calendar</p><h1 class="cal-brand">What's on the mess calendar</h1>
      <p class="cal-sub">Real public holidays, festivals and exam phases, cross-checked against a live calendar.</p></div>
    <div class="cal-nav" role="group" aria-label="Choose a month">
      <button type="button" id="cal-prev" aria-label="Previous month">&#8249;</button>
      <h2 id="cal-month-label"></h2>
      <button type="button" id="cal-next" aria-label="Next month">&#8250;</button>
      <button type="button" class="btn btn-ghost" id="cal-today">Jump to today</button>
    </div>
  </header>
  <p class="cal-live" id="cal-live"></p>
  <div class="cal-body">
    <section class="cal-card">
      <div class="cal-grid-head">${WEEKDAYS.map((d) => `<span>${d}</span>`).join("")}</div>
      <div class="cal-grid" id="cal-grid" aria-live="polite"></div>
      <div class="legend cal-legend">
        <span><i class="dot holiday"></i>Public holiday</span>
        <span><i class="dot festival"></i>Festival</span>
        <span><i class="dot exam"></i>Exam / test week</span>
        <span><i class="dot rain"></i>Rain holiday (past)</span>
        <span><i class="dot live"></i>Confirmed by a live calendar</span>
      </div>
    </section>
    <aside class="cal-card cal-upcoming" aria-labelledby="cal-up-title">
      <h2 id="cal-up-title">Coming up</h2>
      <ul id="cal-upcoming-list" class="cal-up-list"></ul>
    </aside>
  </div>`;

function dayCell(d, isCurrentMonth) {
  if (!d) return `<div class="cal-cell empty" aria-hidden="true"></div>`;
  const tags = [];
  if (d.holiday) tags.push(`<i class="dot holiday" title="Public holiday"></i>`);
  if (d.festival) tags.push(`<i class="dot festival" title="Festival"></i>`);
  if (d.exam_week || d.formative_test) tags.push(`<i class="dot exam" title="${d.exam_week ? "University exam" : "Formative test"} week"></i>`);
  if (d.rain_holiday) tags.push(`<i class="dot rain" title="Rain holiday"></i>`);
  const label = d.holiday_name || d.event_note || (d.festival ? "Festival" : d.exam_week ? "Exam week" : d.formative_test ? "Test week" : "");
  const classes = ["cal-cell", !isCurrentMonth && "muted", d.is_today && "today", d.is_weekend && "weekend",
    (d.holiday || d.festival) && "flagged"].filter(Boolean).join(" ");
  return `<button type="button" class="${classes}" data-date="${d.date}" aria-label="${esc(d.weekday)} ${d.date}${label ? `, ${esc(label)}` : ""}">
    <span class="cal-daynum">${Number(d.date.slice(-2))}</span>
    ${d.live_confirmed ? `<i class="dot live" title="Confirmed by a live calendar: ${esc(d.live_holiday_name)}"></i>` : ""}
    <span class="cal-dots">${tags.join("")}</span>
    ${label ? `<span class="cal-label">${esc(label)}</span>` : ""}
  </button>`;
}

export function mountCalendar(root) {
  root.innerHTML = SKELETON;
  const q = (s) => root.querySelector(s);
  const cache = new Map();   // month -> response
  let month = null;

  async function todayMonth() {
    const health = mainState.health || await api.get("/health").catch(() => null);
    return (health?.today || health?.default_plan_date || new Date().toISOString().slice(0, 10)).slice(0, 7);
  }

  async function load(m) {
    if (!cache.has(m)) cache.set(m, api.get("/calendar", { month: m }).catch((e) => ({ days: [], error: e })));
    return cache.get(m);
  }

  async function render() {
    q("#cal-month-label").textContent = MONTH_NAME(month);
    const data = await load(month);
    if (data.error) {
      q("#cal-grid").innerHTML = `<div class="empty" style="grid-column:1/-1">Could not load the calendar. ${esc(data.error.message || "")}</div>`;
      q("#cal-live").textContent = "";
      return;
    }
    q("#cal-live").innerHTML = data.live_checked
      ? `<span class="cal-live-ok">&#9679; Cross-checked with ${esc(data.live_source)}.</span>`
      : `<span class="cal-live-off">&#9675; Showing the project's own calendar only (live check unavailable right now).</span>`;
    const first = new Date(`${month}-01T00:00:00`);
    const lead = first.getDay();
    const cells = Array(lead).fill(null).concat(data.days);
    q("#cal-grid").innerHTML = cells.map((d) => dayCell(d, true)).join("");

    // Coming up: this month plus next, from today onward. Multi day runs (an exam week, a test week)
    // are collapsed to their first day, so one event shows once rather than once per day.
    const next = await load(addMonths(month, 1));
    const today = mainState.health?.today;
    const all = [...data.days, ...(next.days || [])];
    const startsRun = (d, i, key) => d[key] && !all[i - 1]?.[key];
    const upcoming = all.filter((d, i) => (!today || d.date >= today) &&
      (d.holiday || d.festival || startsRun(d, i, "exam_week") || startsRun(d, i, "formative_test"))).slice(0, 7);
    q("#cal-upcoming-list").innerHTML = upcoming.length ? upcoming.map((d) => `<li>
        <span class="cal-up-date">${new Date(`${d.date}T00:00:00`).toLocaleDateString("en-US", { weekday: "short", day: "numeric", month: "short" })}</span>
        <span class="cal-up-what">${esc(d.holiday_name || (d.festival ? "Festival" : d.exam_week ? "University exam week begins" : "Test week begins"))}</span>
        ${d.live_confirmed ? `<i class="dot live" title="Confirmed online"></i>` : ""}
      </li>`).join("") : `<li class="cal-up-empty">Nothing flagged in the next two months.</li>`;
  }

  q("#cal-prev").addEventListener("click", () => { month = addMonths(month, -1); render(); });
  q("#cal-next").addEventListener("click", () => { month = addMonths(month, 1); render(); });
  q("#cal-today").addEventListener("click", async () => { month = await todayMonth(); render(); });
  q("#cal-grid").addEventListener("click", (e) => {
    const btn = e.target.closest("[data-date]");
    if (!btn) return;
    setDate(btn.dataset.date);
    location.hash = "service";
  });

  todayMonth().then((m) => { month = m; render(); });
}
