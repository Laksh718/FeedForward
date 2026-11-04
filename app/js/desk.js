// View: Forecast desk. A side rail of sections, the past week next to the forecast, the full table, what if,
// surplus risk, approvals and a question box.
import { bindChart, chartDesk } from "./charts.js";
import { liquid, replay, setHTML } from "./fx.js";
import { icon } from "./icons.js";
import { logoMark } from "./logo.js";
import { ask, review, setDate, setDish, setScope, state, subscribe } from "./state.js";
import { cap, esc, fmt, riskLabel, shortDate, sourceNote, weekdayName } from "./util.js";
import { mountWhatIf } from "./whatif.js";

const NAV = [["forecast", "Forecast", "desk"], ["whatif", "What if", "sliders"], ["risk", "Surplus risk", "alert"], ["approvals", "Approvals", "check"], ["copilot", "Copilot", "chat"]];
const CHIPS = ["Explain the Monday and Tuesday rise", "Why is the usual plan higher?", "Which dishes are at risk?"];
const TOP_BUTTONS = 4;

const SKELETON = `
  <aside class="dk-rail glass">
    <div class="dk-brand">${logoMark({ size: 38 })}<span>Forecast desk<small>Main mess kitchen</small></span></div>
    <nav class="dk-nav" aria-label="Forecast desk sections">${NAV.map(([k, t, ic]) =>
      `<button type="button" data-nav="${k}">${icon(ic)}${t}</button>`).join("")}</nav>
    <p class="dk-rail-foot" id="dk-foot"></p>
  </aside>
  <div class="dk-main">
    <header class="dk-top glass">
      <div><p class="eyebrow">${icon("desk")}Next 7 days</p><h1 class="dk-title" id="dk-title"></h1><p class="dk-sub" id="dk-sub"></p></div>
      <div class="dk-actions"><span class="status" id="dk-status" role="status">Waiting for your review</span>
        <button class="btn btn-danger" id="dk-back" type="button">${icon("back")}Send back</button>
        <button class="btn btn-primary" id="dk-approve" type="button">${icon("check")}Approve plan</button></div>
      <p class="dk-notice" id="dk-notice" role="status"></p>
    </header>
    <div id="dk-error"></div>
    <section data-panel="forecast" class="dk-panel">
      <div class="dk-card glass"><div class="dishpick" id="dk-pick" role="group" aria-label="Choose a dish for the chart"></div>
        <div class="chart" id="dk-chart"></div>
        <div class="legend"><span><i style="background:#8AA094"></i>Eaten last week</span><span><i class="swatch" style="background:linear-gradient(180deg,#6EE7B7,#99F6E4)"></i>Likely range</span>
          <span><i style="background:#0D2A1E"></i>Most likely</span><span><i style="background:#C8432A"></i>Recommended to cook</span></div></div>
      <div class="dk-card glass"><h2 id="dk-table-title"></h2><div class="tablewrap" id="dk-table"></div><button class="btn link-btn" id="dk-showall" type="button" hidden></button></div>
    </section>
    <section data-panel="whatif" class="dk-panel" hidden><div class="dk-card glass"><h2>${icon("sliders")}What if</h2>
      <p class="dk-panel-note">Change one thing and see how the plan moves. Nothing is saved until you approve.</p><div id="dk-whatif"></div></div></section>
    <section data-panel="risk" class="dk-panel" hidden><div class="dk-card glass"><h2 id="dk-risk-title">Surplus risk</h2><div id="dk-risk"></div></div></section>
    <section data-panel="approvals" class="dk-panel" hidden><div class="dk-card glass"><h2>Approvals</h2><div id="dk-approvals"></div></div></section>
    <section class="dk-ask glass" id="dk-ask" data-panel="forecast copilot whatif risk approvals" aria-labelledby="dk-ask-title">
      <div><h2 id="dk-ask-title">${icon("chat")}Ask about this forecast</h2>
        <p class="sub">Answers use only the figures on this page. The copilot explains, and you decide.</p>
        <form class="ask-form" id="dk-form"><label class="sr-only" for="dk-q">Your question</label>
          <input id="dk-q" autocomplete="off" placeholder="Why is Tuesday so high?"><button class="btn btn-primary" type="submit">${icon("send")}Ask</button></form>
        <div class="dk-chips">${CHIPS.map((c) => `<button type="button">${c}</button>`).join("")}</div></div>
      <div class="answer" id="dk-answer" aria-live="polite"></div>
    </section>
  </div>`;

