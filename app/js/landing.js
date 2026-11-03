// View: Home. The landing page: what FeedForward does, a live preview fed by the shared state (no extra requests:
// it shows whatever plan the Service board has loaded), how it works, why a range, and the four views.
import { STATIC } from "./api.js";
import { replay, reveal, rollNumber, setHTML } from "./fx.js";
import { icon } from "./icons.js";
import { logoMark } from "./logo.js";
import { subscribe } from "./state.js";
import { cap, esc, fmt, riskLabel, shortDate } from "./util.js";

const REPO = "https://github.com/Laksh718/FeedForward";

const STEPS = [
  { icon: "data", t: "Real data in", d: "A year of simulated kitchen history on a real menu, a real academic calendar and real weather." },
  { icon: "spark", t: "Demand forecaster", d: "A conditional VAE learns the demand distribution and predicts a range: low, most likely, high." },
  { icon: "shield", t: "Surplus & anomaly detector", d: "Compares the usual plan against the forecast and the ingredient stock, and flags low, medium or high risk." },
  { icon: "chat", t: "Copilot explains", d: "A grounded language model turns the numbers into plain sentences. It never changes a quantity." },
  { icon: "person", t: "You decide", d: "The kitchen manager reviews, changes quantities if needed, and approves. Nothing acts on its own." },
];

const VIEWS = [
  { view: "service", icon: "service", title: "Service board", desc: "Today's headline, dish by dish ranges, the week chart, what if and the copilot.", go: "Plan a service", tone: "t-green" },
  { view: "desk", icon: "desk", title: "Forecast desk", desc: "Past week and next 7 days side by side, the full table and surplus risk at a glance.", go: "Open the desk", tone: "t-teal" },
  { view: "calendar", icon: "calendar", title: "Calendar", desc: "Holidays, festivals and exam weeks that move demand, cross-checked against a live calendar.", go: "See the month", tone: "t-amber" },
  { view: "admin", icon: "log", title: "Daily log", desc: "Record real attendance and consumption, so the next forecasts can learn from them.", go: "Log a day", tone: "t-ink" },
];

const FEATURES = ["Ranges, not single numbers", "Dish by dish quantities", "Surplus risk flags", "Weather and exam aware",
  "What if in one click", "A copilot that explains", "A person approves every plan", "Four meal slots a day"];

const marquee = () => {
  const row = FEATURES.map((f) => `<span class="ld-mq-item">${icon("leaf")}${f}</span>`).join("");
  return `<div class="ld-marquee" aria-hidden="true"><div class="ld-mq-track">${row}${row}</div></div>`;
};

// The "why a range" illustration: a demand curve, the likely band under it, the most likely amount and the usual
// plan further right, with the gap between them marked as likely surplus. Shapes only, no real numbers.
const RANGE_FIG = `
  <svg class="ld-curve" viewBox="0 0 520 270" role="img" aria-label="Illustration: a demand curve with the likely range shaded, the most likely amount at its peak, and the usual plan to the right of the range, where food is likely to be left over">
    <defs>
      <linearGradient id="ldBand" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#34D399" stop-opacity=".55"/><stop offset="1" stop-color="#5EEAD4" stop-opacity=".18"/></linearGradient>
      <clipPath id="ldUnder"><path d="M30 210C120 210 160 58 236 58S352 210 470 210Z"/></clipPath>
      <pattern id="ldHatch" width="8" height="8" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><rect width="3" height="8" fill="#C8432A" fill-opacity=".22"/></pattern>
    </defs>
    <line x1="20" x2="500" y1="210" y2="210" stroke="#0D2A1E" stroke-opacity=".18" stroke-width="1.5"/>
    <g clip-path="url(#ldUnder)"><rect class="ld-c-band" x="156" y="40" width="160" height="170" fill="url(#ldBand)"/></g>
    <rect class="ld-c-surplus" x="316" y="176" width="78" height="34" fill="url(#ldHatch)" rx="4"/>
    <path class="ld-c-line" d="M30 210C120 210 160 58 236 58S352 210 470 210" pathLength="1" fill="none" stroke="#0D2A1E" stroke-width="3" stroke-linecap="round"/>
    <line class="ld-c-mark" x1="236" x2="236" y1="52" y2="210" stroke="#0D2A1E" stroke-width="2.5"/>
    <line class="ld-c-usual" x1="394" x2="394" y1="70" y2="210" stroke="#C8432A" stroke-width="2.5" stroke-dasharray="7 6"/>
    <g class="ld-c-labels" font-family="Instrument Sans, system-ui, sans-serif" font-size="14" fill="#2A4638">
      <text x="156" y="234" text-anchor="middle">Low end</text>
      <text x="236" y="40" text-anchor="middle" font-weight="700" fill="#0D2A1E">Most likely</text>
      <text x="316" y="234" text-anchor="middle">High end</text>
      <text x="394" y="60" text-anchor="middle" font-weight="700" fill="#C8432A">Usual plan</text>
      <text x="355" y="256" text-anchor="middle" font-size="12.5" fill="#8A2A18">likely surplus</text>
    </g>
  </svg>`;

