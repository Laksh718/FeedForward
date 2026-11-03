// Hand written SVG charts. No chart library. Lines carry pathLength="1" and the class "ln" so they draw in
// (css/base.css); the views only re-render a chart when its data or the selected day changes.
import { dayMs, esc, fmt, hideTip, niceTicks, parseDay, runs, shortDate, showTip } from "./util.js";

const path = (pts) => pts.map(([x, y], i) => `${i ? "L" : "M"}${x.toFixed(1)},${y.toFixed(1)}`).join("");
const segments = (vals, fx, fy) => {      // polyline pieces that skip missing values (0 or null)
  const out = [];
  let cur = [];
  vals.forEach((v, i) => { if (v > 0) cur.push([fx(i), fy(v)]); else if (cur.length) { out.push(cur); cur = []; } });
  if (cur.length) out.push(cur);
  return out;
};

// A forecast day with no menu for that slot (or, for a single dish, not served that day) comes back as all
// zeros with an empty `facts`. Drawing straight through those days plunges the line and band to zero, so every
// forecast series below only draws across the contiguous runs where the day actually has data.
const hasData = (days) => days.map((d) => Object.keys(d.facts || {}).length > 0);
const seriesPath = (days, fx, fy, key, present) => runs(present).map(([a, b]) =>
  path(days.slice(a, b + 1).map((d, k) => [fx(a + k), fy(d[key])]))).join(" ");
const bandPath = (days, fx, fy, present) => runs(present).map(([a, b]) => {
  const top = days.slice(a, b + 1).map((d, k) => `${fx(a + k).toFixed(1)},${fy(d.p90).toFixed(1)}`);
  const bottom = days.slice(a, b + 1).reverse().map((d, k) => `${fx(b - k).toFixed(1)},${fy(d.p10).toFixed(1)}`);
  return `M${top.join("L")}L${bottom.join("L")}Z`;
}).join(" ");
const seriesDots = (days, fx, fy, key, present, selected, fill, extra = "") => days.map((d, i) =>
  present[i] ? `<circle class="pt" style="--i:${i}" cx="${fx(i).toFixed(1)}" cy="${fy(d[key]).toFixed(1)}" r="${d.date === selected ? 6.5 : 4.5}" fill="${fill}"${extra}/>` : "").join("");
const line = (d, stroke, width, cls = "ln") => (d ? `<path class="${cls}" pathLength="1" d="${d}" fill="none" stroke="${stroke}" stroke-width="${width}" stroke-linecap="round" stroke-linejoin="round"/>` : "");

// theme: colours for the view the chart sits in
export const THEMES = {
  service: { grid: "rgba(13,42,30,.08)", axis: "#546B5F", bandTop: "#34D399", bandBottom: "#5EEAD4", likely: "#0D2A1E", usual: "#C8432A", exam: "#FBEFCF", examText: "#7A5A12", sel: "#12855A" },
  desk: { grid: "rgba(13,42,30,.08)", axis: "#546B5F", bandTop: "#34D399", bandBottom: "#5EEAD4", likely: "#0D2A1E", rec: "#C8432A", past: "#8AA094", exam: "#FBEFCF", examText: "#7A5A12", sel: "#12855A" },
};

const bandDefs = (id, th) => `<defs><linearGradient id="${id}" x1="0" y1="0" x2="0" y2="1">` +
  `<stop offset="0" stop-color="${th.bandTop}" stop-opacity=".62"/><stop offset="1" stop-color="${th.bandBottom}" stop-opacity=".26"/></linearGradient></defs>`;

function frame(W, H, ml, mr, mt, mb, lo, hi, ticks, th) {
  const pw = W - ml - mr, ph = H - mt - mb;
  const y = (v) => mt + ph * (1 - (v - lo) / (hi - lo));
  const grid = ticks.map((t) => `<line x1="${ml}" x2="${W - mr}" y1="${y(t)}" y2="${y(t)}" stroke="${th.grid}"/>` +
    `<text x="${ml - 10}" y="${y(t) + 4}" text-anchor="end" font-size="13" fill="${th.axis}">${fmt(t)}</text>`).join("");
  return { pw, ph, y, grid };
}

