// Hand written SVG charts. No chart library.
import { dayMs, esc, fmt, hideTip, niceTicks, parseDay, runs, shortDate, showTip } from "./util.js";

const path = (pts) => pts.map(([x, y], i) => `${i ? "L" : "M"}${x.toFixed(1)},${y.toFixed(1)}`).join("");
const segments = (vals, fx, fy) => {      // polyline pieces that skip missing values (0 or null)
  const out = [];
  let cur = [];
  vals.forEach((v, i) => { if (v > 0) cur.push([fx(i), fy(v)]); else if (cur.length) { out.push(cur); cur = []; } });
  if (cur.length) out.push(cur);
  return out;
};

// theme: colours for the view the chart sits in
export const THEMES = {
  service: { grid: "#E3E8E2", axis: "#55665B", band: "#9CC4AE", bandOpacity: 0.75, likely: "#15291F", usual: "#C4452D", exam: "#F8F0DD", examText: "#7A5A12", sel: "#2F6B4F" },
  desk: { grid: "#E6EAF3", axis: "#5B6478", band: "#BFD0F0", bandOpacity: 0.95, likely: "#17233B", rec: "#E5702A", past: "#5F6B88", exam: "#FBF0C8", examText: "#7A5A12", sel: "#2C55B8" },
};

function frame(W, H, ml, mr, mt, mb, lo, hi, ticks, th) {
  const pw = W - ml - mr, ph = H - mt - mb;
  const y = (v) => mt + ph * (1 - (v - lo) / (hi - lo));
  const grid = ticks.map((t) => `<line x1="${ml}" x2="${W - mr}" y1="${y(t)}" y2="${y(t)}" stroke="${th.grid}"/>` +
    `<text x="${ml - 10}" y="${y(t) + 4}" text-anchor="end" font-size="13" fill="${th.axis}">${fmt(t)}</text>`).join("");
  return { pw, ph, y, grid };
}

function dayLabels(items, x, yPos, selected, th) {
  return items.map((d, i) => `<g class="daybtn" role="button" tabindex="0" data-date="${d.date}" aria-label="Show ${esc(shortDate(d.date))}" style="cursor:pointer">` +
    `<text x="${x(i)}" y="${yPos}" text-anchor="middle" font-size="14" fill="${d.date === selected ? th.sel : th.axis}" font-weight="${d.date === selected ? 700 : 400}">${esc(d.weekday)}</text></g>`).join("");
}

function examShade(days, x, step, mt, ph, th, labelY, offset = 0) {
  return runs(days.map((d) => d.exam_week)).map(([a, b]) =>
    `<rect x="${x(a + offset) - step / 2}" y="${mt}" width="${(b - a + 1) * step}" height="${ph}" fill="${th.exam}"/>` +
    `<text x="${(x(a + offset) + x(b + offset)) / 2}" y="${labelY}" text-anchor="middle" font-size="13" fill="${th.examText}">Exam week</text>`).join("");
}

function tipHtml(d, extra = "") {
  return `<strong>${esc(shortDate(d.date))}</strong><br>Most likely ${fmt(d.p50)}<br>Likely range ${fmt(d.p10)} to ${fmt(d.p90)}<br>Usual plan ${d.usual_plan ? fmt(d.usual_plan) : "none"}${extra}`;
}

// View A: likely range band, most likely line, dashed usual plan, exam week shading.
export function chartService(week, selected) {
  const th = THEMES.service, days = week.days, n = days.length;
  const W = 880, H = 330, ml = 62, mr = 14, mt = 12, mb = 62;
  const vals = days.flatMap((d) => [d.p10, d.p90, d.usual_plan]).filter((v) => v > 0);
  const ticks = niceTicks(Math.min(...vals) * 0.92, Math.max(...vals) * 1.04);
  const lo = ticks[0], hi = ticks[ticks.length - 1];
  const { pw, ph, y, grid } = frame(W, H, ml, mr, mt, mb, lo, hi, ticks, th);
  const step = pw / n, x = (i) => ml + step * (i + 0.5);
  const band = `M${days.map((d, i) => `${x(i)},${y(d.p90)}`).join("L")}L${[...days].reverse().map((d, i) => `${x(n - 1 - i)},${y(d.p10)}`).join("L")}Z`;
  const usual = segments(days.map((d) => d.usual_plan), x, y).map((s) => `<path d="${path(s)}" fill="none" stroke="${th.usual}" stroke-width="2.2" stroke-dasharray="7 6"/>`).join("");
  const line = `<path d="${path(days.map((d, i) => [x(i), y(d.p50)]))}" fill="none" stroke="${th.likely}" stroke-width="2.6"/>`;
  const dots = days.map((d, i) => `<circle cx="${x(i)}" cy="${y(d.p50)}" r="${d.date === selected ? 6 : 4.5}" fill="${th.likely}" stroke="#fff" stroke-width="2"/>`).join("");
  const hits = days.map((d, i) => `<rect class="hit" data-i="${i}" x="${x(i) - step / 2}" y="${mt}" width="${step}" height="${ph}" fill="transparent"/>`).join("");
  return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Demand this week: likely range, most likely and usual plan for each day">` +
    `${examShade(days, x, step, mt, ph, th, H - 10)}${grid}<path d="${band}" fill="${th.band}" fill-opacity="${th.bandOpacity}"/>${usual}${line}${dots}${dayLabels(days, x, H - mb + 24, selected, th)}${hits}</svg>`;
}