function table(p, s) {
  const rows = p.dishes;
  const head = ["Dish", "Low end", "Most likely", "High end", "Usual plan", "Cook", "Surplus risk"].map((h) => `<th scope="col">${h}</th>`).join("");
  const body = rows.map((d) => `<tr><td>${esc(d.dish_name)}</td><td>${fmt(d.p10)}</td><td>${fmt(d.p50)}</td><td>${fmt(d.p90)}</td>
    <td>${d.usual_plan ? fmt(d.usual_plan) : "none"}</td><td class="cook">${fmt(d.recommended)}</td><td><span class="pill ${d.surplus_risk}">${riskLabel(d.surplus_risk)}</span></td></tr>`).join("");
  const t = p.totals;
  const label = s.scope === "all" ? "All dishes" : "Main dishes";
  return `<table class="dishes"><thead><tr>${head}</tr></thead><tbody>${body}
    <tr class="total"><td>${label}</td><td>${fmt(t.p10)}</td><td>${fmt(t.p50)}</td><td>${fmt(t.p90)}</td><td>${fmt(t.usual_plan)}</td><td class="cook">${fmt(t.recommended)}</td><td></td></tr></tbody></table>`;
}

function riskPanel(p) {
  const order = ["high", "medium", "low"];
  return `<p class="dk-panel-note">Surplus risk compares the usual plan and forecast range with ingredient expiry and stock cover, and takes the higher of the two.</p>` +
    (p.inventory_risk_available === false ? `<p class="dk-panel-note">Stock data not available for this date, risk is based on demand only.</p>` : "") +
    order.map((lvl) => {
      const list = p.dishes.filter((d) => d.surplus_risk === lvl);
      return `<div class="riskgroup"><h3><span class="pill ${lvl}">${riskLabel(lvl)}</span>${list.length} dish${list.length === 1 ? "" : "es"}</h3>` +
        (list.length ? `<ul>${list.map((d) => `<li><span>${esc(d.dish_name)}</span><span class="num">Usual plan ${d.usual_plan ? fmt(d.usual_plan) : "none"}, likely ${fmt(d.p10)} to ${fmt(d.p90)}</span></li>`).join("")}</ul>` : "") + "</div>";
    }).join("");
}

