// Browser smoke test for the dashboard. Needs Node 22+ and Microsoft Edge, and the API running on port 8765:
//   uvicorn api.main:app --port 8765     then     node tests/ui_smoke.mjs
// It drives the real page through the Chrome DevTools protocol (no extra packages).
import { spawn } from "node:child_process";
import { tmpdir } from "node:os";

const EDGE = process.env.EDGE_PATH || "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";
const BASE = process.env.BASE_URL || "http://localhost:8765";
const proc = spawn(EDGE, ["--headless=new", "--disable-gpu", "--remote-debugging-port=9333", "--window-size=1360,1600",
  `--user-data-dir=${tmpdir()}/ff-edge-profile`, "about:blank"], { stdio: "ignore" });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

let targets;
for (let i = 0; i < 40; i++) {
  try { targets = await (await fetch("http://127.0.0.1:9333/json")).json(); if (targets.length) break; } catch { /* browser still starting */ }
  await sleep(300);
}
const ws = new WebSocket(targets.find((t) => t.type === "page").webSocketDebuggerUrl);
await new Promise((r) => { ws.onopen = r; });
let nextId = 0;
const pending = new Map();
const jsErrors = [];
ws.onmessage = (m) => {
  const d = JSON.parse(m.data);
  if (d.id && pending.has(d.id)) pending.get(d.id)(d);
  else if (d.method === "Runtime.exceptionThrown") jsErrors.push(d.params.exceptionDetails.exception?.description || d.params.exceptionDetails.text);
};
const send = (method, params = {}) => new Promise((r) => { const id = ++nextId; pending.set(id, r); ws.send(JSON.stringify({ id, method, params })); });
const ev = async (expression) => (await send("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true })).result.result.value;
const waitFor = async (expr, label) => {
  for (let i = 0; i < 80; i++) { if (await ev(expr)) return; await sleep(250); }
  throw new Error(`timed out waiting for: ${label}`);
};
const results = [];
const check = (name, ok, detail = "") => results.push(`${ok ? "PASS" : "FAIL"}  ${name}  ${detail}`);

await send("Runtime.enable");
await send("Page.navigate", { url: `${BASE}/#service` });
await waitFor("document.querySelectorAll('#sv-tickets .ticket').length > 0", "tickets");
const headline = () => ev("document.querySelector('#sv-headline').textContent");
const h0 = await headline();
check("A headline loads", /^Cook [\d,]+ portions for lunch/.test(h0), h0);

await ev("document.querySelector('[data-slot=dinner]').click()");
await waitFor("document.querySelector('#sv-headline').textContent.includes('dinner')", "dinner headline");
check("A meal slot switch", true, await headline());

await ev("document.querySelectorAll('#sv-chart .daybtn')[2].dispatchEvent(new MouseEvent('click', { bubbles: true }))");
await waitFor("document.querySelector('#sv-sub').textContent.includes('Friday')", "day change");
check("A clicking a chart day changes the forecast day", true, await ev("document.querySelector('#sv-sub').textContent"));

await ev("const r = document.querySelector('#sv-whatif input[type=range]'); r.value = 15; r.dispatchEvent(new Event('input', { bubbles: true })); r.dispatchEvent(new Event('change', { bubbles: true }))");
await waitFor("document.querySelector('#sv-note').textContent.includes('what if') && document.querySelector('#sv-whatif .whatif-foot button')", "what if result");
const summary = await ev("document.querySelector('#sv-whatif .whatif-foot').textContent");
check("A what if shows the note and a summary", summary.includes("Cooking would change"), summary.slice(0, 80));
await ev("document.querySelector('#sv-whatif .whatif-foot button').click()");
await waitFor("!document.querySelector('#sv-note').textContent.includes('what if')", "what if reset");
check("A what if reset", true);

await waitFor("!document.querySelector('#view-service').classList.contains('is-loading')", "plan reloaded after the reset");
await ev("document.querySelector('#sv-change').click()");
await waitFor("document.querySelector('#sv-tickets input')", "edit inputs");
await ev("const i = document.querySelector('#sv-tickets input'); i.focus(); i.value = '2000'; i.dispatchEvent(new Event('input', { bubbles: true }))");
check("A typing a quantity keeps focus", await ev("document.activeElement.tagName === 'INPUT'"));
check("A edited total is explained", (await ev("document.querySelector('#sv-support').textContent")).includes("With your changes"));

await ev("document.querySelector('#sv-approve').click()");
await waitFor("document.querySelector('#sv-status').textContent.length > 0", "approve status");
check("A approve gives a confirmation", true, await ev("document.querySelector('#sv-status').textContent"));


await ev("document.querySelector('#sv-showall').click()");
await waitFor("document.querySelectorAll('#sv-tickets .ticket').length > 4", "show all dishes");
check("A show all dishes", true, `${await ev("document.querySelectorAll('#sv-tickets .ticket').length")} tickets`);

await ev("location.hash = 'forecast'");
await waitFor("document.querySelectorAll('#fc-days button.fc-day').length === 7 && document.querySelector('#fc-table tbody tr')", "forecast days");
check("B forecast shows seven day cards and a title", (await ev("document.querySelector('#fc-title').textContent")).includes("next 7 days"));
await ev("document.querySelectorAll('#fc-days button.fc-day')[2].click()");
await waitFor("document.querySelectorAll('#fc-days button.fc-day')[2].classList.contains('on')", "day pick");
check("B picking a day changes the detail", true, await ev("document.querySelector('#fc-detail-t').textContent"));
await ev("document.querySelectorAll('#fc-pick button')[1].click()");
await waitFor("document.querySelector('#fc-pick button[aria-pressed=true]').dataset.dish", "dish selection");
check("B dish selector", true, await ev("document.querySelector('#fc-pick button[aria-pressed=true]').textContent"));
check("B every dish on every day", await ev("document.querySelectorAll('#fc-matrix tbody tr').length > 3"));

await ev("location.hash = 'plans'");
await waitFor("document.querySelectorAll('#pl-board [data-act=approve]').length > 0", "plans board");
await ev("document.querySelector('#pl-board [data-act=approve]').click()");
await waitFor("document.querySelectorAll('#pl-board .st-approve').length > 0", "plan approved");
check("P approving on Plans shows on the board", true, await ev("document.querySelector('#pl-stats').textContent.replace(/\\s+/g, ' ')"));

await ev("location.hash = 'events'");
await waitFor("document.querySelector('#ev-head h2') && document.querySelectorAll('#ev-dishes tbody tr').length > 0", "rare event plan");
check("E a rare event plan loads", true, await ev("document.querySelector('#ev-head h2').textContent"));

await ev("location.hash = 'copilot'");
await ev("document.querySelector('#co-q').value = 'Why is this high?'; document.querySelector('#co-form').dispatchEvent(new Event('submit', { cancelable: true, bubbles: true }))");
await waitFor("document.querySelector('#co-log').lastElementChild.textContent.includes('One caution') || document.querySelector('#co-log .bubble.err')", "chat reply");
const reply = await ev("document.querySelector('#co-log').lastElementChild.textContent");
check("A copilot answers in the three part format", reply.includes("Short answer:") && reply.includes("One caution:"), reply.slice(0, 90));


// ---- Daily log (needs the server started with ADMIN_PIN=1234 and FEEDFORWARD_ADMIN_LOG_DIR pointing at a temp folder)
const setVal = (sel, v) => ev(`(() => { const e = document.querySelector(${JSON.stringify(sel)}); e.value = ${JSON.stringify(String(v))}; e.dispatchEvent(new Event('input', { bubbles: true })); e.dispatchEvent(new Event('change', { bubbles: true })); })()`);
await ev("location.hash = 'admin'");
await waitFor("document.querySelector('#ad-pin')", "pin field");
await setVal("#ad-pin", "0000");
await ev("document.querySelector('#ad-pin-form').dispatchEvent(new Event('submit', { cancelable: true, bubbles: true }))");
await waitFor("document.querySelector('#ad-gate-msg').textContent.includes('PIN')", "wrong pin message");
check("C wrong PIN is refused with a clear message", await ev("document.querySelector('#ad-app').hidden"), await ev("document.querySelector('#ad-gate-msg').textContent.slice(0, 80)"));
await setVal("#ad-pin", "1234");
await ev("document.querySelector('#ad-pin-form').dispatchEvent(new Event('submit', { cancelable: true, bubbles: true }))");
await waitFor("!document.querySelector('#ad-app').hidden && document.querySelector('#ad-rows input')", "unlock");
check("C right PIN unlocks the form", true, `date ${await ev("document.querySelector('#ad-date').value")} weekday ${await ev("document.querySelector('#ad-wd').value")}`);
await setVal("#ad-wd", "Monday");
await waitFor("document.querySelector('#ad-date').value === '2026-10-05'", "weekday sync");
check("C weekday selector moves the date", true, await ev("document.querySelector('#ad-date').value"));
await setVal("#ad-date", "2026-10-06");
await waitFor("document.querySelector('#ad-wd').value === 'Tuesday'", "date sync");
check("C date change updates the weekday", true);
await setVal("#ad-tmax", 33); await setVal("#ad-tmin", 26); await setVal("#ad-weather", "Light Rain");
await setVal("#ad-att-lunch", 3300);
const rows = "document.querySelectorAll('#ad-rows tr')";
await ev(`(() => { const r = ${rows}; const set = (tr, k, v) => { const i = tr.querySelector('[data-k=' + k + ']'); i.value = v; i.dispatchEvent(new Event('input', { bubbles: true })); }; set(r[0], 'prepared', 3500); set(r[0], 'eaten', 3100); set(r[1], 'prepared', 3300); set(r[1], 'left', 200); })()`);
await ev("document.querySelector('#ad-fill').click()");
await waitFor("document.querySelectorAll('#ad-ing tr input[data-k=used_kg]').length > 0", "fill from recipes");
check("C fill from recipes adds ingredient rows", true, `${await ev("document.querySelectorAll('#ad-ing tr input[data-k=used_kg]').length")} ingredients`);
await ev("document.querySelector('#ad-check').click()");
await waitFor("document.querySelector('#ad-msg').textContent.length > 0", "check message");
check("C check entry gives feedback", true, await ev("document.querySelector('#ad-msg').textContent.slice(0, 100)"));
await ev("document.querySelector('#ad-save').click()");
await waitFor("document.querySelector('#ad-msg').textContent.includes('Saved')", "save");
check("C save confirms what was saved", true, await ev("document.querySelector('#ad-msg').textContent.slice(0, 120)"));
await waitFor("document.querySelectorAll('#ad-recent tr [data-edit]').length > 0", "recent entries");
check("C recent entries list the saved day", true);
await ev(`(() => { const i = ${rows}[0].querySelector('[data-k=prepared]'); i.value = 40000; i.dispatchEvent(new Event('input', { bubbles: true })); const e = ${rows}[0].querySelector('[data-k=eaten]'); e.value = 39000; e.dispatchEvent(new Event('input', { bubbles: true })); })()`);
await ev("document.querySelector('#ad-check').click()");
await waitFor("document.querySelector('#ad-msg').textContent.includes('far outside')", "typo warning");
check("C a likely typo raises a warning", true);
await setVal("#ad-date", "2026-10-20");
await waitFor("!document.querySelector('#ad-future').hidden", "future note");
check("C a future date shows only the day context", await ev("document.querySelector('#ad-past').hidden"));
await ev("document.querySelector('[data-export=attendance]').click()");
const bad = await ev("document.querySelector('#ad-s6') && [...document.querySelectorAll('#view-admin button, #view-admin select, #view-admin input:not([type=checkbox])')].filter((e) => e.offsetParent && e.getBoundingClientRect().height < 43.5).map((e) => (e.id || e.textContent.slice(0, 14)) + ':' + Math.round(e.getBoundingClientRect().height)).join(' | ')");
check("C every visible control is at least 44px tall", bad === "", bad);

await ev("location.hash = 'forecast'");
const small = await ev("[...document.querySelectorAll('#view-forecast button, #view-forecast select, #view-forecast input:not([type=range])')].filter((e) => e.offsetParent && e.getBoundingClientRect().height < 43.5).map((e) => (e.id || e.textContent.slice(0, 14)) + ':' + Math.round(e.getBoundingClientRect().height)).join(' | ')");
check("B every visible control is at least 44px tall", small === "", small);

// ---- Home and Calendar
await ev("location.hash = 'landing'");
await waitFor("document.querySelector('#ld-preview') && document.querySelector('#ld-preview').textContent.trim().length > 20", "home preview");
check("H home shows the live preview", /\d/.test(await ev("document.querySelector('#ld-preview').textContent")), await ev("document.querySelector('#ld-preview').textContent.trim().slice(0, 60)"));
check("H home has its sections and a selected Home tab", await ev("document.querySelectorAll('#view-landing .ld-section').length >= 3 && document.querySelector('#tab-landing').getAttribute('aria-selected') === 'true'"));
await ev("location.hash = 'calendar'");
await waitFor("document.querySelectorAll('#cal-grid [data-date]').length >= 28", "calendar grid");
const month = await ev("document.querySelector('#cal-month-label').textContent");
check("K calendar shows a month grid and its label", month.length > 3, `${month}, ${await ev("document.querySelectorAll('#cal-grid [data-date]').length")} days`);
await ev("document.querySelector('#cal-next').click()");
await waitFor(`document.querySelector('#cal-month-label').textContent !== ${JSON.stringify(month)}`, "next month");
check("K calendar next month changes the label", true, await ev("document.querySelector('#cal-month-label').textContent"));
await ev("document.querySelector('#cal-today').click()");
await waitFor(`document.querySelector('#cal-month-label').textContent === ${JSON.stringify(month)}`, "back to today");
check("K calendar Jump to today returns", true);
check("K calendar has the Coming up list", await ev("!!document.querySelector('#cal-upcoming-list') && !!document.querySelector('#cal-live')"));

// mobile: false keeps the viewport at 390 px, so content that is too wide shows up as overflow
await send("Emulation.setDeviceMetricsOverride", { width: 390, height: 900, deviceScaleFactor: 1, mobile: false });
for (const view of ["landing", "service", "forecast", "plans", "events", "copilot", "calendar", "admin"]) {
  await ev(`location.hash = '${view}'`);
  await sleep(700);
  const wide = await ev("[...document.querySelectorAll('#view-" + view + " *')].filter((e) => e.offsetParent && e.getBoundingClientRect().right > 391 && !e.closest('.tablewrap, .ad-tablewrap, svg, .ld-mq-track, .ld-final-orb, .fc-days')).slice(0, 6).map((e) => (e.id || e.className.baseVal || e.className || e.tagName) + ':' + Math.round(e.getBoundingClientRect().right)).join(' | ')");
  check(`phone width: nothing wider than the screen (${view})`, wide === "" && await ev("document.documentElement.scrollWidth <= 391"), wide);
}
console.log(results.join("\n"));
console.log("JavaScript errors:", jsErrors.length ? jsErrors.join("\n") : "none");
ws.close();
proc.kill();
process.exit(results.some((r) => r.startsWith("FAIL")) || jsErrors.length ? 1 : 0);
