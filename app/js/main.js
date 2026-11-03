// Entry point: view switch, mounting and first load.
import { mountAdmin } from "./admin.js";
import { mountCalendar } from "./calendar.js";
import { mountDesk } from "./desk.js";
import { mountLanding } from "./landing.js";
import { mountService } from "./service.js";
import { init } from "./state.js";

const VIEWS = ["landing", "service", "desk", "calendar", "admin"];
const TITLES = { desk: "FeedForward, forecast desk", admin: "FeedForward, daily log", calendar: "FeedForward, calendar",
  service: "FeedForward, service board", landing: "FeedForward, predict. prevent. provide." };

function showView(name) {
  const view = VIEWS.includes(name) ? name : "landing";
  document.body.dataset.view = view;
  document.querySelectorAll("[data-view-panel]").forEach((p) => { p.hidden = p.dataset.viewPanel !== view; });
  document.querySelectorAll("[data-view-tab]").forEach((b) => b.setAttribute("aria-selected", String(b.dataset.viewTab === view)));
  document.title = TITLES[view];
  window.scrollTo(0, 0);
}

mountLanding(document.getElementById("view-landing"));
mountService(document.getElementById("view-service"));
mountDesk(document.getElementById("view-desk"));
mountCalendar(document.getElementById("view-calendar"));
mountAdmin(document.getElementById("view-admin"));
document.querySelectorAll("[data-view-tab]").forEach((b) => b.addEventListener("click", () => {
  location.hash = b.dataset.viewTab;
}));
window.addEventListener("hashchange", () => showView(location.hash.slice(1)));
showView(location.hash.slice(1));
init();
