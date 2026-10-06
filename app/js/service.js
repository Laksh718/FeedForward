// View A: Service board.
import { bindChart, chartService } from "./charts.js";
import { ask, review, setAdjusted, setDate, setEditing, setScope, setSlot, state, subscribe } from "./state.js";
import { SLOTS, cap, esc, fmt, riskLabel, weekdayName } from "./util.js";
import { mountWhatIf } from "./whatif.js";

const CHIPS = ["Explain the range", "What if it rains?", "Summarise the week"];

const SKELETON = `
  <header class="sv-top">
    <div><div class="sv-brand">FeedForward</div><p class="sv-sub" id="sv-sub"></p></div>
    <div class="sv-tools">
      <div class="sv-pills" role="group" aria-label="Meal slot">${SLOTS.map((s) => `<button type="button" data-slot="${s}" aria-pressed="false">${cap(s)}</button>`).join("")}</div>
      <span class="sv-chip" id="sv-chip"></span>
    </div>
  </header>
  <section class="sv-hero" aria-live="polite">
    <div class="sv-hero-text"><h1 class="sv-headline" id="sv-headline">Loading the forecast</h1><p class="sv-support" id="sv-support"></p><div id="sv-note"></div></div>
    <div class="sv-actions">
      <button class="btn btn-primary" id="sv-approve" type="button">Approve this plan</button>
      <button class="btn btn-ghost" id="sv-change" type="button" aria-pressed="false">Change quantities</button>
      <p class="sv-status" id="sv-status" aria-live="polite"></p>
    </div>
  </section>
  <div class="sv-grid">
    <div>
      <div class="sv-section-head"><h2>Dish by dish</h2><p class="sv-legend-text">Green bar is the likely range. Tick is the most likely amount. Red line is the usual plan.</p></div>
      <div id="sv-tickets" class="tickets"></div>
      <button class="btn show-all" id="sv-showall" type="button" hidden></button>
      <section class="card weekcard" aria-labelledby="sv-week-title">
        <div class="sv-section-head"><h2 id="sv-week-title"></h2><p class="sv-legend-text" id="sv-week-sub"></p></div>
        <div class="chart" id="sv-chart"></div>
        <div class="legend"><span><i class="swatch" style="background:#9CC4AE"></i>Likely range</span><span><i style="background:#15291F"></i>Most likely</span><span><i class="dash"></i>Usual plan</span></div>
      </section>
      <section class="whatif" aria-labelledby="sv-wi-title"><h2 id="sv-wi-title">Try a what if</h2><div id="sv-whatif"></div></section>
    </div>
    <aside class="card copilot" aria-labelledby="sv-co-title">
      <div class="copilot-head"><h2 id="sv-co-title">Ask the kitchen copilot</h2><p>It explains the numbers on this page. It does not change quantities.</p></div>
      <div class="chat-log" id="sv-log" aria-live="polite"></div>
      <div class="chips">${CHIPS.map((c) => `<button type="button" class="chip-btn">${c}</button>`).join("")}</div>
      <form class="chat-form" id="sv-form"><label class="sr-only" for="sv-q">Ask about a dish or a change</label>
        <input id="sv-q" autocomplete="off" placeholder="Ask about a dish or a change"><button class="btn" type="submit">Send</button></form>
    </aside>
  </div>`;

function rangeBar(d, rec) {
  const max = Math.max(d.p90, d.usual_plan, rec) * 1.12 || 1;
  const pos = (v) => `${(v / max) * 100}%`;
  return `<div class="rangebar" aria-hidden="true"><div class="band" style="left:${pos(d.p10)};width:${((d.p90 - d.p10) / max) * 100}%"></div>` +
    `<div class="tick" style="left:${pos(d.p50)}"></div>${d.usual_plan ? `<div class="usual" style="left:${pos(d.usual_plan)}"></div>` : ""}</div>`;
}

function ticket(d, s) {
  const qty = s.adjusted[d.dish_id] ?? d.recommended;
  const big = s.editing
    ? `<input type="number" min="0" step="5" value="${qty}" data-dish="${d.dish_id}" aria-label="Portions to cook for ${esc(d.dish_name)}">`
    : `<span class="big num">${fmt(qty)}</span>`;
  const usual = d.usual_plan ? `Usual plan is ${fmt(d.usual_plan)}.` : "No usual plan yet for this dish.";
  return `<article class="ticket"><div class="ticket-head"><h3 class="ticket-name">${esc(d.dish_name)}</h3><span class="pill ${d.surplus_risk}">${riskLabel(d.surplus_risk, true)}</span></div>
    <div class="ticket-qty">${big}<span class="unit">portions to cook</span></div>${rangeBar(d, qty)}
    <p class="ticket-cap num">Likely ${fmt(d.p10)} to ${fmt(d.p90)}. ${usual}</p></article>`;
}