const SKELETON = `
  <section class="ld-hero">
    <div class="ld-hero-copy">
      <p class="ld-badge reveal"><span class="ld-pulse"></span>Demand forecasting for mess kitchens</p>
      <h1 class="ld-headline">
        <span class="reveal" style="--d:1">Predict.</span>
        <span class="reveal" style="--d:2">Prevent.</span>
        <span class="reveal ld-grad" style="--d:3">Provide.</span>
      </h1>
      <p class="ld-sub reveal" style="--d:4">FeedForward tells the kitchen how much of each dish to cook as a range, not a single guess.
        It flags surplus risk before food is wasted, explains every number in plain words, and a person always makes the final call.</p>
      <div class="ld-cta reveal" style="--d:5">
        <a class="btn btn-primary btn-lg" href="#service">Open the Service board ${icon("arrow")}</a>
        <button class="btn btn-lg" type="button" data-scroll="ld-how">See how it works</button>
      </div>
      <ul class="ld-proof reveal" style="--d:6">
        <li>${icon("check")}Conditional VAE forecaster</li><li>${icon("check")}Grounded copilot</li><li>${icon("check")}Human approval</li>
      </ul>
    </div>
    <div class="ld-hero-visual reveal" style="--d:3">
      <div class="ld-orb o1" aria-hidden="true"></div>
      <div class="ld-orb o2" aria-hidden="true"></div>
      <article class="ld-preview glass glow" id="ld-preview" aria-live="polite" aria-label="Live forecast preview"></article>
      <div class="ld-float f1" aria-hidden="true">${icon("sliders")}Range, not a guess</div>
      <div class="ld-float f2" aria-hidden="true">${icon("check")}Approved by a person</div>
    </div>
  </section>

  ${marquee()}

  <section class="ld-section" id="ld-how" aria-labelledby="ld-how-t">
    <div class="ld-head reveal">
      <p class="eyebrow">How it works</p>
      <h2 id="ld-how-t">From a year of data to a cooked quantity</h2>
      <p class="ld-lede">Five steps, and the last one is always a person's.</p>
    </div>
    <ol class="ld-steps reveal">
      ${STEPS.map((s, i) => `<li class="ld-step glass glow reveal lift" style="--d:${i}">
        <span class="ld-step-icon">${icon(s.icon)}</span><span class="ld-step-n">0${i + 1}</span>
        <h3>${s.t}</h3><p>${s.d}</p></li>`).join("")}
    </ol>
  </section>

  <section class="ld-section ld-range" aria-labelledby="ld-range-t">
    <div class="ld-range-copy reveal">
      <p class="eyebrow">Why a range</p>
      <h2 id="ld-range-t">One number is always a little wrong. A range says by how much.</h2>
      <p class="ld-lede">For every dish the forecaster predicts a low end, a most likely amount and a high end. FeedForward recommends a
        quantity inside that range with a small safety margin, so the line does not run dry, and sets it against the usual plan to show
        where food is likely to be left over.</p>
      <ul class="ld-keys">
        <li><i class="k band"></i><span><strong>Likely range</strong> from the low end to the high end</span></li>
        <li><i class="k tick"></i><span><strong>Most likely</strong> the single best estimate</span></li>
        <li><i class="k usual"></i><span><strong>Usual plan</strong> what the kitchen would cook anyway</span></li>
      </ul>
    </div>
    <figure class="ld-range-fig glass reveal" style="--d:1">${RANGE_FIG}<figcaption>Illustration of the idea, not real data.</figcaption></figure>
  </section>

  <section class="ld-section" aria-labelledby="ld-views-t">
    <div class="ld-head reveal">
      <p class="eyebrow">Four views, one kitchen</p>
      <h2 id="ld-views-t">Everything the kitchen needs before service</h2>
    </div>
    <div class="ld-cards">
      ${VIEWS.map((c, i) => `<a class="ld-card glass glow reveal lift ${c.tone}" style="--d:${i}" href="#${c.view}">
        <span class="ld-card-icon">${icon(c.icon)}</span><h3>${c.title}</h3><p>${c.desc}</p>
        <span class="ld-card-go">${c.go}${icon("arrow")}</span></a>`).join("")}
    </div>
  </section>

  <section class="ld-final glass reveal" aria-labelledby="ld-final-t">
    <div class="ld-final-orb" aria-hidden="true"></div>
    <div class="ld-final-mark" aria-hidden="true">${logoMark({ size: 64, className: "draw" })}</div>
    <h2 id="ld-final-t">Plan the next service with a range, not a guess.</h2>
    <p class="ld-lede">Open the Service board to see tomorrow's plan, try a what if, and approve it.</p>
    <div class="ld-cta">
      <a class="btn btn-primary btn-lg" href="#service">Open the Service board ${icon("arrow")}</a>
      <a class="btn btn-lg" href="${REPO}#run-it-yourself" target="_blank" rel="noopener">${icon("code")}${STATIC ? "Run it yourself" : "Read the code"}</a>
    </div>
  </section>

  <footer class="ld-foot">
    <div class="ld-foot-brand">${logoMark({ size: 28 })}<span>Feed<b>Forward</b></span></div>
    <p>Kitchen history is <strong>simulated</strong> on a real menu, a real academic calendar and real weather. No real world savings are
      claimed. See the data caveats in the <a href="${REPO}#readme" target="_blank" rel="noopener">README</a> before quoting a number.</p>
  </footer>`;