function dayLabels(items, x, yPos, selected, th) {
  return items.map((d, i) => {
    const on = d.date === selected;
    return `<g class="daybtn" role="button" tabindex="0" data-date="${d.date}" aria-label="Show ${esc(shortDate(d.date))}" style="cursor:pointer">` +
      (on ? `<rect x="${x(i) - 26}" y="${yPos - 19}" width="52" height="28" rx="14" fill="${th.sel}" fill-opacity=".13"/>` : "") +
      `<text x="${x(i)}" y="${yPos}" text-anchor="middle" font-size="14" fill="${on ? th.sel : th.axis}" font-weight="${on ? 700 : 500}">${esc(d.weekday)}</text></g>`;
  }).join("");
}

function examShade(days, x, step, mt, ph, th, labelY, offset = 0) {
  return runs(days.map((d) => d.exam_week)).map(([a, b]) =>
    `<rect x="${x(a + offset) - step / 2}" y="${mt}" width="${(b - a + 1) * step}" height="${ph}" rx="8" fill="${th.exam}"/>` +
    `<text x="${(x(a + offset) + x(b + offset)) / 2}" y="${labelY}" text-anchor="middle" font-size="13" fill="${th.examText}">Exam week</text>`).join("");
}

const guide = (mt, ph) => `<line class="guide" x1="0" x2="0" y1="${mt}" y2="${mt + ph}" stroke="#0D2A1E" stroke-opacity=".25" stroke-dasharray="3 4"/>`;

function tipHtml(d, extra = "") {
  if (!Object.keys(d.facts || {}).length) return `<strong>${esc(shortDate(d.date))}</strong><br>Not on the menu this day.`;
  return `<strong>${esc(shortDate(d.date))}</strong><br>Most likely ${fmt(d.p50)}<br>Likely range ${fmt(d.p10)} to ${fmt(d.p90)}<br>Usual plan ${d.usual_plan ? fmt(d.usual_plan) : "none"}${extra}`;
}

// Service board: likely range band, most likely line, dashed usual plan, exam week shading.
export function chartService(week, selected) {
  const th = THEMES.service, days = week.days, n = days.length;
  const W = 880, H = 330, ml = 62, mr = 14, mt = 12, mb = 62;
  const vals = days.flatMap((d) => [d.p10, d.p90, d.usual_plan]).filter((v) => v > 0);
  const ticks = niceTicks(Math.min(...vals) * 0.92, Math.max(...vals) * 1.04);
  const lo = ticks[0], hi = ticks[ticks.length - 1];
  const { pw, ph, y, grid } = frame(W, H, ml, mr, mt, mb, lo, hi, ticks, th);
  const step = pw / n, x = (i) => ml + step * (i + 0.5);
  const present = hasData(days);
  const band = bandPath(days, x, y, present);
  const usual = segments(days.map((d) => d.usual_plan), x, y).map((s) => `<path class="fade" d="${path(s)}" fill="none" stroke="${th.usual}" stroke-width="2.2" stroke-dasharray="7 6"/>`).join("");
  const likely = line(seriesPath(days, x, y, "p50", present), th.likely, 2.8);
  const dots = seriesDots(days, x, y, "p50", present, selected, th.likely, ` stroke="#fff" stroke-width="2"`);
  const hits = days.map((d, i) => `<rect class="hit" data-i="${i}" data-x="${x(i)}" x="${x(i) - step / 2}" y="${mt}" width="${step}" height="${ph}" fill="transparent"/>`).join("");
  return `<svg viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" role="img" aria-label="Demand this week: likely range, most likely and usual plan for each day">${bandDefs("ffBandS", th)}` +
    `${examShade(days, x, step, mt, ph, th, H - 10)}${grid}${guide(mt, ph)}<path class="fade" d="${band}" fill="url(#ffBandS)"/>${usual}${likely}${dots}${dayLabels(days, x, H - mb + 24, selected, th)}${hits}</svg>`;
}

