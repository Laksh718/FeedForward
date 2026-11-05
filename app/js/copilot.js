// View: Copilot. A conversation about one meal's plan. On the left, the plan the copilot is reading (pick the day and
// meal there); on the right, the questions and answers. The copilot puts the numbers into words: it uses only the
// figures of the plan shown, and it never changes, approves or sends back a plan.
import { liquid, setHTML } from "./fx.js";
import { icon } from "./icons.js";
import { logoMark } from "./logo.js";
import { ask, clearChat, openPlan, setDate, setSlot, state, subscribe } from "./state.js";
import { SLOTS, cap, esc, fmt, planKind, riskLabel, shortDate, sourceNote, statusPill } from "./util.js";

const GROUPS = [
  ["The plan", ["What should we cook?", "Explain the range", "Why is this different from the usual plan?"]],
  ["Dishes and risk", ["Which dishes are at risk of surplus?", "How much rice should we make?"]],
  ["Changes and the week", ["What if it rains?", "What if 15% fewer students come?", "What does an exam week do to demand?", "Summarise the week"]],
  ["Your documents", ["What does the SOP say about donating surplus food?", "What are the food safety rules for holding hot food?"]],
];

const SKELETON = `
  <div class="co-grid">
    <aside class="co-side">
      <header class="co-top"><p class="eyebrow">${icon("copilot")}Copilot</p><h1 class="co-title">Ask about a plan</h1>
        <p class="co-sub">The copilot puts the forecast into plain words. It only uses the figures of the plan below, and it never changes or approves anything.</p></header>
      <section class="co-card glass" aria-labelledby="co-ctx-t">
        <h2 id="co-ctx-t">${icon("service")}The plan it is reading</h2>
        <div class="co-ctx-row"><label for="co-date" class="sr-only">Day</label><input id="co-date" type="date">
          <div class="seg co-slots" id="co-slot" role="group" aria-label="Meal slot">${SLOTS.map((s) => `<button type="button" data-slot="${s}" aria-pressed="false">${cap(s)}</button>`).join("")}</div></div>
        <div id="co-plan" aria-live="polite"></div>
      </section>
      <section class="co-card glass" aria-labelledby="co-sug-t"><h2 id="co-sug-t">${icon("spark")}Try asking</h2>
        ${GROUPS.map(([t, qs]) => `<p class="co-group">${t}</p><div class="co-chips">${qs.map((x) => `<button type="button" class="co-chip">${x}</button>`).join("")}</div>`).join("")}
      </section>
    </aside>
    <section class="co-chat glass" aria-labelledby="co-chat-t">
      <header class="co-chat-head"><span class="copilot-avatar">${logoMark({ size: 40 })}</span>
        <div><h2 id="co-chat-t">Kitchen copilot</h2><p id="co-chat-sub"></p></div>
        <button class="btn btn-small" type="button" id="co-clear">${icon("trash")}Clear</button></header>
      <div class="co-log" id="co-log" aria-live="polite"></div>
      <form class="co-form" id="co-form"><label class="sr-only" for="co-q">Your question</label>
        <input id="co-q" autocomplete="off" maxlength="500" placeholder="Ask about a dish, the range, a change or the week">
        <button class="btn btn-primary" type="submit">${icon("send")}Ask</button></form>
    </section>
  </div>`;

const WELCOME = `<div class="bubble bot">Ask what to cook, how much of a dish to make, why a dish is above or below the usual plan, what a change would do, or how the week looks. I answer from the plan on the left.</div>`;
const TYPING = `<div class="bubble bot typing" role="status" aria-label="The copilot is writing"><i></i><i></i><i></i></div>`;

