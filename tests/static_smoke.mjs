// Browser smoke test for the static online demo (the GitHub Pages build). Needs Node 22+ and Chrome or Edge.
// Build the site, serve it under a sub path the way GitHub Pages does, then run this test:
//   python scripts/build_static_site.py
//   mkdir -p /tmp/pages && ln -sfn "$PWD/site" /tmp/pages/FeedForward && python -m http.server -d /tmp/pages 8090
//   node tests/static_smoke.mjs                 (BASE_URL defaults to http://localhost:8090/FeedForward/)
// Set SHOTS_DIR to also save a screenshot of each view. Drives the page through the Chrome DevTools protocol.
// It opens the page with ?remote=off, so it checks the snapshot alone and never calls the deployed server.
import { spawn } from "node:child_process";
import { writeFileSync } from "node:fs";
import { tmpdir } from "node:os";

const BROWSER = process.env.BROWSER_PATH || (process.platform === "darwin"
  ? "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
  : "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe");
const BASE = process.env.BASE_URL || "http://localhost:8090/FeedForward/";
const SHOTS = process.env.SHOTS_DIR;
const proc = spawn(BROWSER, ["--headless=new", "--disable-gpu", "--remote-debugging-port=9334", "--window-size=1360,1600",
  `--user-data-dir=${tmpdir()}/ff-static-profile-${Date.now()}`, "about:blank"], { stdio: "ignore" });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

