// Entry point: the shell (logo, view tabs, demo notice, toasts), the view switch, mounting and first load.
import { mountAdmin } from "./admin.js";
import { STATIC } from "./api.js";
import { mountCalendar } from "./calendar.js";
import { mountDesk } from "./desk.js";
import { initGlow, liquid, toast } from "./fx.js";
import { icon } from "./icons.js";
import { mountLanding } from "./landing.js";
import { logoMark } from "./logo.js";
import { mountService } from "./service.js";
import { init, subscribe } from "./state.js";

const VIEWS = ["landing", "service", "desk", "calendar", "admin"];
const TITLES = { desk: "FeedForward, forecast desk", admin: "FeedForward, daily log", calendar: "FeedForward, calendar",
  service: "FeedForward, service board", landing: "FeedForward, predict. prevent. provide." };
const DEMO_HIDDEN = "feedforward-demo-notice-hidden";

// ---------- shell: logo, tab icons, the liquid pill under the tabs
document.querySelectorAll("[data-logo]").forEach((el) => { el.innerHTML = logoMark({ size: 34 }); });
document.querySelectorAll("[data-icon]").forEach((el) => el.insertAdjacentHTML("afterbegin", icon(el.dataset.icon)));
const tablist = document.querySelector(".viewbar-tabs");
const tabs = [...tablist.querySelectorAll("[role=tab]")];
liquid(tablist);

let current = null;
function showView(name) {
  const view = VIEWS.includes(name) ? name : "landing";
  const changed = view !== current;
  current = view;
  document.body.dataset.view = view;
  document.querySelectorAll("[data-view-panel]").forEach((p) => {
    const on = p.dataset.viewPanel === view;
    p.hidden = !on;
    if (on && changed) { p.classList.remove("view-in"); void p.offsetWidth; p.classList.add("view-in"); }
  });
  tabs.forEach((b) => {
    const on = b.dataset.viewTab === view;
    b.setAttribute("aria-selected", String(on));
    b.tabIndex = on ? 0 : -1;
  });
  document.title = TITLES[view];
  if (changed) window.scrollTo({ top: 0, behavior: "instant" });
}

tabs.forEach((b) => b.addEventListener("click", () => { location.hash = b.dataset.viewTab; }));
// Arrow keys move between tabs (the usual tab list keyboard pattern); Home and End jump to the ends.
tablist.addEventListener("keydown", (e) => {
  const i = tabs.indexOf(document.activeElement);
  if (i < 0) return;
  const j = { ArrowRight: i + 1, ArrowLeft: i - 1, Home: 0, End: tabs.length - 1 }[e.key];
  if (j === undefined) return;
  e.preventDefault();
  const next = tabs[(j + tabs.length) % tabs.length];
  next.focus();
  location.hash = next.dataset.viewTab;
});

// The top bar firms up a little once the page scrolls under it.
let ticking = false;
window.addEventListener("scroll", () => {
  if (ticking) return;
  ticking = true;
  requestAnimationFrame(() => { document.body.classList.toggle("scrolled", window.scrollY > 8); ticking = false; });
}, { passive: true });

// ---------- online demo (GitHub Pages): say plainly what is precomputed and what needs the server
function hiddenBefore() { try { return localStorage.getItem(DEMO_HIDDEN) === "1"; } catch { return false; } }
if (STATIC && !hiddenBefore()) {
  const strip = document.createElement("div");
  strip.className = "demo-strip glass";
  strip.setAttribute("role", "note");
  strip.innerHTML = `${icon("info")}<p><strong>Online demo.</strong> Every forecast here was computed by the trained model and saved as a snapshot. `
    + `What if works one setting at a time, the copilot answers its suggested questions, and the Daily log needs the server. `
    + `<a href="https://github.com/Laksh718/FeedForward#run-it-yourself" target="_blank" rel="noopener">Run it yourself</a></p>`
    + `<button type="button" class="icon-btn" aria-label="Hide this notice">${icon("close")}</button>`;
  strip.querySelector("button").addEventListener("click", () => {
    try { localStorage.setItem(DEMO_HIDDEN, "1"); } catch { /* private window: hide for this visit only */ }
    strip.classList.add("out");
    setTimeout(() => strip.remove(), 300);
  });
  document.querySelector(".topbar").after(strip);
}

// ---------- views
mountLanding(document.getElementById("view-landing"));
mountService(document.getElementById("view-service"));
mountDesk(document.getElementById("view-desk"));
mountCalendar(document.getElementById("view-calendar"));
mountAdmin(document.getElementById("view-admin"));
initGlow();

// Approve and Send back confirmations also pop up as a toast, whichever view they came from.
let lastNotice = 0;
subscribe((s) => {
  if (!s.noticeAt || s.noticeAt === lastNotice) return;
  lastNotice = s.noticeAt;
  toast(s.notice, s.noticeKind);
});

window.addEventListener("hashchange", () => showView(location.hash.slice(1)));
showView(location.hash.slice(1));
init();
