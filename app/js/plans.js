// View: Plans. Every meal of the next 7 days on one board: what to cook, its status, and the decision buttons.
// Approve, send back or withdraw one plan, a whole day, everything waiting, or a selection. Each decision is saved on
// the server and every other view (Home, Service board, Forecast, Calendar, Daily log) shows it at once.
import { api } from "./api.js";
import { liquid, replay, setHTML } from "./fx.js";
import { icon } from "./icons.js";
import { openPlan, reviewMany, state, subscribe } from "./state.js";
import { SLOTS, SLOT_ICON, cap, esc, fmt, isoDay, parseDay, planKind, reviewStatus, shortDate, statusPill, whenText } from "./util.js";

const shift = (iso, n) => { const d = parseDay(iso); d.setDate(d.getDate() + n); return isoDay(d); };
const FILTERS = [["all", "All"], ["pending", "Waiting"], ["approve", "Approved"], ["send_back", "Sent back"]];

const SKELETON = `
  <header class="pl-top glass">
    <div><p class="eyebrow">${icon("plans")}Plans</p><h1 class="pl-title">Plans for the next days</h1>
      <p class="pl-sub">Approve what to cook for every meal in one place. Whatever you decide here is what the Service board, the Forecast,
        the Calendar and the Daily log show.</p></div>
    <div class="fc-week" role="group" aria-label="Choose the days">
      <button type="button" class="icon-btn" id="pl-prev" aria-label="Previous seven days">${icon("left")}</button>
      <span class="fc-week-label" id="pl-week-label"></span>
      <button type="button" class="icon-btn" id="pl-next" aria-label="Next seven days">${icon("right")}</button>
      <button type="button" class="btn btn-small" id="pl-now">From today</button>
    </div>
  </header>
  <section class="pl-stats" id="pl-stats" aria-live="polite"></section>
  <section class="pl-auto glass-lite" id="pl-auto"></section>
  <section class="pl-bar glass" aria-label="Decide on many plans">
    <div class="seg" id="pl-filter" role="group" aria-label="Show">${FILTERS.map(([k, t]) => `<button type="button" data-filter="${k}" aria-pressed="${k === "all"}">${t}</button>`).join("")}</div>
    <div class="pl-bulk">
      <span class="pl-selected" id="pl-selected"></span>
      <button class="btn btn-small" type="button" id="pl-sel-approve" disabled>${icon("check")}Approve selected</button>
      <button class="btn btn-small btn-danger" type="button" id="pl-sel-back" disabled>${icon("back")}Send back selected</button>
      <button class="btn btn-small" type="button" id="pl-sel-withdraw" disabled>${icon("close")}Withdraw selected</button>
      <button class="btn btn-small btn-primary" type="button" id="pl-all">${icon("check")}Approve every waiting plan</button>
    </div>
  </section>
  <div id="pl-error"></div>
  <section class="pl-board" id="pl-board" aria-label="Plans by day and meal"></section>
  <section class="dk-card glass pl-history" aria-labelledby="pl-hist-t">
    <h2 id="pl-hist-t">${icon("clock")}Latest decisions</h2><ul class="feed" id="pl-feed"></ul>
  </section>`;

const factLine = (f) => [f.festival && "Festival", f.holiday && "Holiday", f.exam_week && "Exam week", !f.exam_week && f.formative_test && "Test week",
  f.rain_level >= 2 && "Rain", f.students_mostly_away && "Many students away"].filter(Boolean).join(" · ");

