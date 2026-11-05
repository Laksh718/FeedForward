// Entry point: the shell (logo, view tabs, demo notice, toasts), the view switch, mounting and first load.
import { mountAdmin } from "./admin.js";
import { mountCalendar } from "./calendar.js";
import { mountCopilot } from "./copilot.js";
import { mountEvents } from "./events.js";
import { mountForecast } from "./forecast.js";
import { initGlow, liquid, toast } from "./fx.js";
import { icon } from "./icons.js";
import { mountLanding } from "./landing.js";
import { logoMark } from "./logo.js";
import { mountPlans } from "./plans.js";
import { mountService } from "./service.js";
import { init, subscribe } from "./state.js";

const VIEWS = ["landing", "service", "forecast", "plans", "events", "copilot", "calendar", "admin"];
const ALIASES = { desk: "forecast" };   // older links
const TITLES = { forecast: "FeedForward, forecast", plans: "FeedForward, plans", events: "FeedForward, rare events",
  copilot: "FeedForward, copilot", admin: "FeedForward, daily log", calendar: "FeedForward, calendar",
  service: "FeedForward, service board", landing: "FeedForward, predict. prevent. provide." };

// ---------- shell: logo, tab icons, the liquid pill under the tabs
document.querySelectorAll("[data-logo]").forEach((el) => { el.innerHTML = logoMark({ size: 34 }); });
document.querySelectorAll("[data-icon]").forEach((el) => el.insertAdjacentHTML("afterbegin", icon(el.dataset.icon)));
const tablist = document.querySelector(".viewbar-tabs");
const tabs = [...tablist.querySelectorAll("[role=tab]")];
liquid(tablist);

let current = null;
function showView(name) {
  const asked = ALIASES[name] ?? name;
  const view = VIEWS.includes(asked) ? asked : "landing";
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
  if (changed) {
    window.scrollTo({ top: 0, behavior: "instant" });
    window.dispatchEvent(new CustomEvent("ff:view", { detail: view }));   // views that load on first show listen
  }
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

// ---------- views
mountLanding(document.getElementById("view-landing"));
mountService(document.getElementById("view-service"));
mountForecast(document.getElementById("view-forecast"));
mountPlans(document.getElementById("view-plans"));
mountEvents(document.getElementById("view-events"));
mountCopilot(document.getElementById("view-copilot"));
mountCalendar(document.getElementById("view-calendar"));
mountAdmin(document.getElementById("view-admin"));
initGlow();

// Every confirmation (a decision, a save, an automatic run) pops up as a toast, whichever view it came from.
let lastNotice = 0;
subscribe((s) => {
  if (!s.noticeAt || s.noticeAt === lastNotice) return;
  lastNotice = s.noticeAt;
  toast(s.notice, s.noticeKind);
});

window.addEventListener("hashchange", () => showView(location.hash.slice(1)));
showView(location.hash.slice(1));
init();