const loadingCard = `
  <div class="ld-pv-head"><span class="skel" style="width:36px;height:36px;border-radius:12px"></span>
    <div style="flex:1"><span class="skel-line" style="width:40%"></span><span class="skel-line" style="width:65%;margin-top:8px"></span></div></div>
  <div class="skel" style="height:64px;margin-top:22px"></div>
  <div class="skel" style="height:14px;margin-top:16px;border-radius:7px"></div>
  <div class="ld-snap-row"><div class="ld-snap-tile"><span class="ld-snap-label">Loading today's numbers&hellip;</span></div></div>`;

function previewCard(s) {
  if (s.error && !s.plan) {
    return `<div class="ld-pv-head"><span class="ld-pv-mark">${logoMark({ size: 36 })}</span><div><p class="ld-pv-kicker">Live forecast</p>
      <h2 class="ld-pv-title">Not available right now</h2></div></div><p class="ld-pv-error">${esc(s.error.message)} ${esc(s.error.fix || "")}</p>
      <div class="ld-snap-row"><div class="ld-snap-tile"><span class="ld-snap-value">&ndash;</span><span class="ld-snap-label">The views still explain how it works</span></div></div>`;
  }
  const p = s.plan;
  if (!s.health || !p) return loadingCard;
  const t = p.totals;
  const max = Math.max(t.p90, t.usual_plan || 0, t.recommended) * 1.08 || 1;
  const pct = (v) => `${((v / max) * 100).toFixed(2)}%`;
  const flagged = (p.risk_counts?.high ?? 0) + (p.risk_counts?.medium ?? 0);
  const top = p.dishes.slice(0, 3);
  return `
    <div class="ld-pv-head"><span class="ld-pv-mark">${logoMark({ size: 36 })}</span>
      <div><p class="ld-pv-kicker">Live forecast</p><h2 class="ld-pv-title">${cap(s.slot)}, ${esc(shortDate(p.date))}</h2></div>
      <span class="ld-pv-live"><i></i>Model</span></div>
    <div class="ld-pv-total"><span class="ld-pv-big num" data-roll="${t.recommended}">${fmt(t.recommended)}</span><span class="ld-pv-unit">portions to cook</span></div>
    <div class="ld-pv-range" aria-hidden="true"><i class="band" style="left:${pct(t.p10)};width:${pct(t.p90 - t.p10)}"></i>
      <i class="tick" style="left:${pct(t.p50)}"></i>${t.usual_plan ? `<i class="usual" style="left:${pct(t.usual_plan)}"></i>` : ""}</div>
    <p class="ld-pv-cap num">Likely ${fmt(t.p10)} to ${fmt(t.p90)}${t.usual_plan ? `, usual plan ${fmt(t.usual_plan)}` : ""}.</p>
    ${top.length ? `<ul class="ld-pv-dishes">${top.map((d, i) => `<li style="--i:${i}"><span class="risk-dot ${d.surplus_risk}" title="${riskLabel(d.surplus_risk, true)}"></span>
      <span class="nm">${esc(d.dish_name)}</span><span class="qty num">${fmt(d.recommended)}</span></li>`).join("")}</ul>` : ""}
    <div class="ld-snap-row">
      <div class="ld-snap-tile"><span class="ld-snap-value num">${fmt(p.expected_attendance)}</span><span class="ld-snap-label">Expected at ${s.slot}</span></div>
      <div class="ld-snap-tile"><span class="ld-snap-value">${flagged || "None"}</span><span class="ld-snap-label">${flagged ? "Dishes at medium or high risk" : "Dishes at surplus risk"}</span></div>
      <div class="ld-snap-tile"><span class="ld-snap-value">${esc(s.health.data_source_short)}</span><span class="ld-snap-label">Data source</span></div>
    </div>
    <a class="ld-pv-open" href="#service">Open this plan${icon("arrow")}</a>`;
}

export function mountLanding(root) {
  root.innerHTML = SKELETON;
  reveal(root);
  root.querySelectorAll("[data-scroll]").forEach((b) => b.addEventListener("click", () => {
    root.querySelector(`#${b.dataset.scroll}`)?.scrollIntoView({ behavior: "smooth", block: "start" });
  }));
  const card = root.querySelector("#ld-preview");
  let shown = null;
  subscribe((s) => {
    if (!setHTML(card, previewCard(s))) return;
    const big = card.querySelector("[data-roll]");
    if (big) {
      const to = Number(big.dataset.roll);
      rollNumber(big, shown ?? Math.round(to * 0.6), to, shown === null ? 1100 : 650);
      if (shown === null) replay(card, "ld-pv-in", 1200);
      shown = to;
    }
  });
}