function slotCard(day, s, picked) {
  if (!s.has_menu) return `<div class="pl-slot glass-lite off"><span class="pl-slot-name">${icon(SLOT_ICON[s.meal_slot])}${cap(s.meal_slot)}</span><span class="pl-none">No menu</span></div>`;
  const r = s.review, st = reviewStatus(r), key = `${day.date}|${s.meal_slot}`;
  const approved = r?.decision === "approve";
  const big = approved ? r.approved_total : s.totals.recommended;
  const kind = planKind(r);
  const risky = s.risk_counts.high + s.risk_counts.medium;
  const log = s.logged ? `<span class="pl-chip ${s.logged.auto ? "auto" : "ok"}">${icon(s.logged.auto ? "auto" : "log")}${s.logged.auto ? "Log filled automatically" : "Logged"}</span>` : "";
  const buttons = [
    !approved && `<button class="btn btn-small btn-primary" type="button" data-act="approve">${icon("check")}Approve</button>`,
    r?.decision !== "send_back" && `<button class="btn btn-small btn-danger" type="button" data-act="send_back">${icon("back")}Send back</button>`,
    r && `<button class="btn btn-small" type="button" data-act="withdraw" title="Withdraw the decision: the plan waits for a review again">${icon("close")}Withdraw</button>`,
    `<button class="btn btn-small" type="button" data-act="open">${icon("edit")}Open</button>`,
  ].filter(Boolean).join("");
  return `<article class="pl-slot glass-lite st-${st.key}" data-key="${key}">
    <label class="pl-check"><input type="checkbox" data-pick="${key}" ${picked.has(key) ? "checked" : ""} aria-label="Select ${cap(s.meal_slot)} on ${esc(day.date)}"></label>
    <span class="pl-slot-name">${icon(SLOT_ICON[s.meal_slot])}${cap(s.meal_slot)}</span>
    <span class="pl-big num">${fmt(big)}</span>
    <span class="pl-unit">${approved ? "portions approved" : "portions recommended"}${approved && r.approved_total !== s.totals.recommended ? `, forecast says ${fmt(s.totals.recommended)}` : ""}</span>
    <span class="pl-range num">Likely ${fmt(s.totals.p10)} to ${fmt(s.totals.p90)} · ${fmt(s.expected_attendance)} expected</span>
    <span class="pl-tags">${statusPill(r, true)}${kind ? `<span class="pl-chip">${esc(kind)}</span>` : ""}${risky ? `<span class="pl-chip risk"><span class="risk-dot ${s.risk_counts.high ? "high" : "medium"}"></span>${risky} at risk</span>` : ""}${log}</span>
    ${r ? `<span class="pl-when">${esc(st.label)} ${esc(whenText(r.reviewed_at))}${r.reviewer && !r.automatic ? ` by ${esc(r.reviewer)}` : ""}${r.edited_dishes ? `, ${r.edited_dishes} quantit${r.edited_dishes === 1 ? "y" : "ies"} changed` : ""}</span>` : ""}
    <div class="pl-actions">${buttons}</div></article>`;
}

export function feedItem(e) {
  const day = e.date ? esc(shortDate(e.date)) : "";
  const slot = e.meal_slot ? ` ${esc(e.meal_slot)}` : "";
  const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;
  const map = {   // built only for the event's own kind: each kind carries different fields
    approve: () => ["check", e.automatic ? `Approved automatically: ${day}${slot}` : `Approved: ${day}${slot}`, "ok"],
    send_back: () => ["back", `Sent back: ${day}${slot}`, "bad"],
    withdraw: () => ["close", `Decision withdrawn: ${day}${slot}`, "warn"],
    log: () => ["log", `Daily log saved for ${day}${e.by ? ` by ${esc(e.by)}` : ""}`, "ok"],
    log_auto: () => ["auto", `Daily log filled automatically for ${day}`, "auto"],
    donation_offer: () => ["leaf", `${esc(e.who)} offered ${fmt(e.portions)} portions (${day}${slot})`, "ok"],
    donation_requested: () => ["leaf", `${esc(e.who)} asked for ${fmt(e.portions)} portions`, "warn"],
    donation_accepted: () => ["check", `Request of ${esc(e.who)} accepted (${fmt(e.portions)} portions)`, "ok"],
    donation_collected: () => ["leaf", `${esc(e.who)} collected ${fmt(e.portions)} portions`, "ok"],
    donation_declined: () => ["close", `Request of ${esc(e.who)} declined`, "warn"],
    donation_withdrawn: () => ["close", `${esc(e.who)} withdrew a request`, "warn"],
    automation: () => ["auto", `Automatic run: ${plural(e.approved_count ?? 0, "plan")} approved, ${plural((e.logged_dates ?? []).length, "day")} logged`, "auto"],
  };
  const [ic, text, tone] = map[e.kind]?.() ?? ["info", esc(e.kind), ""];
  const note = e.note && !["approve", "send_back", "withdraw"].includes(e.note) && !e.note.startsWith("Approved automatically") ? `<small>${esc(e.note)}</small>` : "";
  return `<li class="feed-item ${tone}"><span class="feed-ic">${icon(ic)}</span><span class="feed-text">${text}${note}</span><time datetime="${esc(e.at)}">${esc(whenText(e.at))}</time></li>`;
}

