// One shared store for every view. Views read `state` and call the actions below.
//
// Everything that changes saved data (a decision, a Daily log save, an automatic run) ends with `synced()`: it reloads
// the open plan, the plans of the coming days and the activity feed, and bumps `state.dataVersion`, so every view
// that keeps its own data (Forecast, Plans, Rare events, Calendar, Daily log) reloads it too. The server is also asked
// every few seconds whether anything was saved elsewhere (another tab, another person, the automation).
import { api, ApiError, auth, REMOTE, STATIC } from "./api.js";

export const state = {
  health: null, slot: "lunch", date: null, weekStart: null, scope: "core", dishId: null,
  overrides: {}, plan: null, whatif: null, week: null, weekDish: null, menu: [],
  editing: false, adjusted: {}, loading: true, error: null, notice: "", noticeAt: 0, noticeKind: "ok",
  chat: [], chatBusy: false,
  plans: null, activity: [], dataVersion: 0, serverVersion: null,
  eventPreset: null,             // set by the Calendar or Home before opening Rare events: {date, event}
  user: null,                    // the signed in account (kitchen or NGO), or null
  donationPreset: null,          // set by Rare events before opening Donations: {date, slot, items, note}
};

const listeners = new Set();
const emit = () => listeners.forEach((fn) => fn(state));
export function subscribe(fn) { listeners.add(fn); fn(state); }

let seq = 0;
const hasOverrides = () => Object.keys(state.overrides).length > 0;
const fail = (e) => { state.error = e instanceof ApiError ? { message: e.message, fix: e.fix } : { message: String(e.message || e), fix: "Refresh the page." }; };

export function notify(message, kind = "ok") {
  state.notice = message;
  state.noticeKind = kind;
  state.noticeAt = Date.now();   // a new message, even when the text repeats (main.js shows it as a toast)
  emit();
}

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
        state.whatif = hasOverrides() ? { baseline: done[i].baseline_totals, difference: done[i].difference, impact: done[i].impact ?? null } : null;
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

// The plans of the next 7 days (from today) and the activity feed: shared by Home, the Service board, Plans and the
// Calendar, so they always agree. Neither is in the static snapshot; without a server they stay empty.
export async function loadShared() {
  const [plans, activity] = await Promise.allSettled([api.get("/plans", { days: 7 }), api.get("/activity", { limit: 25 })]);
  if (plans.status === "fulfilled") state.plans = plans.value;
  if (activity.status === "fulfilled") { state.activity = activity.value.events; state.serverVersion = activity.value.version; }
  emit();
}

// After anything was saved: reload what every view shows and tell the views that keep their own data.
export async function synced() {
  state.dataVersion += 1;
  await Promise.all([refresh({ plan: true }), loadShared()]);
}

// Ask the server now and then whether anything was saved elsewhere; reload only when it was.
const POLL_MS = 15000;
async function poll() {
  if (document.hidden) return;
  try {
    const { version } = await api.get("/activity/version");
    if (state.serverVersion && version !== state.serverVersion) { state.serverVersion = version; await synced(); }
    else state.serverVersion = version;
  } catch { /* offline or no server: try again later */ }
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
  await Promise.all([refresh(), loadShared(), restoreSession()]);
  if (!STATIC || REMOTE) {
    setInterval(poll, POLL_MS);
    document.addEventListener("visibilitychange", () => { if (!document.hidden) poll(); });
  }
}

export const setSlot = (slot) => { state.slot = slot; state.overrides = {}; state.dishId = null; return refresh(); };
export const setDate = (date) => { state.date = date; return refresh({ plan: true }); };
export const setScope = (scope) => { state.scope = scope; return refresh({ plan: true, week: true }); };
export const setDish = (id) => { state.dishId = id; return refresh({ dish: true }); };
export const setOverrides = (overrides) => { state.overrides = overrides; return refresh({ plan: true }); };
export const resetOverrides = () => setOverrides({});
export function setEditing(on) { state.editing = on; if (!on) state.adjusted = {}; emit(); }
export function setAdjusted(id, qty) { state.adjusted[id] = qty; emit(); }

// Open one plan on the Service board (from Plans, Forecast, Calendar, Home or Rare events).
export function openPlan(date, slot) {
  const slotChanged = Boolean(slot) && slot !== state.slot;
  state.date = date;
  if (slot) state.slot = slot;
  state.overrides = {};
  if (slotChanged) state.dishId = null;
  location.hash = "service";
  return refresh(slotChanged ? undefined : { plan: true, menu: true });
}

