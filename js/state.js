// One shared store for both views. Views read `state` and call the actions below.
import { api, ApiError } from "./api.js";

export const state = {
  health: null, slot: "lunch", date: null, weekStart: null, scope: "core", dishId: null,
  overrides: {}, plan: null, whatif: null, week: null, weekDish: null, menu: [],
  editing: false, adjusted: {}, loading: true, error: null, notice: "",
  chat: [], chatBusy: false,
};

const listeners = new Set();
const emit = () => listeners.forEach((fn) => fn(state));
export function subscribe(fn) { listeners.add(fn); fn(state); }

let seq = 0;
const hasOverrides = () => Object.keys(state.overrides).length > 0;
const fail = (e) => { state.error = e instanceof ApiError ? { message: e.message, fix: e.fix } : { message: String(e.message || e), fix: "Refresh the page." }; };

// parts: which pieces to reload
export async function refresh(parts = { plan: true, week: true, dish: true, menu: true }) {
  const mine = ++seq;
  state.loading = true;
  state.error = null;
  emit();
  const { slot, date, scope, weekStart, dishId, overrides } = state;
  try {
    const jobs = {};
    if (parts.plan) jobs.plan = hasOverrides()
      ? api.post("/whatif", { date, meal_slot: slot, scope, overrides })
      : api.get("/plan", { date, slot, scope });
    if (parts.week) jobs.week = api.get("/week", { slot, start: weekStart, scope });
    if (parts.dish) jobs.weekDish = dishId ? api.get("/week", { slot, start: weekStart, dish_id: dishId }) : Promise.resolve(null);
    if (parts.menu) jobs.menu = api.get("/dishes", { date, slot });
    const done = await Promise.all(Object.values(jobs));
    if (mine !== seq) return;
    Object.keys(jobs).forEach((k, i) => {
      if (k === "plan") {
        state.plan = hasOverrides() ? done[i].changed : done[i];
        state.whatif = hasOverrides() ? { baseline: done[i].baseline_totals, difference: done[i].difference } : null;
        state.editing = false;
        state.adjusted = {};
      } else if (k === "menu") state.menu = done[i].dishes;
      else state[k] = done[i];
    });
  } catch (e) {
    if (mine === seq) fail(e);
  } finally {
    if (mine === seq) { state.loading = false; emit(); }
  }
}

export async function init() {
  try {
    state.health = await api.get("/health");
    state.date = state.weekStart = state.health.default_plan_date;
  } catch (e) {
    fail(e);
    state.loading = false;
    emit();
    return;
  }
  await refresh();
}

export const setSlot = (slot) => { state.slot = slot; state.overrides = {}; state.dishId = null; return refresh(); };
export const setDate = (date) => { state.date = date; return refresh({ plan: true }); };
export const setScope = (scope) => { state.scope = scope; return refresh({ plan: true, week: true }); };
export const setDish = (id) => { state.dishId = id; return refresh({ dish: true }); };
export const setOverrides = (overrides) => { state.overrides = overrides; return refresh({ plan: true }); };
export const resetOverrides = () => setOverrides({});
export function setEditing(on) { state.editing = on; if (!on) state.adjusted = {}; emit(); }
export function setAdjusted(id, qty) { state.adjusted[id] = qty; emit(); }

export async function review(decision) {
  state.notice = "";
  try {
    const adjusted = Object.fromEntries(Object.entries(state.adjusted).filter(([id, q]) => {
      const row = state.plan.dishes.find((d) => d.dish_id === id);
      return row && q !== row.recommended;
    }));
    const r = await api.post("/review", { date: state.date, meal_slot: state.slot, decision, scope: state.scope,
      overrides: state.overrides, adjusted_quantities: adjusted });
    state.plan.review = r.review;
    state.notice = r.message;
    state.editing = false;
  } catch (e) {
    state.notice = `${e.message} ${e.fix || ""}`.trim();
  }
  emit();
}

export async function ask(question) {
  const text = question.trim();
  if (!text || state.chatBusy) return;
  state.chat.push({ role: "user", text });
  state.chatBusy = true;
  emit();
  try {
    const r = await api.post("/chat", { question: text, date: state.date, meal_slot: state.slot, scope: state.scope, overrides: state.overrides });
    state.chat.push({ role: "bot", text: r.answer, source: r.source });
  } catch (e) {
    const missing = e.status === 404 || e.status === 405;
    state.chat.push({ role: "err", text: missing
      ? "The copilot is not available on this server. The numbers on this page are not affected."
      : `${e.message} ${e.fix || ""}`.trim() });
  }
  state.chatBusy = false;
  emit();
}