function planCard(s) {
  const p = s.plan;
  if (s.error) return `<p class="co-err">${esc(s.error.message)}</p>`;
  if (!p) return `<div class="skel" style="height:150px"></div>`;
  if (!p.dishes.length) return `<p class="dk-panel-note">No ${esc(s.slot)} is on the menu this day. Pick another day or meal.</p>`;
  const t = p.totals, r = p.review, kind = planKind(r);
  const risky = p.dishes.filter((d) => d.surplus_risk !== "low");
  return `<p class="co-plan-h">${esc(p.headline)}</p>
    <dl class="co-plan-grid"><div><dt>To cook</dt><dd class="num">${fmt(t.recommended)}</dd></div><div><dt>Likely</dt><dd class="num">${fmt(t.p10)}&ndash;${fmt(t.p90)}</dd></div>
      <div><dt>Expected</dt><dd class="num">${fmt(p.expected_attendance)}</dd></div></dl>
    <div class="co-plan-st">${statusPill(r)}${kind ? `<span class="sv-chip">${esc(kind)}</span>` : ""}</div>
    ${Object.keys(s.overrides).length ? `<p class="sv-note">${icon("sliders")}A what if from the Service board is applied.</p>` : ""}
    <ul class="co-plan-dishes">${p.dishes.slice(0, 5).map((d) => `<li><span class="risk-dot ${d.surplus_risk}" title="${riskLabel(d.surplus_risk, true)}"></span>${esc(d.dish_name)}<b class="num">${fmt(d.recommended)}</b></li>`).join("")}</ul>
    ${risky.length ? `<p class="dk-panel-note">${risky.length} dish${risky.length === 1 ? "" : "es"} with a medium or high surplus risk.</p>` : ""}
    <button class="btn btn-small" type="button" id="co-open">${icon("service")}Open this plan</button>`;
}

export function mountCopilot(root) {
  root.innerHTML = SKELETON;
  const q = (s) => root.querySelector(s);
  root.querySelectorAll(".seg").forEach(liquid);
  const send = (text) => { ask(text); q("#co-q").value = ""; };
  q("#co-form").addEventListener("submit", (e) => { e.preventDefault(); send(q("#co-q").value); });
  root.querySelectorAll(".co-chip").forEach((b) => b.addEventListener("click", () => send(b.textContent)));
  q("#co-clear").addEventListener("click", clearChat);
  q("#co-slot").addEventListener("click", (e) => { const b = e.target.closest("[data-slot]"); if (b && b.dataset.slot !== state.slot) setSlot(b.dataset.slot); });
  q("#co-date").addEventListener("change", (e) => { if (e.target.value && e.target.value !== state.date) setDate(e.target.value); });
  q("#co-plan").addEventListener("click", (e) => { if (e.target.closest("#co-open")) openPlan(state.date, state.slot); });

  let count = 0;
  subscribe((s) => {
    root.querySelectorAll("[data-slot]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.slot === s.slot)));
    const d = q("#co-date");
    if (s.health) { d.min = s.health.first_plan_date; d.max = s.health.last_plan_date; }
    if (s.date && d.value !== s.date && document.activeElement !== d) d.value = s.date;
    setHTML(q("#co-plan"), planCard(s));
    q("#co-chat-sub").textContent = s.date ? `Reading the ${s.slot} plan for ${shortDate(s.date)}.` : "";
    const log = q("#co-log");
    const html = s.chat.length ? s.chat.map((m) => `<div class="bubble ${m.role}">${m.role === "user" && m.date ? `<span class="ctx">${esc(cap(m.slot))}, ${esc(shortDate(m.date))}</span>` : ""}${esc(m.text)}${sourceNote(m) ? `<span class="src">${sourceNote(m)}</span>` : ""}${m.documents?.length && m.source !== "documents"
        ? `<span class="co-docs">${icon("book")}Your documents: ${m.documents.map((d) => `<span title="${esc(d.text)}">${esc(d.source)}</span>`).join(", ")}</span>` : ""}</div>`).join("") + (s.chatBusy ? TYPING : "")
      : WELCOME;
    if (setHTML(log, html)) {
      [...log.children].slice(s.chat.length ? count : 0).forEach((el) => el.classList.add("fresh"));
      count = s.chat.length;
      log.scrollTo({ top: log.scrollHeight, behavior: "smooth" });
    }
    q("#co-form button").disabled = s.chatBusy;
  });
}