export function mountPlans(root) {
  root.innerHTML = SKELETON;
  const q = (s) => root.querySelector(s);
  root.querySelectorAll(".seg").forEach(liquid);
  const V = { start: null, data: null, error: null, filter: "all", picked: new Set(), busy: false };
  let seq = 0, mounted = false, lastVersion = -1;

  async function load() {
    const mine = ++seq;
    try {
      const data = await api.get("/plans", { start: V.start, days: 7 });
      if (mine !== seq) return;
      V.data = data;
      V.error = null;
    } catch (e) { if (mine === seq) V.error = e; }
    if (mine === seq) render();
  }

  const refOf = (key) => { const [date, meal_slot] = key.split("|"); return { date, meal_slot }; };
  async function decide(keys, decision) {
    if (V.busy || !keys.length) return;
    V.busy = true;
    render();
    await reviewMany(keys.map(refOf), decision);   // reloads every view, this one included (dataVersion)
    V.picked.clear();
    V.busy = false;
    render();
  }

  q("#pl-prev").addEventListener("click", () => { V.start = shift(V.start, -7); load(); });
  q("#pl-next").addEventListener("click", () => { V.start = shift(V.start, 7); load(); });
  q("#pl-now").addEventListener("click", () => { V.start = state.health.today; load(); });
  q("#pl-filter").addEventListener("click", (e) => { const b = e.target.closest("[data-filter]"); if (b) { V.filter = b.dataset.filter; render(); } });
  q("#pl-board").addEventListener("change", (e) => {
    const key = e.target.dataset.pick;
    if (!key) return;
    if (e.target.checked) V.picked.add(key); else V.picked.delete(key);
    render();
  });
  q("#pl-board").addEventListener("click", (e) => {
    const b = e.target.closest("[data-act], [data-day]");
    if (!b) return;
    if (b.dataset.day) {
      const day = V.data.days.find((d) => d.date === b.dataset.day);
      decide(day.slots.filter((s) => s.has_menu && s.review?.decision !== "approve").map((s) => `${day.date}|${s.meal_slot}`), "approve");
      return;
    }
    const key = b.closest("[data-key]").dataset.key;
    if (b.dataset.act === "open") { const r = refOf(key); openPlan(r.date, r.meal_slot); return; }
    decide([key], b.dataset.act);
  });
  q("#pl-sel-approve").addEventListener("click", () => decide([...V.picked], "approve"));
  q("#pl-sel-back").addEventListener("click", () => decide([...V.picked], "send_back"));
  q("#pl-sel-withdraw").addEventListener("click", () => decide([...V.picked], "withdraw"));
  q("#pl-all").addEventListener("click", () => decide(V.data.days.flatMap((d) => d.slots.filter((s) => s.has_menu && !s.review).map((s) => `${d.date}|${s.meal_slot}`)), "approve"));

  function render() {
    root.classList.toggle("is-loading", V.busy);
    root.querySelectorAll("[data-filter]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.filter === V.filter)));
    if (V.start) q("#pl-week-label").textContent = `${shortDate(V.start)} to ${shortDate(shift(V.start, 6))}`;
    setHTML(q("#pl-error"), V.error ? `<div class="banner" style="margin:16px 0 0;width:auto"><strong>${esc(V.error.message)}</strong>${esc(V.error.fix || "")}</div>` : "");
    setHTML(q("#pl-feed"), state.activity.length ? state.activity.slice(0, 12).map(feedItem).join("") : `<li class="feed-empty">No decisions yet. Approve a plan and it shows here.</li>`);
    const d = V.data;
    if (!d) { setHTML(q("#pl-board"), `<div class="skel" style="height:420px"></div>`); return; }
    const sm = d.summary;
    setHTML(q("#pl-stats"), [
      ["check", sm.approved, "approved", sm.approved_automatically ? `${sm.approved_automatically} automatically` : "", "ok"],
      ["clock", sm.pending, "waiting for review", "", sm.pending ? "warn" : ""],
      ["back", sm.sent_back, "sent back", sm.sent_back ? "need a person" : "", sm.sent_back ? "bad" : ""],
      ["log", sm.logged, "meals logged", "in the Daily log", ""],
    ].map(([ic, n, label, sub, tone]) => `<div class="pl-stat glass-lite ${tone}">${icon(ic)}<span class="pl-stat-n num">${n}</span><span class="pl-stat-l">${label}${sub ? `<small>${sub}</small>` : ""}</span></div>`).join(""));
    const a = d.automation;
    setHTML(q("#pl-auto"), `${icon("auto")}<span>${a.auto_approve
      ? `<strong>Automatic approval is on</strong> for today and the next ${a.days_ahead - 1} day${a.days_ahead === 2 ? "" : "s"}: plans nobody has looked at are approved with the recommended quantities. Plans you send back are left for you.`
      : "<strong>Automatic approval is off.</strong> Every plan waits for a person."}
      ${a.auto_log ? " The Daily log fills itself from approved plans once a day has passed." : ""}
      ${a.last_run ? ` Last automatic run ${esc(whenText(a.last_run.at))}.` : ""}</span><a class="btn btn-small" href="#admin">${icon("sliders")}Automation settings</a>`);

    const n = V.picked.size;
    q("#pl-selected").textContent = n ? `${n} selected` : "Select plans to decide on many at once";
    ["#pl-sel-approve", "#pl-sel-back", "#pl-sel-withdraw"].forEach((s) => { q(s).disabled = !n || V.busy; });
    q("#pl-all").disabled = !sm.pending || V.busy;

    const show = (s) => V.filter === "all" || (V.filter === "pending" ? !s.review : s.review?.decision === V.filter);
    const html = d.days.map((day, i) => {
      const slots = day.slots.filter((s) => s.has_menu && show(s));
      if (V.filter !== "all" && !slots.length) return "";
      const waiting = day.slots.filter((s) => s.has_menu && s.review?.decision !== "approve").length;
      const facts = factLine(day.facts);
      return `<div class="pl-day" style="--i:${i}"><div class="pl-day-head"><div><h2>${esc(day.weekday)}${day.is_today ? ` <span class="pl-today">Today</span>` : ""}</h2>
          <p>${esc(shortDate(day.date).replace(/^\w+, /, ""))}${facts ? ` · ${esc(facts)}` : ""}</p></div>
          ${waiting ? `<button class="btn btn-small" type="button" data-day="${day.date}">${icon("check")}Approve the day (${waiting})</button>` : `<span class="pl-day-done">${icon("check")}All approved</span>`}</div>
        <div class="pl-slots">${(V.filter === "all" ? day.slots : slots).map((s) => slotCard(day, s, V.picked)).join("")}</div></div>`;
    }).join("");
    if (setHTML(q("#pl-board"), html || `<div class="glass-lite empty"><strong>No plans match this filter.</strong>Choose another filter above.</div>`)) replay(q("#pl-board"), "entering", 700);
  }

  function start() {
    if (mounted || !state.health) return;
    mounted = true;
    V.start = state.health.today;
    lastVersion = state.dataVersion;
    load();
  }
  window.addEventListener("ff:view", (e) => { if (e.detail === "plans") start(); });
  subscribe((s) => {
    if (location.hash.slice(1) === "plans") start();
    if (mounted && s.dataVersion !== lastVersion) { lastVersion = s.dataVersion; load(); }
    else if (mounted) render();
  });
}
