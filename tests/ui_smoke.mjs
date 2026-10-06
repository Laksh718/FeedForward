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

await ev("document.querySelector('#sv-change').click()");
await waitFor("document.querySelector('#sv-tickets input')", "edit inputs");
await ev("const i = document.querySelector('#sv-tickets input'); i.focus(); i.value = '2000'; i.dispatchEvent(new Event('input', { bubbles: true }))");
check("A typing a quantity keeps focus", await ev("document.activeElement.tagName === 'INPUT'"));
check("A edited total is explained", (await ev("document.querySelector('#sv-support').textContent")).includes("With your changes"));

await ev("document.querySelector('#sv-approve').click()");
await waitFor("document.querySelector('#sv-status').textContent.length > 0", "approve status");
check("A approve gives a confirmation", true, await ev("document.querySelector('#sv-status').textContent"));

await ev("document.querySelector('#sv-q').value = 'Why is this high?'; document.querySelector('#sv-form').dispatchEvent(new Event('submit', { cancelable: true, bubbles: true }))");
await waitFor("document.querySelector('#sv-log').lastElementChild.textContent.includes('One caution') || document.querySelector('#sv-log .bubble.err')", "chat reply");
const reply = await ev("document.querySelector('#sv-log').lastElementChild.textContent");
check("A copilot answers in the three part format", reply.includes("Short answer:") && reply.includes("One caution:"), reply.slice(0, 90));

await ev("document.querySelector('#sv-showall').click()");
await waitFor("document.querySelectorAll('#sv-tickets .ticket').length > 4", "show all dishes");
check("A show all dishes", true, `${await ev("document.querySelectorAll('#sv-tickets .ticket').length")} tickets`);

await ev("location.hash = 'desk'");
await waitFor("document.querySelector('#dk-table tbody tr')", "desk table");
check("B title", (await ev("document.querySelector('#dk-title').textContent")).includes("forecast, next 7 days"));
check("B status chip", true, await ev("document.querySelector('#dk-status').textContent"));
await ev("document.querySelectorAll('#dk-pick button')[1].click()");
await waitFor("document.querySelector('#dk-pick button[aria-pressed=true]').dataset.dish", "dish selection");
check("B dish selector", true, await ev("document.querySelector('#dk-pick button[aria-pressed=true]').textContent"));
for (const nav of ["whatif", "risk", "approvals", "copilot", "forecast"]) {
  await ev(`document.querySelector('[data-nav=${nav}]').click()`);
  check(`B nav ${nav}`, await ev(`document.querySelector('[data-nav=${nav}]').getAttribute('aria-current') === 'page'`));
}
await ev("document.querySelector('#dk-q').value = 'Why is Tuesday so high?'; document.querySelector('#dk-form').dispatchEvent(new Event('submit', { cancelable: true, bubbles: true }))");
await waitFor("document.querySelector('#dk-answer').textContent.includes('One caution') || document.querySelector('#dk-answer.err')", "desk answer");
const deskReply = await ev("document.querySelector('#dk-answer').textContent");
check("B copilot answer area shows an answer", deskReply.includes("Short answer:"), deskReply.slice(0, 90));

const small = await ev("[...document.querySelectorAll('#view-desk button, #view-desk select, #view-desk input:not([type=range])')].filter((e) => e.offsetParent && e.getBoundingClientRect().height < 43.5).map((e) => (e.id || e.textContent.slice(0, 14)) + ':' + Math.round(e.getBoundingClientRect().height)).join(' | ')");
check("B every visible control is at least 44px tall", small === "", small);

// mobile: false keeps the viewport at 390 px, so content that is too wide shows up as overflow
await send("Emulation.setDeviceMetricsOverride", { width: 390, height: 900, deviceScaleFactor: 1, mobile: false });
for (const view of ["service", "desk"]) {
  await ev(`location.hash = '${view}'`);
  await sleep(700);
  const wide = await ev("[...document.querySelectorAll('#view-" + view + " *')].filter((e) => e.offsetParent && e.getBoundingClientRect().right > 391 && !e.closest('.tablewrap, svg')).slice(0, 6).map((e) => (e.id || e.className.baseVal || e.className || e.tagName) + ':' + Math.round(e.getBoundingClientRect().right)).join(' | ')");
  check(`phone width: nothing wider than the screen (${view})`, wide === "" && await ev("document.documentElement.scrollWidth <= 391"), wide);
}
console.log(results.join("\n"));
console.log("JavaScript errors:", jsErrors.length ? jsErrors.join("\n") : "none");
ws.close();
proc.kill();
process.exit(results.some((r) => r.startsWith("FAIL")) || jsErrors.length ? 1 : 0);
