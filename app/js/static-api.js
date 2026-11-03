// Static demo mode: answers the dashboard's API calls from the JSON snapshot that scripts/build_static_site.py
// writes next to the page (data/...). Used on GitHub Pages, where no Python server runs. Every response has the
// same shape as the live API's, so the views do not know the difference. What needs the server (free questions
// to the copilot, what if combinations, the Daily log) answers with a plain message that says how to get it.
import { ApiError } from "./api.js";

const DATA = new URL("data/", document.baseURI);
const files = new Map();   // path -> Promise of parsed JSON, or null when the snapshot has no such file
const REVIEWS_KEY = "feedforward-demo-reviews";
const RUN_LOCALLY = "Run FeedForward locally for the full version (see the README on GitHub).";

function load(path) {
  if (!files.has(path)) {
    files.set(path, fetch(new URL(path, DATA)).then((res) => {
      if (res.status === 404) return null;
      if (!res.ok) throw new Error(String(res.status));
      return res.json();
    }).catch((e) => {
      files.delete(path);   // let a later call try again
      throw new ApiError(0, "Could not load the demo data.", `Check your connection and refresh the page. (${e.message})`);
    }));
  }
  return files.get(path);
}

const copy = (x) => (x == null ? x : structuredClone(x));
const health = () => load("health.json");
const demoInfo = async () => (await health()).demo;
const range = (dates) => (dates.length ? `${dates[0]} to ${dates[dates.length - 1]}` : "no dates");
// "Not in the snapshot" errors carry miss = true: with a deployed server configured (api.js REMOTE), those calls go
// to the server instead; without one, the message is shown as it is.
const miss = (e) => Object.assign(e, { miss: true });
const serverOnly = (what) => miss(new ApiError(503, `${what} needs the FeedForward server, so it is switched off in this online demo.`, RUN_LOCALLY));

// Same canonical form the build script uses: the given settings, sorted by name, as name=value joined by &.
export const overridesKey = (o = {}) => Object.keys(o).filter((k) => o[k] !== undefined && o[k] !== null).sort()
  .map((k) => `${k}=${o[k]}`).join("&");

async function day(date) {
  const h = await health();
  const d = date || h.default_plan_date;
  const bundle = await load(`days/${d}.json`);
  if (!bundle) throw new ApiError(400, `No calendar for ${d}. Choose a date from ${h.demo.first_date} to ${h.demo.last_date}.`, "Change the input and try again.");
  return { date: d, bundle };
}

// Approve or Send back is kept in this browser only (localStorage), so the demo stays read only for everyone else.
function readReviews() {
  try { return JSON.parse(localStorage.getItem(REVIEWS_KEY)) || {}; } catch { return {}; }
}
function saveReview(date, slot, review) {
  const all = readReviews();
  all[`${date}|${slot}`] = review;
  try { localStorage.setItem(REVIEWS_KEY, JSON.stringify(all)); } catch { /* private window: keep it for this page only */ }
  memoryReviews[`${date}|${slot}`] = review;
}
const memoryReviews = {};
const latestReview = (date, slot) => memoryReviews[`${date}|${slot}`] ?? readReviews()[`${date}|${slot}`] ?? null;

async function plan({ date, slot = "lunch", scope = "core" }) {
  const { date: d, bundle } = await day(date);
  const p = copy(bundle.plans?.[slot]?.[scope]);
  if (!p) throw new ApiError(400, `No plan for ${slot} on ${d} in this demo.`, "Pick another meal or day.");
  p.review = latestReview(d, slot) ?? p.review;
  return p;
}

async function dishes({ date, slot }) {
  if (!date || !slot) throw serverOnly("The full dish catalogue");
  const { bundle } = await day(date);
  return copy(bundle.menu?.[slot] ?? { count: 0, dishes: [] });
}

async function week({ slot = "lunch", start, scope = "core", dish_id: dishId }) {
  const demo = await demoInfo();
  if (start && start !== demo.week_start) {
    throw miss(new ApiError(400, `This demo has the week starting ${demo.week_start} only.`, RUN_LOCALLY));
  }
  const w = await load(dishId ? `week/${slot}/dish/${dishId}.json` : `week/${slot}/${scope}.json`);
  if (!w) throw miss(new ApiError(404, "This week view is not in the demo snapshot.", "Pick another dish or meal."));
  return copy(w);
}

async function calendar({ month }) {
  const m = await load(`calendar/${month}.json`);
  return copy(m) ?? { month, days: [], live_checked: false, live_source: "offline (showing the project's own calendar only)" };
}

async function whatif({ date, meal_slot: slot, scope = "core", overrides = {} }) {
  const demo = await demoInfo();
  const answers = await load(`whatif/${date}.json`);
  if (!answers) {
    throw miss(new ApiError(400, `In this online demo, what if answers are prebuilt for ${range(demo.whatif_dates)} only.`,
      "Pick one of those days in the week chart, or run FeedForward locally to try any date."));
  }
  const hit = answers[slot]?.[scope]?.[overridesKey(overrides)];
  if (!hit) {
    throw miss(new ApiError(400, "This online demo has what if answers for one setting at a time.",
      "Set the other settings back to normal, or run FeedForward locally to combine them."));
  }
  const r = copy(hit);
  r.changed.review = latestReview(date, slot) ?? r.changed.review;
  return r;
}

async function review({ date, meal_slot: slot, decision }) {
  await day(date);
  const r = { decision, reviewed_at: new Date().toISOString().slice(0, 19), reviewer: null, note: null };
  saveReview(date, slot, r);
  const what = decision === "approve" ? "Plan approved" : "Plan sent back";
  return { stored_rows: 0, review: r, message: `${what} and saved in this browser only (online demo).` };
}

async function chat({ question = "", date, meal_slot: slot = "lunch", scope = "core", overrides = {} }) {
  const demo = await demoInfo();
  const d = date || (await health()).default_plan_date;
  const answers = await load(`chat/${d}.json`);
  const asked = question.trim().toLowerCase();
  const prebuilt = answers?.[slot]?.[scope] ?? {};
  const hit = prebuilt[Object.keys(prebuilt).find((q) => q.toLowerCase() === asked)];
  if (!hit) {
    const why = answers
      ? `In this online demo the copilot answers the suggested questions: ${demo.chat_questions.map((q) => `"${q}"`).join(", ")}.`
      : `In this online demo the copilot has prebuilt answers for ${range(demo.chat_dates)} only.`;
    return { answer: `${why} Free questions need the FeedForward server and its copilot. ${RUN_LOCALLY}`, source: "demo" };
  }
  const note = Object.keys(overrides).length ? "\n\n(This prebuilt answer is for the normal plan, without your what if setting.)" : "";
  return { ...copy(hit), answer: hit.answer + note };
}

const ROUTES = {
  "GET /health": async () => copy(await health()),
  "GET /plan": plan,
  "GET /dishes": dishes,
  "GET /week": week,
  "GET /calendar": calendar,
  "POST /whatif": (_, body) => whatif(body),
  "POST /review": (_, body) => review(body),
  "POST /chat": (_, body) => chat(body),
};

export async function staticRequest(method, path, params, body) {
  const route = ROUTES[`${method} ${path.replace(/^\/api/, "")}`];
  if (route) return route(params, body);
  if (path.startsWith("/admin") || path === "/ingredients") throw serverOnly("The Daily log");
  throw miss(new ApiError(404, "This feature is not available in the online demo.", RUN_LOCALLY));
}