// View B: past week (grey) | divider | forecast band, most likely (navy), recommended (orange).
export function chartDesk(week, selected) {
  const th = THEMES.desk, days = week.days, n = days.length, N = 14;
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
  const band = `M${days.map((d, j) => `${xf(j)},${y(d.p90)}`).join("L")}L${[...days].reverse().map((d, j) => `${xf(n - 1 - j)},${y(d.p10)}`).join("L")}Z`;
  const pastLine = segments(past.map((p) => (p ? p.actual : 0)), x, y).map((s) => `<path d="${path(s)}" fill="none" stroke="${th.past}" stroke-width="2.2"/>`).join("");
  const pastDots = past.map((p, i) => (p ? `<circle cx="${x(i)}" cy="${y(p.actual)}" r="4" fill="${th.past}"/>` : "")).join("");
  const pastLabels = Array.from({ length: 7 }, (_, i) => new Date(start - (7 - i) * dayMs)).map((d, i) =>
    `<text x="${x(i)}" y="${H - mb + 24}" text-anchor="middle" font-size="14" fill="${th.axis}">${d.toLocaleDateString("en-US", { weekday: "short" })}</text>`).join("");
  const likely = `<path d="${path(days.map((d, j) => [xf(j), y(d.p50)]))}" fill="none" stroke="${th.likely}" stroke-width="3"/>` +
    days.map((d, j) => `<circle cx="${xf(j)}" cy="${y(d.p50)}" r="${d.date === selected ? 6 : 4.5}" fill="${th.likely}"/>`).join("");
  const rec = `<path d="${path(days.map((d, j) => [xf(j), y(d.recommended)]))}" fill="none" stroke="${th.rec}" stroke-width="2.6"/>` +
    days.map((d, j) => `<circle cx="${xf(j)}" cy="${y(d.recommended)}" r="${d.date === selected ? 6 : 4.5}" fill="${th.rec}"/>`).join("");
  const hits = days.map((d, j) => `<rect class="hit" data-i="${j}" x="${xf(j) - step / 2}" y="${mt}" width="${step}" height="${ph}" fill="transparent"/>`).join("");
  return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Past week demand and forecast for the next seven days">` +
    `${examShade(days, xf, step, mt, ph, th, H - 10)}${grid}<line x1="${split}" x2="${split}" y1="${mt - 18}" y2="${mt + ph}" stroke="#17233B" stroke-dasharray="3 4"/>` +
    `<text x="${split - 12}" y="${mt - 10}" text-anchor="end" font-size="14" font-weight="600" fill="#17233B">Past week</text>` +
    `<text x="${split + 12}" y="${mt - 10}" font-size="14" font-weight="600" fill="#17233B">Forecast</text>` +
    `${pastLine}${pastDots}<path d="${band}" fill="${th.band}" fill-opacity="${th.bandOpacity}"/>${likely}${rec}` +
    `${pastLabels}${dayLabels(days, xf, H - mb + 24, selected, th)}${hits}</svg>`;
}

// Click and hover behaviour for either chart.
export function bindChart(container, week, onSelect, extraTip = () => "") {
  container.querySelectorAll(".daybtn").forEach((g) => {
    const pick = () => onSelect(g.dataset.date);
    g.addEventListener("click", pick);
    g.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); pick(); } });
  });
  container.querySelectorAll(".hit").forEach((r) => {
    const d = week.days[Number(r.dataset.i)];
    r.addEventListener("mousemove", (e) => showTip(e, tipHtml(d, extraTip(d))));
    r.addEventListener("mouseleave", hideTip);
    r.addEventListener("click", () => onSelect(d.date));
  });
}
