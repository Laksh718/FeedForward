// View: Landing. First screen a visitor sees. Static content plus a small live snapshot pulled from the
// shared state (no extra network calls -- it reuses whatever the Service board has already loaded).
import { state, subscribe } from "./state.js";
import { fmt } from "./util.js";

const STEPS = [
  { n: "01", t: "Real data in", d: "A year of simulated kitchen history on a real menu, a real academic calendar and real weather." },
  { n: "02", t: "Demand forecaster", d: "A conditional VAE learns the demand distribution and predicts a range: low, most likely, high." },
  { n: "03", t: "Surplus & anomaly detector", d: "Compares the usual plan against the forecast and the ingredient stock, and flags low, medium or high risk." },
  { n: "04", t: "Copilot explains", d: "A grounded language model turns the numbers into plain sentences. It never changes a quantity." },
  { n: "05", t: "You decide", d: "The kitchen manager reviews, changes quantities if needed, and approves. Nothing acts on its own." },
];

const CARDS = [
  { view: "service", title: "Service board", desc: "Today's headline, dish by dish ranges, the week chart and the copilot.", cls: "card-service" },
  { view: "desk", title: "Forecast desk", desc: "Past week and next 7 days, the full table, surplus risk at a glance.", cls: "card-desk" },
  { view: "calendar", title: "Calendar", desc: "Holidays, festivals and exam weeks, cross-checked against a live calendar.", cls: "card-cal" },
  { view: "admin", title: "Daily log", desc: "Record real attendance and consumption, and feed it back into the model.", cls: "card-admin" },
];

const SKELETON = `
  <section class="ld-hero">
    <div class="ld-blob b1" aria-hidden="true"></div>
    <div class="ld-blob b2" aria-hidden="true"></div>
    <div class="ld-blob b3" aria-hidden="true"></div>
    <p class="ld-kicker reveal">FeedForward</p>
    <h1 class="ld-headline">
      <span class="reveal" style="--d:0">Predict.</span>
      <span class="reveal" style="--d:1">Prevent.</span>
      <span class="reveal" style="--d:2">Provide.</span>
    </h1>
    <p class="ld-sub reveal" style="--d:3">A range, not a single number, for how much to cook &mdash; so the kitchen wastes less and never runs
      short, and a person always makes the final call.</p>
    <div class="ld-cta reveal" style="--d:4">
      <a class="btn btn-primary" href="#service">Open the Service board</a>
      <a class="btn btn-ghost" href="#calendar">See the calendar</a>
    </div>
    <div class="ld-snapshot" id="ld-snapshot" aria-live="polite"></div>
  </section>

  <section class="ld-steps" aria-labelledby="ld-steps-title">
    <h2 id="ld-steps-title" class="reveal">From a year of data to a cooked quantity</h2>
    <div class="ld-step-grid">
      ${STEPS.map((s, i) => `<div class="ld-step reveal" style="--d:${i}"><span class="ld-step-n">${s.n}</span><h3>${s.t}</h3><p>${s.d}</p></div>`).join("")}
    </div>
  </section>

  <section class="ld-views" aria-labelledby="ld-views-title">
    <h2 id="ld-views-title" class="reveal">Four views, one kitchen</h2>
    <div class="ld-card-grid">
      ${CARDS.map((c, i) => `<a class="ld-card ${c.cls} reveal" style="--d:${i}" href="#${c.view}">
          <h3>${c.title}</h3><p>${c.desc}</p><span class="ld-card-go">Open &#8594;</span></a>`).join("")}
    </div>
  </section>

  <footer class="ld-foot reveal">
    <p>Kitchen history is <strong>simulated</strong> on a real menu, a real academic calendar and real weather. No real
      world savings are claimed &mdash; see the data caveats in the README before quoting a number.</p>
  </footer>`;

function snapshot(s) {
  const p = s.plan;
  if (!s.health) return `<div class="ld-snap-tile"><span class="ld-snap-label">Loading today's numbers&hellip;</span></div>`;
  const atRisk = p?.dishes?.filter((d) => d.surplus_risk !== "low").length ?? null;
  const tiles = [
    { label: "Project's today", value: s.health.today },
    { label: "Data source", value: s.health.data_source_short },
    p ? { label: `${s.slot[0].toUpperCase()}${s.slot.slice(1)} expected attendance`, value: fmt(p.expected_attendance) } : null,
    p ? { label: "Dishes flagged", value: atRisk ? `${atRisk} at medium/high surplus risk` : "None, all low risk" } : null,
  ].filter(Boolean);
  return tiles.map((t) => `<div class="ld-snap-tile"><span class="ld-snap-value">${t.value}</span><span class="ld-snap-label">${t.label}</span></div>`).join("");
}

function initReveal(root) {
  const els = root.querySelectorAll(".reveal");
  if (!("IntersectionObserver" in window)) { els.forEach((el) => el.classList.add("in")); return; }
  const io = new IntersectionObserver((entries) => {
    entries.forEach((e) => { if (e.isIntersecting) { e.target.classList.add("in"); io.unobserve(e.target); } });
  }, { threshold: .2 });
  els.forEach((el) => io.observe(el));
}

export function mountLanding(root) {
  root.innerHTML = SKELETON;
  initReveal(root);
  subscribe((s) => { root.querySelector("#ld-snapshot").innerHTML = snapshot(s); });
}