export function mountService(root) {
  root.innerHTML = SKELETON;
  const q = (s) => root.querySelector(s);
  mountWhatIf(q("#sv-whatif"), { gridClass: "whatif-grid" });

  root.querySelectorAll("[data-slot]").forEach((b) => b.addEventListener("click", () => setSlot(b.dataset.slot)));
  q("#sv-approve").addEventListener("click", () => review("approve"));
  q("#sv-change").addEventListener("click", () => setEditing(!state.editing));
  q("#sv-showall").addEventListener("click", () => setScope(state.scope === "core" ? "all" : "core"));
  q("#sv-tickets").addEventListener("input", (e) => {
    if (e.target.dataset.dish) setAdjusted(e.target.dataset.dish, Math.max(0, Math.round(Number(e.target.value) || 0)));
  });
  const send = (text) => { ask(text); q("#sv-q").value = ""; };
  q("#sv-form").addEventListener("submit", (e) => { e.preventDefault(); send(q("#sv-q").value); });
  root.querySelectorAll(".chip-btn").forEach((b) => b.addEventListener("click", () => send(b.textContent)));

  subscribe((s) => {
    const p = s.plan;
    root.querySelectorAll("[data-slot]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.slot === s.slot)));
    q("#sv-chip").textContent = s.health?.data_source_short ?? "";
    q("#sv-chip").title = s.health?.data_source_chip ?? "";
    q("#sv-sub").textContent = `Main mess kitchen, forecast for ${s.date ? weekdayName(s.date) : "..."}`;
    const tickets = q("#sv-tickets");
    if (s.error) {
      q("#sv-headline").textContent = "The forecast could not be loaded";
      q("#sv-support").textContent = "";
      tickets.innerHTML = `<div class="card empty" style="grid-column:1/-1"><strong>${esc(s.error.message)}</strong>${esc(s.error.fix || "")}</div>`;
    } else if (!p) {
      tickets.innerHTML = `<div class="card empty" style="grid-column:1/-1"><strong>Loading the forecast</strong>This takes a moment.</div>`;
    } else if (!p.dishes.length) {
      q("#sv-headline").textContent = `No ${s.slot} is planned for ${weekdayName(s.date)}`;
      q("#sv-support").textContent = "";
      tickets.innerHTML = `<div class="card empty" style="grid-column:1/-1"><strong>No dishes are on the menu for this slot.</strong>Pick another meal slot above.</div>`;
    } else {
      const total = p.dishes.reduce((a, d) => a + (s.adjusted[d.dish_id] ?? d.recommended), 0);
      const changed = s.editing && total !== p.totals.recommended;
      q("#sv-headline").textContent = p.headline;
      q("#sv-support").textContent = changed
        ? `With your changes the total is ${fmt(total)} portions, ${fmt(Math.abs(total - p.totals.recommended))} ${total > p.totals.recommended ? "more" : "fewer"} than recommended.`
        : p.supporting;
      const typing = s.editing && document.activeElement?.tagName === "INPUT" && tickets.contains(document.activeElement);
      if (!typing) tickets.innerHTML = p.dishes.map((d) => ticket(d, s)).join(""); // keep focus while the person types
    }
    const hasWhatIf = Object.keys(s.overrides).length > 0;
    q("#sv-note").innerHTML = hasWhatIf ? `<p class="sv-note">This is a what if, not the saved plan. Approving saves it with your changes listed.</p>` : "";
    const all = s.scope === "all", hidden = p?.dishes_hidden ?? 0;
    const btn = q("#sv-showall");
    btn.hidden = !p || (!all && hidden === 0);
    btn.textContent = all ? "Show main dishes only" : `Show all dishes (${hidden} more)`;
    q("#sv-change").setAttribute("aria-pressed", String(s.editing));
    q("#sv-change").textContent = s.editing ? "Done changing" : "Change quantities";
    const r = p?.review;
    q("#sv-status").textContent = s.notice || (r ? `${r.decision === "approve" ? "Approved" : "Sent back"} on ${r.reviewed_at.replace("T", " at ")}.` : "");
    q("#sv-approve").disabled = !p || !p.dishes.length;

    q("#sv-week-title").textContent = `${cap(s.slot)} demand this week`;
    q("#sv-week-sub").textContent = s.scope === "all" ? "Total portions across all dishes" : "Total portions across the main dishes";
    const chart = q("#sv-chart");
    if (s.week) {
      chart.innerHTML = chartService(s.week, s.date);
      bindChart(chart, s.week, (d) => d !== s.date && setDate(d));
    }
    const log = q("#sv-log");
    log.innerHTML = s.chat.length ? s.chat.map((m) => `<div class="bubble ${m.role}">${esc(m.text)}</div>`).join("") + (s.chatBusy ? `<div class="bubble bot">Working on it</div>` : "")
      : `<div class="bubble bot">Ask why a dish is above or below the usual plan, or what a change would do. I only use the numbers on this page.</div>`;
    log.scrollTop = log.scrollHeight;
  });
}
