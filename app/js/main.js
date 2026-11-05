// Entry point: the shell (logo, view tabs, demo notice, toasts), the view switch, mounting and first load.
import { mountAccount } from "./account.js";
import { mountAdmin } from "./admin.js";
import { mountCalendar } from "./calendar.js";
import { mountCopilot } from "./copilot.js";
import { mountDocs } from "./docs.js";
import { mountDonate } from "./donate.js";
import { mountEvents } from "./events.js";
import { mountForecast } from "./forecast.js";
import { initGlow, liquid, toast } from "./fx.js";
import { icon } from "./icons.js";
import { mountLanding } from "./landing.js";
import { logoMark } from "./logo.js";
import { mountPlans } from "./plans.js";
import { mountService } from "./service.js";
import { init, state, subscribe } from "./state.js";

const VIEWS = ["landing", "service", "forecast", "plans", "events", "copilot", "calendar", "admin", "donate", "docs", "account"];
const ALIASES = { desk: "forecast" };   // older links
// An NGO account only uses the food offers and its own account: the kitchen's planning views are not for it.
const NGO_VIEWS = ["donate", "account"];
const isNgo = () => state.user?.role === "ngo";
const TITLES = { forecast: "FeedForward, forecast", plans: "FeedForward, plans", events: "FeedForward, rare events",
  copilot: "FeedForward, copilot", admin: "FeedForward, daily log", calendar: "FeedForward, calendar",
  donate: "FeedForward, donations", docs: "FeedForward, documents", account: "FeedForward, account",
  service: "FeedForward, service board", landing: "FeedForward, predict. prevent. provide." };

// ---------- shell: logo, tab icons, the liquid pill under the tabs
document.querySelectorAll("[data-logo]").forEach((el) => { el.innerHTML = logoMark({ size: 34 }); });
document.querySelectorAll("[data-icon]").forEach((el) => el.insertAdjacentHTML("afterbegin", icon(el.dataset.icon)));
const tablist = document.querySelector(".viewbar-tabs");
const tabs = [...tablist.querySelectorAll("[role=tab]")];
const moreBtn = document.getElementById("more-btn"), moreMenu = document.getElementById("more-menu");
const menuItems = [...moreMenu.querySelectorAll("[data-view-tab]")];
liquid(tablist);

// ---------- the More menu (Calendar, Daily log, Donations, Documents): keeps the bar to one row on every screen
function closeMenu() { moreMenu.hidden = true; moreBtn.setAttribute("aria-expanded", "false"); }
moreBtn.addEventListener("click", (e) => {
  e.stopPropagation();
  const open = moreMenu.hidden;
  moreMenu.hidden = !open;
  moreBtn.setAttribute("aria-expanded", String(open));
  if (open) (menuItems.find((b) => b.getAttribute("aria-current") === "true") ?? menuItems[0]).focus();
});
menuItems.forEach((b) => b.addEventListener("click", () => { location.hash = b.dataset.viewTab; closeMenu(); }));
document.addEventListener("click", (e) => { if (!moreMenu.hidden && !e.target.closest("#more")) closeMenu(); });
moreMenu.addEventListener("keydown", (e) => {
  const i = menuItems.indexOf(document.activeElement);
  if (e.key === "Escape") { closeMenu(); moreBtn.focus(); }
  if (e.key === "ArrowDown" || e.key === "ArrowUp") { e.preventDefault(); menuItems[(i + (e.key === "ArrowDown" ? 1 : -1) + menuItems.length) % menuItems.length].focus(); }
});

let current = null;
function showView(name) {
  const asked = ALIASES[name] ?? name;
  let view = VIEWS.includes(asked) ? asked : "landing";
  if (isNgo() && !NGO_VIEWS.includes(view)) {
    view = "donate";
    if (location.hash !== "#donate") history.replaceState(null, "", "#donate");
  }
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
  // the More menu: its button takes the name of the view open from it, and shows as selected
  const fromMenu = menuItems.find((b) => b.dataset.viewTab === view);
  menuItems.forEach((b) => b.setAttribute("aria-current", String(b === fromMenu)));
  moreBtn.setAttribute("aria-pressed", String(Boolean(fromMenu)));
  document.getElementById("more-label").textContent = fromMenu ? fromMenu.querySelector("span").firstChild.textContent : "More";
  closeMenu();
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
mountDonate(document.getElementById("view-donate"));
mountDocs(document.getElementById("view-docs"));
mountAccount(document.getElementById("view-account"));

// The account button in the top bar: "Sign in", or the signed in organisation. Signing in or out as an NGO changes
// which views exist, so the open view is checked again.
let shownRole = null;
subscribe((s) => {
  const role = s.user?.role ?? "";
  if (role !== shownRole) {
    shownRole = role;
    document.body.dataset.role = role;
    document.querySelector(".brand").setAttribute("href", role === "ngo" ? "#donate" : "#landing");
    showView(location.hash.slice(1));
  }
  const t = document.getElementById("topbar-account-t");
  const label = s.user ? s.user.org_name : "Sign in";
  if (t.textContent !== label) t.textContent = label;
  document.getElementById("topbar-account").classList.toggle("signed-in", Boolean(s.user));
  document.getElementById("topbar-account").setAttribute("aria-current", location.hash === "#account" ? "page" : "false");
});
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
