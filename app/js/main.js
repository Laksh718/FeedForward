// Entry point: view switch, mounting and first load.
import { mountAdmin } from "./admin.js";
import { mountDesk } from "./desk.js";
import { mountService } from "./service.js";
import { init } from "./state.js";

const VIEWS = ["service", "desk", "admin"];

function showView(name) {
  const view = VIEWS.includes(name) ? name : "service";
  document.body.dataset.view = view;
  document.querySelectorAll("[data-view-panel]").forEach((p) => { p.hidden = p.dataset.viewPanel !== view; });
  document.querySelectorAll("[data-view-tab]").forEach((b) => b.setAttribute("aria-selected", String(b.dataset.viewTab === view)));
  document.title = { desk: "FeedForward, forecast desk", admin: "FeedForward, daily log" }[view] ?? "FeedForward, service board";
}

mountService(document.getElementById("view-service"));
mountDesk(document.getElementById("view-desk"));
mountAdmin(document.getElementById("view-admin"));
document.querySelectorAll("[data-view-tab]").forEach((b) => b.addEventListener("click", () => {
  location.hash = b.dataset.viewTab;
}));
window.addEventListener("hashchange", () => showView(location.hash.slice(1)));
showView(location.hash.slice(1));
init();