// Forecast desk: past week (grey) | divider | forecast band, most likely (ink), recommended (rust).
export function chartDesk(week, selected) {
  const th = THEMES.desk, days = week.days, N = 14;
  const W = 880, H = 380, ml = 62, mr = 14, mt = 34, mb = 62;
  const start = parseDay(week.start).getTime();
  const past = Array(7).fill(null);
  week.past.forEach((p) => { past[Math.round((parseDay(p.date).getTime() - (start - 7 * dayMs)) / dayMs)] = p; });
  const vals = [...days.flatMap((d) => [d.p10, d.p90, d.recommended]), ...week.past.map((p) => p.actual)].filter((v) => v > 0);
  const ticks = niceTicks(Math.min(...vals) * 0.9, Math.max(...vals) * 1.04);
  const lo = ticks[0], hi = ticks[ticks.length - 1];
  const { pw, ph, y, grid } = frame(W, H, ml, mr, mt, mb, lo, hi, ticks, th);
  const step = pw / N, x = (i) => ml + step * (i + 0.5), xf = (j) => x(7 + j);
  const split = ml + step * 7;
  const present = hasData(days);
  const band = bandPath(days, xf, y, present);
  const pastLine = line(segments(past.map((p) => (p ? p.actual : 0)), x, y).map(path).join(" "), th.past, 2.2);
  const pastDots = past.map((p, i) => (p ? `<circle class="pt" style="--i:${i}" cx="${x(i)}" cy="${y(p.actual)}" r="4" fill="${th.past}"/>` : "")).join("");
  const pastLabels = Array.from({ length: 7 }, (_, i) => new Date(start - (7 - i) * dayMs)).map((d, i) =>
    `<text x="${x(i)}" y="${H - mb + 24}" text-anchor="middle" font-size="14" fill="${th.axis}">${d.toLocaleDateString("en-US", { weekday: "short" })}</text>`).join("");
  const likely = line(seriesPath(days, xf, y, "p50", present), th.likely, 3, "ln l2") + seriesDots(days, xf, y, "p50", present, selected, th.likely);
  const rec = line(seriesPath(days, xf, y, "recommended", present), th.rec, 2.6, "ln l2") + seriesDots(days, xf, y, "recommended", present, selected, th.rec);
  const hits = days.map((d, j) => `<rect class="hit" data-i="${j}" data-x="${xf(j)}" x="${xf(j) - step / 2}" y="${mt}" width="${step}" height="${ph}" fill="transparent"/>`).join("");
  return `<svg viewBox="0 0 ${W} ${H}" width="${W}" height="${H}" role="img" aria-label="Past week demand and forecast for the next seven days">${bandDefs("ffBandD", th)}` +
    `${examShade(days, xf, step, mt, ph, th, H - 10)}${grid}<rect x="${ml}" y="${mt}" width="${split - ml}" height="${ph}" fill="#0D2A1E" fill-opacity=".025"/>` +
    `<line x1="${split}" x2="${split}" y1="${mt - 18}" y2="${mt + ph}" stroke="${th.likely}" stroke-opacity=".5" stroke-dasharray="3 4"/>` +
    `<text x="${split - 12}" y="${mt - 10}" text-anchor="end" font-size="14" font-weight="600" fill="${th.axis}">Past week</text>` +
    `<text x="${split + 12}" y="${mt - 10}" font-size="14" font-weight="600" fill="${th.likely}">Forecast</text>${guide(mt, ph)}` +
    `${pastLine}${pastDots}<path class="fade" d="${band}" fill="url(#ffBandD)"/>${likely}${rec}` +
    `${pastLabels}${dayLabels(days, xf, H - mb + 24, selected, th)}${hits}</svg>`;
}

// Click, keyboard and hover behaviour for either chart: a guide line follows the pointer across the days.
export function bindChart(container, week, onSelect, extraTip = () => "") {
  const svg = container.querySelector("svg");
  const g = svg?.querySelector(".guide");
  container.querySelectorAll(".daybtn").forEach((b) => {
    const pick = () => onSelect(b.dataset.date);
    b.addEventListener("click", pick);
    b.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); pick(); } });
  });
  container.querySelectorAll(".hit").forEach((r) => {
    const d = week.days[Number(r.dataset.i)];
    r.addEventListener("mousemove", (e) => {
      showTip(e, tipHtml(d, extraTip(d)));
      if (g) { g.setAttribute("x1", r.dataset.x); g.setAttribute("x2", r.dataset.x); g.style.opacity = "1"; }
    });
    r.addEventListener("mouseleave", () => { hideTip(); if (g) g.style.opacity = "0"; });
    r.addEventListener("click", () => onSelect(d.date));
  });
}