export function mountDesk(root) {
  root.innerHTML = SKELETON;
  const q = (s) => root.querySelector(s);
  let panel = "forecast";
  const showPanel = () => {
    root.querySelectorAll("[data-nav]").forEach((b) => {
      if (b.dataset.nav === panel) b.setAttribute("aria-current", "page"); else b.removeAttribute("aria-current");
    });
    root.querySelectorAll("[data-panel]").forEach((el) => {
      const on = el.dataset.panel.split(" ").includes(panel);
      if (on && el.hidden) replay(el, "panel-in", 700);
      el.hidden = !on;
    });
  };
  root.querySelectorAll("[data-nav]").forEach((b) => b.addEventListener("click", () => { panel = b.dataset.nav; showPanel(); }));
  liquid(q(".dk-nav"));
  mountWhatIf(q("#dk-whatif"), { gridClass: "wi-grid", fieldClass: "wi-field" });

  q("#dk-approve").addEventListener("click", () => review("approve"));
  q("#dk-back").addEventListener("click", () => review("send_back"));
  q("#dk-showall").addEventListener("click", () => {
    setScope(state.scope === "core" ? "all" : "core");
  });
  const send = (t) => { ask(t); q("#dk-q").value = ""; };
  q("#dk-form").addEventListener("submit", (e) => { e.preventDefault(); send(q("#dk-q").value); });
  q("#dk-ask").querySelectorAll(".dk-chips button").forEach((b) => b.addEventListener("click", () => send(b.textContent)));
  q("#dk-pick").addEventListener("click", (e) => { const b = e.target.closest("button[data-dish]"); if (b) setDish(b.dataset.dish || null); });
  q("#dk-pick").addEventListener("change", (e) => { if (e.target.tagName === "SELECT") setDish(e.target.value || null); });

  let chartFor = null;
  subscribe((s) => {
    const p = s.plan;
    q("#dk-foot").textContent = s.health?.data_source_chip ?? "";
    q("#dk-title").textContent = `${cap(s.slot)} forecast, next 7 days`;
    q("#dk-sub").textContent = "Past demand on the left, the model's forecast on the right.";
    q("#dk-notice").textContent = s.notice;
    setHTML(q("#dk-error"), s.error ? `<div class="banner" style="margin:16px 0 0;width:auto"><strong>${esc(s.error.message)}</strong>${esc(s.error.fix || "")}</div>` : "");
    const r = p?.review, status = q("#dk-status");
    status.className = `status ${r ? r.decision : ""}`;
    status.textContent = r ? (r.decision === "approve" ? "Approved" : "Sent back") : "Waiting for your review";
    q("#dk-approve").disabled = q("#dk-back").disabled = !p || !p.dishes.length;
    showPanel();

    if (s.week) {
      // dish buttons: all (or main) dishes, then the top few dishes by quantity, then the rest in a list
      const top = (p?.dishes ?? []).slice(0, TOP_BUTTONS), topIds = new Set(top.map((d) => d.dish_id));
      const rest = s.menu.filter((d) => !topIds.has(d.dish_id));
      setHTML(q("#dk-pick"), `<button type="button" data-dish="" aria-pressed="${!s.dishId}">${s.scope === "all" ? "All dishes" : "Main dishes"}</button>` +
        top.map((d) => `<button type="button" data-dish="${d.dish_id}" aria-pressed="${s.dishId === d.dish_id}">${esc(d.dish_name)}</button>`).join("") +
        (rest.length ? `<label class="sr-only" for="dk-more">More dishes</label><select id="dk-more"><option value="">More dishes</option>${rest.map((d) => `<option value="${d.dish_id}" ${s.dishId === d.dish_id ? "selected" : ""}>${esc(d.dish_name)}</option>`).join("")}</select>` : ""));
      const data = s.dishId && s.weekDish ? s.weekDish : s.week;
      if (chartFor?.data !== data || chartFor.date !== s.date) {
        const chart = q("#dk-chart");
        chart.classList.toggle("static", chartFor?.data === data);
        chart.innerHTML = chartDesk(data, s.date);
        bindChart(chart, data, (d) => d !== s.date && setDate(d), (d) => `<br>Recommended to cook ${fmt(d.recommended)}`);
        chartFor = { data, date: s.date };
      }
    }
    if (p) {
      q("#dk-table-title").textContent = `${weekdayName(s.date)} ${s.slot}, dish by dish`;
      setHTML(q("#dk-table"), p.dishes.length ? table(p, s) : `<div class="empty"><strong>No dishes are on the menu for this slot.</strong>Pick another day in the chart.</div>`);
      const more = p.dishes_hidden, btn = q("#dk-showall");
      btn.hidden = s.scope === "core" && more === 0;
      setHTML(btn, `${icon("list")}${s.scope === "all" ? "Show main dishes only" : `Show all dishes (${more} more)`}`);
      setHTML(q("#dk-risk"), riskPanel(p));
      q("#dk-risk-title").textContent = `Surplus risk, ${shortDate(s.date)}`;
      setHTML(q("#dk-approvals"), `<p class="dk-panel-note">You are reviewing the ${s.slot} plan for ${shortDate(s.date)}.</p>` +
        (r ? `<p class="dk-review ${r.decision}">${icon(r.decision === "approve" ? "check" : "back")}${r.decision === "approve" ? "Approved" : "Sent back"} on ${esc(r.reviewed_at.replace("T", " at "))}.</p>` : `<p>Nobody has approved or sent back this plan yet.</p>`) +
        `<p class="dk-panel-note" style="margin-top:12px">Approve plan saves the plan with the forecast you see now. Send back saves your decision so the plan can be revisited.</p>`);
    }
    const last = [...s.chat].reverse().find((m) => m.role !== "user");
    const lastQ = [...s.chat].reverse().find((m) => m.role === "user");
    const ans = q("#dk-answer");
    ans.className = `answer ${last?.role === "err" ? "err" : ""}`;
    setHTML(ans, s.chatBusy ? `<p class="q">${esc(lastQ?.text ?? "")}</p><p class="typing-line"><span class="dots"><i></i><i></i><i></i></span>Working on it</p>`
      : last ? `<p class="q">${esc(lastQ?.text ?? "")}</p><p class="a">${esc(last.text)}</p>${sourceNote(last) ? `<p class="src">${sourceNote(last)}</p>` : ""}`
        : `<p class="empty-note">${icon("chat")}Ask a question and the answer appears here. It only uses the figures on this page.</p>`);
  });
}