// Open Donations with an offer already filled in (from Rare events: the surplus an event leaves).
export function offerSurplus(preset) {
  state.donationPreset = preset;
  location.hash = "donate";
  emit();
}

// Open Rare events with a day and an event chosen.
export function openEvent(date, event) {
  state.eventPreset = { date, event };
  location.hash = "events";
  emit();
}

const DONE = { approve: "ok", send_back: "warn", withdraw: "warn" };

// The decision on the plan open on the Service board, with any quantities the reviewer changed.
export async function review(decision) {
  try {
    const adjusted = Object.fromEntries(Object.entries(state.adjusted).filter(([id, q]) => {
      const row = state.plan.dishes.find((d) => d.dish_id === id);
      return row && q !== row.recommended;
    }));
    const r = await api.post("/review", { date: state.date, meal_slot: state.slot, decision, scope: state.scope,
      overrides: state.overrides, adjusted_quantities: adjusted });
    state.plan.review = r.review;
    state.editing = false;
    notify(r.message, DONE[decision]);
    await synced();
  } catch (e) {
    notify(`${e.message} ${e.fix || ""}`.trim(), "bad");
  }
}

// The same decision on many plans (items: [{date, meal_slot}]).
export async function reviewMany(items, decision) {
  if (!items.length) return null;
  try {
    const r = await api.post("/plans/review", { items, decision });
    notify(r.message, r.done.length ? DONE[decision] : "warn");
    await synced();
    return r;
  } catch (e) {
    notify(`${e.message} ${e.fix || ""}`.trim(), "bad");
    return null;
  }
}

export async function ask(question, context = {}) {
  const text = question.trim();
  if (!text || state.chatBusy) return;
  const date = context.date ?? state.date, slot = context.slot ?? state.slot;
  state.chat.push({ role: "user", text, date, slot });
  state.chatBusy = true;
  emit();
  try {
    const r = await api.post("/chat", { question: text, date, meal_slot: slot, scope: state.scope, overrides: context.overrides ?? state.overrides });
    state.chat.push({ role: "bot", text: r.answer, source: r.source, reason: r.fallback_reason || "", documents: r.documents || [] });
  } catch (e) {
    const missing = e.status === 404 || e.status === 405;
    state.chat.push({ role: "err", text: missing
      ? "The copilot is not available on this server. The numbers on the other pages are not affected."
      : `${e.message} ${e.fix || ""}`.trim() });
  }
  state.chatBusy = false;
  emit();
}

export function clearChat() { state.chat = []; emit(); }

// ---------- accounts: the session token is kept in this browser so a reload stays signed in
const SESSION_KEY = "feedforward-session";
function keep(token) {
  auth.token = token || "";
  try { if (token) localStorage.setItem(SESSION_KEY, token); else localStorage.removeItem(SESSION_KEY); } catch { /* storage blocked */ }
}

export async function restoreSession() {
  let token = "";
  try { token = localStorage.getItem(SESSION_KEY) || ""; } catch { /* storage blocked */ }
  if (!token) return;
  auth.token = token;
  try {
    const { user } = await api.get("/auth/me");
    state.user = user;
    if (!user) keep("");
  } catch { /* server asleep or offline: keep the token and try again on the next load */ }
  emit();
}

export async function signIn(email, password) {
  const r = await api.post("/auth/login", { email, password });
  keep(r.token);
  state.user = r.user;
  notify(r.message, "ok");
  state.dataVersion += 1;
  emit();
  return r;
}

export async function register(body) {
  const r = await api.post("/auth/register", body);
  keep(r.token);
  state.user = r.user;
  notify(r.message, r.user.status === "active" ? "ok" : "warn");
  state.dataVersion += 1;
  emit();
  return r;
}

// One click into the shared demo kitchen or demo NGO (no password).
export async function demoSignIn(role) {
  const r = await api.post("/auth/demo", { role });
  keep(r.token);
  state.user = r.user;
  notify(r.message, "ok");
  state.dataVersion += 1;
  emit();
  return r;
}

export async function signOut() {
  try { await api.post("/auth/logout", {}); } catch { /* the token is forgotten here anyway */ }
  keep("");
  state.user = null;
  notify("Signed out.", "ok");
  state.dataVersion += 1;
  emit();
}

export async function refreshUser() {
  if (!auth.token) return;
  try { state.user = (await api.get("/auth/me")).user; emit(); } catch { /* keep what we have */ }
}