let targets;
for (let i = 0; i < 40; i++) {
  try { targets = await (await fetch("http://127.0.0.1:9334/json")).json(); if (targets.length) break; } catch { /* browser still starting */ }
  await sleep(300);
}
const ws = new WebSocket(targets.find((t) => t.type === "page").webSocketDebuggerUrl);
await new Promise((r) => { ws.onopen = r; });
let nextId = 0;
const pending = new Map();
const jsErrors = [], failedRequests = [];
ws.onmessage = (m) => {
  const d = JSON.parse(m.data);
  if (d.id && pending.has(d.id)) pending.get(d.id)(d);
  else if (d.method === "Runtime.exceptionThrown") jsErrors.push(d.params.exceptionDetails.exception?.description || d.params.exceptionDetails.text);
  else if (d.method === "Network.responseReceived" && d.params.response.status >= 400) failedRequests.push(`${d.params.response.status} ${d.params.response.url}`);
};
const send = (method, params = {}) => new Promise((r) => { const id = ++nextId; pending.set(id, r); ws.send(JSON.stringify({ id, method, params })); });
const ev = async (expression) => (await send("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true })).result.result.value;
const waitFor = async (expr, label) => {
  for (let i = 0; i < 80; i++) { if (await ev(expr)) return; await sleep(250); }
  throw new Error(`timed out waiting for: ${label}`);
};
const shot = async (name) => {
  if (!SHOTS) return;
  await sleep(400);
  const { result } = await send("Page.captureScreenshot", { format: "png", captureBeyondViewport: false });
  writeFileSync(`${SHOTS}/${name}.png`, Buffer.from(result.data, "base64"));
};
const setVal = (sel, v) => ev(`(() => { const e = document.querySelector(${JSON.stringify(sel)}); e.value = ${JSON.stringify(String(v))}; e.dispatchEvent(new Event('input', { bubbles: true })); e.dispatchEvent(new Event('change', { bubbles: true })); })()`);
const text = (sel) => ev(`document.querySelector(${JSON.stringify(sel)})?.textContent ?? ""`);
const results = [];
const check = (name, ok, detail = "") => results.push(`${ok ? "PASS" : "FAIL"}  ${name}  ${detail}`);

await send("Runtime.enable");
await send("Network.enable");
await send("Page.enable");
// ?remote=off: test the snapshot on its own, without the deployed server the page can also call
await send("Page.navigate", { url: `${BASE}${BASE.includes("?") ? "&" : "?"}remote=off` });
await waitFor("document.querySelector('.ld-snap-tile') && !document.querySelector('.ld-snap-tile').textContent.includes('Loading')", "home numbers");
check("Home loads with the live preview", !(await text(".ld-snap-tile")).includes("Loading"), (await text(".ld-preview .ld-pv-title")).slice(0, 60));
await shot("home");

await ev("location.hash = 'service'");
await waitFor("document.querySelectorAll('#sv-tickets .ticket').length > 0", "tickets");
const h0 = await text("#sv-headline");
check("Service board headline", /^Cook [\d,]+ portions for lunch/.test(h0), h0);
await shot("service");

await ev("document.querySelector('[data-slot=dinner]').click()");
await waitFor("document.querySelector('#sv-headline').textContent.includes('dinner')", "dinner headline");
check("Meal slot switch", true, await text("#sv-headline"));

await ev("document.querySelectorAll('#sv-chart .daybtn')[2].dispatchEvent(new MouseEvent('click', { bubbles: true }))");
await waitFor("document.querySelector('#sv-sub').textContent.includes('Friday')", "day change");
check("Clicking a chart day changes the day", true, await text("#sv-sub"));

await setVal("#sv-whatif select[id$=special]", "exam_week");
await waitFor("document.querySelector('#sv-whatif .whatif-foot button')", "what if result");
check("What if (exam week) shows a summary", (await text("#sv-whatif .whatif-foot")).includes("Cooking would change"), (await text("#sv-whatif .whatif-foot")).slice(0, 70));
await setVal("#sv-whatif select[id$=weather]", "Heavy Rain");
await waitFor("document.querySelector('#sv-whatif select[id$=special]').value === ''", "other setting reset");
check("Demo what if keeps one setting at a time", !(await text("#sv-headline")).includes("could not be loaded"), await text("#sv-whatif .whatif-foot"));
await ev("document.querySelector('#sv-whatif .whatif-foot button').click()");
await waitFor("document.querySelector('#sv-whatif .whatif-foot').hidden", "what if reset");
check("What if reset", true);

await ev("[...document.querySelectorAll('#view-service .chip-btn')].find((b) => b.textContent === 'Explain the range').click()");
await waitFor("document.querySelector('#sv-log .bubble.bot:last-child')?.textContent.includes('Short answer')", "chip answer");
check("Copilot answers a suggested question", true, (await ev("document.querySelector('#sv-log .bubble.bot:last-child').textContent")).slice(0, 70));
await ev("document.querySelector('#sv-q').value = 'Why is this so high?'; document.querySelector('#sv-form').dispatchEvent(new Event('submit', { cancelable: true, bubbles: true }))");
await waitFor("document.querySelector('#sv-log .bubble:last-child')?.textContent.includes('suggested questions')", "demo note");
check("A free question explains the demo limit", true);

await ev("document.querySelector('#sv-approve').click()");
await waitFor("document.querySelector('#view-service').textContent.includes('saved in this browser')", "approve");
check("Approve is saved in the browser", true, await text("#sv-status"));

await ev("document.querySelector('#sv-showall').click()");
await waitFor("document.querySelector('#sv-showall').textContent.includes('main dishes only')", "show all dishes");
check("Show all dishes", true, `${await ev("document.querySelectorAll('#sv-tickets .ticket').length")} tickets`);

await ev("location.hash = 'desk'");
await waitFor("document.querySelector('#dk-table tbody tr') && document.querySelector('#dk-chart svg')", "desk table and chart");
check("Forecast desk table and chart", true, await text("#dk-title"));
await ev("document.querySelectorAll('#dk-pick button')[1].click()");
await waitFor("document.querySelector('#dk-pick button[aria-pressed=true]')?.dataset.dish && document.querySelector('#dk-chart svg')", "dish week");
check("Dish week chart", await ev("!document.querySelector('#dk-error .banner')"), await text("#dk-pick button[aria-pressed=true]"));
const other = await ev("document.querySelector('#dk-more option:nth-child(2)')?.value ?? ''");
if (other) {
  await setVal("#dk-more", other);
  await waitFor(`document.querySelector('#dk-more')?.value === ${JSON.stringify(other)} && document.querySelector('#dk-chart svg')`, "more dishes week");
  check("A dish from More dishes has a week chart", await ev("!document.querySelector('#dk-error .banner')"), other);
}
await shot("desk");

await ev("location.hash = 'calendar'");
await waitFor("document.querySelectorAll('#cal-grid [data-date]').length > 20", "calendar month");
check("Calendar month", true, `${await text("#cal-month-label")}: ${(await text("#cal-live")).trim().slice(0, 50)}`);
await shot("calendar");
const month0 = await text("#cal-month-label");
await ev("document.querySelector('#cal-next').click()");
await waitFor(`document.querySelector('#cal-month-label').textContent !== ${JSON.stringify(month0)} && document.querySelectorAll('#cal-grid [data-date]').length > 20`, "next month");
await ev("document.querySelector('#cal-grid [data-date$=\"-20\"]').click()");
await waitFor("location.hash === '#service' && document.querySelector('#sv-sub').textContent.includes('Friday')", "calendar to service");
await sleep(500);
check("Clicking a calendar day opens it on the Service board", await ev("document.querySelectorAll('#sv-tickets .ticket').length > 0 || document.querySelector('#sv-tickets .empty')"), await text("#sv-sub"));
await setVal("#sv-whatif select[id$=special]", "festival");
await waitFor("document.querySelector('#sv-tickets').textContent.includes('prebuilt')", "out of window message");
check("What if outside the 7 days explains why", true, (await text("#sv-tickets")).slice(0, 80));
await setVal("#sv-whatif select[id$=special]", "");
await waitFor("document.querySelectorAll('#sv-tickets .ticket').length > 0", "back to the normal plan");
check("Setting it back to normal restores the plan", true);

await ev("location.hash = 'admin'");
await waitFor("document.querySelector('#ad-gate-t')", "daily log");
check("Daily log says it needs the server", (await text("#ad-gate-t")).includes("server") && await ev("document.querySelector('#ad-pin-form').hidden"));
await shot("admin");

await send("Emulation.setDeviceMetricsOverride", { width: 390, height: 900, deviceScaleFactor: 1, mobile: false });
for (const view of ["landing", "service", "desk", "calendar"]) {
  await ev(`location.hash = '${view}'`);
  await sleep(700);
  const wide = await ev("[...document.querySelectorAll('#view-" + view + " *')].filter((e) => e.offsetParent && e.getBoundingClientRect().right > 391 && !e.closest('.tablewrap, .ad-tablewrap, svg, [aria-hidden=true]')).slice(0, 6).map((e) => (e.id || e.className.baseVal || e.className || e.tagName) + ':' + Math.round(e.getBoundingClientRect().right)).join(' | ')");
  check(`phone width: nothing wider than the screen (${view})`, wide === "" && await ev("document.documentElement.scrollWidth <= 391"), wide);
}
await ev("location.hash = 'service'");
await shot("service-phone");

console.log(results.join("\n"));
console.log("JavaScript errors:", jsErrors.length ? jsErrors.join("\n") : "none");
console.log("Failed requests:", failedRequests.length ? failedRequests.join("\n") : "none");
ws.close();
proc.kill();
process.exit(results.some((r) => r.startsWith("FAIL")) || jsErrors.length ? 1 : 0);
