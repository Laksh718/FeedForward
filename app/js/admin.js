// Daily log (admin): PIN, then a form in five sections, recent entries, CSV export and forecast versus actual.
import { api, auth } from "./api.js";
import { SLOTS, WEATHER_TYPES, cap, esc, fmt } from "./util.js";

const WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
const TABLES = ["day_context", "attendance", "kitchen_log", "ingredient_usage"];
const SPECIAL_TYPES = { holiday: "Holiday", rain_holiday: "Rain holiday", campus_event: "Campus event", other: "Other" };
const WHY = "We ask for portions eaten or left over, and whether the dish ran out, because without them a row cannot be used for learning. "
  + "Portions wanted are the portions eaten plus any not served.";

const num = (v) => (v === "" || v === null || v === undefined ? null : Number(v));
const opts = (obj, blank) => (blank ? `<option value="">${blank}</option>` : "") + Object.entries(obj).map(([k, v]) => `<option value="${k}">${v}</option>`).join("");

const SKELETON = `
  <header><h1>Daily log</h1><p class="ad-sub">Real entries are saved so the next forecasts can learn from them.</p></header>
  <section class="ad-card" id="ad-gate" aria-labelledby="ad-gate-t"><h2 id="ad-gate-t">Admin PIN</h2>
    <p class="ad-help">The PIN is set as ADMIN_PIN in the .env file.</p>
    <form id="ad-pin-form" class="ad-actions" style="margin-top:0"><label class="sr-only" for="ad-pin">PIN</label>
      <input id="ad-pin" type="password" autocomplete="off" placeholder="PIN" style="min-height:44px;padding:0 12px;border:1px solid #B7C2B8;border-radius:8px">
      <button class="btn btn-primary" type="submit">Unlock</button></form><div id="ad-gate-msg"></div></section>
  <div id="ad-app" hidden>
    <section class="ad-card" aria-labelledby="ad-s1"><h2 id="ad-s1">1. Day context</h2>
      <p class="ad-help">Past dates can be filled in later. Future dates take expected weather and special day information only.</p>
      <div class="ad-grid">
        <div class="ad-field"><label for="ad-date">Date</label><input id="ad-date" type="date"></div>
        <div class="ad-field"><label for="ad-wd">Weekday</label><select id="ad-wd">${WEEKDAYS.map((w) => `<option>${w}</option>`).join("")}</select></div>
        <div class="ad-field"><label for="ad-tmax">Maximum temperature (C)</label><input id="ad-tmax" type="number" min="10" max="50" step="0.5"></div>
        <div class="ad-field"><label for="ad-tmin">Minimum temperature (C)</label><input id="ad-tmin" type="number" min="10" max="50" step="0.5"></div>
        <div class="ad-field"><label for="ad-weather">Weather</label><select id="ad-weather"><option value="">Not entered</option>${WEATHER_TYPES.map((w) => `<option>${esc(w)}</option>`).join("")}</select></div>
      </div>
      <div class="ad-grid" style="margin-top:14px">
        <div class="ad-field"><label class="ad-toggle"><input id="ad-sp" type="checkbox">Special day</label>
          <div class="ad-sub-fields" id="ad-sp-f" hidden><select id="ad-sp-type" aria-label="Special day type">${opts(SPECIAL_TYPES, "Choose a type")}</select>
            <input id="ad-sp-name" aria-label="Special day name" placeholder="Name, for example Founder's day"></div></div>
        <div class="ad-field"><label class="ad-toggle"><input id="ad-ex" type="checkbox">Exam week</label>
          <div class="ad-sub-fields" id="ad-ex-f" hidden><select id="ad-ex-type" aria-label="Exam type">${opts({ formative_test: "Formative test", university_exam: "University exam" }, "Choose a type")}</select></div></div>
        <div class="ad-field"><label class="ad-toggle"><input id="ad-fe" type="checkbox">Festival</label>
          <div class="ad-sub-fields" id="ad-fe-f" hidden><input id="ad-fe-name" aria-label="Festival name" placeholder="Name, for example Deepavali">
            <select id="ad-fe-scale" aria-label="Festival scale">${opts({ major: "Major", minor: "Minor" }, "Major or minor")}</select></div></div>
      </div></section>
    <div id="ad-future" class="ad-note" hidden>This date is in the future, so only the day context above is saved. Enter attendance, dishes and ingredients after the day.</div>
    <div id="ad-past">
    <section class="ad-card" aria-labelledby="ad-s2"><h2 id="ad-s2">2. Attendance</h2>
      <p class="ad-help">How many students ate in each meal slot.</p>
      <div class="ad-grid">${SLOTS.map((s) => `<div class="ad-field"><label for="ad-att-${s}">${cap(s)}: students who ate</label><input id="ad-att-${s}" data-att="${s}" type="number" min="0" max="4000"></div>`).join("")}
        <div class="ad-field"><label for="ad-present">Students on campus (optional)</label><input id="ad-present" type="number" min="0" max="4000"></div></div></section>
    <section class="ad-card" aria-labelledby="ad-s3"><h2 id="ad-s3">3. Dishes and quantities</h2><p class="ad-help">${WHY}</p>
      <div class="ad-pills" role="group" aria-label="Meal slot">${SLOTS.map((s) => `<button type="button" data-slot="${s}" aria-pressed="false">${cap(s)}</button>`).join("")}</div>
      <div class="ad-tablewrap"><table><thead><tr><th>Dish</th><th>Prepared</th><th>Top up</th><th>Eaten</th><th>Left over</th><th>Ran out early</th><th>Not served</th></tr></thead><tbody id="ad-rows"></tbody></table></div>
      <div class="ad-actions"><label class="sr-only" for="ad-add">Add a dish not on the menu</label><select id="ad-add" style="min-height:44px;min-width:240px;border:1px solid #B7C2B8;border-radius:8px;padding:0 10px"><option value="">Add a dish not on the menu</option></select>
        <button class="btn btn-small" id="ad-add-btn" type="button">Add dish</button></div></section>
    <section class="ad-card" aria-labelledby="ad-s4"><h2 id="ad-s4">4. Ingredients used</h2><p class="ad-help">Kilograms used in the day. Pick from the ingredient list, or type a new one.</p>
      <div class="ad-tablewrap"><table><thead><tr><th>Ingredient</th><th>Used (kg)</th><th><span class="sr-only">Remove</span></th></tr></thead><tbody id="ad-ing"></tbody></table></div>
      <datalist id="ad-ing-list"></datalist>
      <div class="ad-actions"><button class="btn btn-small" id="ad-ing-add" type="button">Add ingredient</button>
        <button class="btn btn-small" id="ad-fill" type="button">Fill from recipes</button></div></section></div>
    <section class="ad-card" aria-labelledby="ad-s5"><h2 id="ad-s5">5. Review and save</h2>
      <p class="ad-help">Warnings point at values that look unusual compared with what the model expected. They never stop a save.</p>
      <div class="ad-field" style="max-width:320px"><label for="ad-by">Entered by (optional)</label><input id="ad-by" maxlength="60"></div>
      <div class="ad-actions"><button class="btn" id="ad-check" type="button">Check entry</button><button class="btn btn-primary" id="ad-save" type="button">Save day</button></div>
      <div id="ad-msg" aria-live="polite"></div></section>
    <section class="ad-card" aria-labelledby="ad-s6"><h2 id="ad-s6">Recent entries</h2>
      <div class="ad-tablewrap"><table><thead><tr><th>Date</th><th>Context</th><th>Attendance</th><th>Dishes</th><th>Ingredients</th><th>Saved at</th><th><span class="sr-only">Actions</span></th></tr></thead><tbody id="ad-recent"></tbody></table></div>
      <div class="ad-actions">${TABLES.map((t) => `<button class="btn btn-small" data-export="${t}" type="button">Export ${t}.csv</button>`).join("")}</div></section>
    <section class="ad-card" aria-labelledby="ad-s7"><h2 id="ad-s7">Forecast versus actual</h2>
      <p class="ad-help">Approved forecasts next to what was logged afterwards.</p><div id="ad-cmp"></div></section>
  </div>`;

export function mountAdmin(root) {
  root.innerHTML = SKELETON;
  const $ = (s) => root.querySelector(s);
  const S = { slot: "lunch", rows: {}, menu: null, ingredients: [], catalogue: [], ing: [], today: null };
  const showMsg = (html, kind) => { $("#ad-msg").innerHTML = html ? `<div class="ad-msg ${kind}">${html}</div>` : ""; };
  const list = (items) => `<ul>${items.map((i) => `<li>${esc(i)}</li>`).join("")}</ul>`;
  const errText = (e) => (e.fields ? list(e.fields.map((f) => `${f.field}: ${f.problem}`)) : "") || `${esc(e.message)} ${esc(e.fix || "")}`;

  // ---------- PIN
  async function unlock(pin) {
    auth.pin = pin;
    try {
      const r = await api.post("/admin/login", {});
      try { sessionStorage.setItem("ffpin", pin); } catch { /* private window: stay unlocked for this page only */ }
      S.today = r.today;
      $("#ad-gate").hidden = true;
      $("#ad-app").hidden = false;
      const [ing, cat] = await Promise.all([api.get("/ingredients"), api.get("/dishes")]);
      S.ingredients = ing.ingredients.map((i) => i.ingredient);
      S.catalogue = cat.dishes;
      $("#ad-ing-list").innerHTML = S.ingredients.map((i) => `<option value="${esc(i)}">`).join("");
      $("#ad-add").innerHTML = `<option value="">Add a dish not on the menu</option>` + S.catalogue.map((d) => `<option value="${d.dish_id}">${esc(d.dish_name)}</option>`).join("");
      $("#ad-date").value = S.today;
      await loadDay(S.today);
      refreshSide();
    } catch (e) {
      auth.pin = "";
      $("#ad-gate").hidden = false;
      $("#ad-app").hidden = true;
      $("#ad-gate-msg").innerHTML = `<div class="ad-msg bad" role="alert"><strong>${esc(e.message)}</strong> ${esc(e.fix || "")}</div>`;
    }
  }
  $("#ad-pin-form").addEventListener("submit", (e) => { e.preventDefault(); unlock($("#ad-pin").value); });

  // ---------- load a date (menu defaults plus anything already saved)
  let loadSeq = 0;
  async function loadDay(date) {
    const mine = ++loadSeq;                       // a quick second date change must not be overwritten by the slower first one
    const m = await api.get("/admin/menu", { date });
    if (mine !== loadSeq) return;
    S.menu = m;
    S.rows = {};
    SLOTS.forEach((s) => {
      S.rows[s] = {};
      m.slots[s].forEach((d) => { S.rows[s][d.dish_id] = { name: d.dish_name, prepared: "", topup: "", eaten: "", left: "", ran: false, unmet: "" }; });
    });
    const sv = m.saved;
    sv.kitchen_log.forEach((k) => {
      const row = (S.rows[k.meal_slot][k.dish_id] ??= { name: S.catalogue.find((d) => d.dish_id === k.dish_id)?.dish_name ?? k.dish_id });
      Object.assign(row, { prepared: k.prepared_qty, topup: k.topup_qty || "", eaten: k.consumed_qty, left: k.leftover_qty, ran: String(k.ran_out_early) === "1", unmet: Number(k.unmet_qty) || "" });
    });
    SLOTS.forEach((s) => { $(`#ad-att-${s}`).value = ""; });
    sv.attendance.forEach((a) => { $(`#ad-att-${a.meal_slot}`).value = a.attendance; if (a.students_present !== "") $("#ad-present").value = a.students_present; });
    const c = sv.day_context[0] || {};
    $("#ad-tmax").value = c.temp_max_c ?? ""; $("#ad-tmin").value = c.temp_min_c ?? ""; $("#ad-weather").value = c.condition ?? "";
    const on = (k) => String(c[k]) === "1";
    $("#ad-sp").checked = on("special_day"); $("#ad-sp-type").value = c.special_day_type ?? ""; $("#ad-sp-name").value = c.special_day_name ?? "";
    $("#ad-ex").checked = on("exam_week"); $("#ad-ex-type").value = c.exam_type ?? "";
    $("#ad-fe").checked = on("festival"); $("#ad-fe-name").value = c.festival_name ?? ""; $("#ad-fe-scale").value = c.festival_scale ?? "";
    S.ing = sv.ingredient_usage.map((i) => ({ ingredient: i.ingredient, used_kg: i.used_kg }));
    $("#ad-wd").value = m.weekday;
    $("#ad-future").hidden = date <= S.today;
    $("#ad-past").hidden = date > S.today;
    toggles();
    renderRows();
    renderIng();
    showMsg("", "");
  }

  function toggles() {
    $("#ad-sp-f").hidden = !$("#ad-sp").checked; $("#ad-ex-f").hidden = !$("#ad-ex").checked; $("#ad-fe-f").hidden = !$("#ad-fe").checked;
  }
  ["#ad-sp", "#ad-ex", "#ad-fe"].forEach((s) => $(s).addEventListener("change", toggles));
  $("#ad-date").addEventListener("change", (e) => e.target.value && loadDay(e.target.value));
  $("#ad-wd").addEventListener("change", (e) => {          // move to that weekday in the same Monday to Sunday week
    const d = new Date(`${$("#ad-date").value}T00:00:00`);
    const shift = WEEKDAYS.indexOf(e.target.value) - ((d.getDay() + 6) % 7);
    d.setDate(d.getDate() + shift);
    $("#ad-date").value = d.toLocaleDateString("en-CA");
    loadDay($("#ad-date").value);
  });

  // ---------- dishes table
  function renderRows() {
    root.querySelectorAll("[data-slot]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.slot === S.slot)));
    const rows = S.rows[S.slot] || {};
    const cell = (id, key, extra = "") => `<td><input type="number" min="0" data-dish="${id}" data-k="${key}" value="${rows[id][key] ?? ""}" ${extra} aria-label="${esc(rows[id].name)}: ${key}"></td>`;
    $("#ad-rows").innerHTML = Object.keys(rows).map((id) => `<tr><td>${esc(rows[id].name)}</td>${cell(id, "prepared")}${cell(id, "topup")}${cell(id, "eaten")}${cell(id, "left")}
      <td><input type="checkbox" data-dish="${id}" data-k="ran" ${rows[id].ran ? "checked" : ""} aria-label="${esc(rows[id].name)}: ran out early"></td>${cell(id, "unmet", rows[id].ran ? "" : "disabled")}</tr>`).join("")
      || `<tr><td colspan="7" class="ad-help">No dishes on the menu for this slot on this day. Add one below.</td></tr>`;
  }
  root.querySelectorAll("[data-slot]").forEach((b) => b.addEventListener("click", () => { S.slot = b.dataset.slot; renderRows(); }));
  $("#ad-rows").addEventListener("input", (e) => {
    const t = e.target, row = S.rows[S.slot][t.dataset.dish];
    if (!row) return;
    row[t.dataset.k] = t.type === "checkbox" ? t.checked : t.value;
    if (t.dataset.k === "ran") renderRows();
  });
  $("#ad-add-btn").addEventListener("click", () => {
    const id = $("#ad-add").value;
    if (!id) return;
    S.rows[S.slot][id] ??= { name: S.catalogue.find((d) => d.dish_id === id).dish_name, prepared: "", topup: "", eaten: "", left: "", ran: false, unmet: "" };
    renderRows();
  });

  // ---------- ingredients
  function renderIng() {
    $("#ad-ing").innerHTML = S.ing.map((r, i) => `<tr><td><input list="ad-ing-list" data-i="${i}" data-k="ingredient" value="${esc(r.ingredient)}" aria-label="Ingredient"></td>
      <td><input type="number" min="0" step="0.1" data-i="${i}" data-k="used_kg" value="${r.used_kg}" aria-label="Kilograms used"></td>
      <td><button class="btn btn-small" type="button" data-rm="${i}">Remove</button></td></tr>`).join("") || `<tr><td colspan="3" class="ad-help">No ingredients entered.</td></tr>`;
  }
  $("#ad-ing").addEventListener("input", (e) => { const t = e.target; if (t.dataset.i) S.ing[t.dataset.i][t.dataset.k] = t.value; });
  $("#ad-ing").addEventListener("click", (e) => { if (e.target.dataset.rm) { S.ing.splice(Number(e.target.dataset.rm), 1); renderIng(); } });
  $("#ad-ing-add").addEventListener("click", () => { S.ing.push({ ingredient: "", used_kg: "" }); renderIng(); });
  $("#ad-fill").addEventListener("click", async () => {
    const rows = SLOTS.flatMap((s) => Object.entries(S.rows[s]).filter(([, r]) => r.prepared !== "").map(([id, r]) => ({ dish_id: id, prepared_qty: Number(r.prepared) })));
    if (!rows.length) { showMsg("Enter prepared quantities in section 3 first. The ingredient quantities are worked out from them.", "warn"); return; }
    try {
      S.ing = (await api.post("/admin/fill-recipes", { rows })).ingredients;
      renderIng();
      showMsg(`Filled ${S.ing.length} ingredients from the recipes. The numbers are estimates, so edit them to match what was really used.`, "ok");
    } catch (e) { showMsg(errText(e), "bad"); }
  });

  // ---------- build the request, check, save
  function payload() {
    const date = $("#ad-date").value, ctx = { date };
    const keep = { temp_max_c: num($("#ad-tmax").value), temp_min_c: num($("#ad-tmin").value), weather_type: $("#ad-weather").value || null };
    Object.assign(ctx, keep, {
      special_day: $("#ad-sp").checked, special_day_type: $("#ad-sp-type").value || null, special_day_name: $("#ad-sp-name").value || null,
      exam_week: $("#ad-ex").checked, exam_type: $("#ad-ex-type").value || null,
      festival: $("#ad-fe").checked, festival_name: $("#ad-fe-name").value || null, festival_scale: $("#ad-fe-scale").value || null,
    });
    const present = num($("#ad-present").value);
    const body = { date, entered_by: $("#ad-by").value || null, context: ctx, attendance: [], kitchen: [], ingredients: [] };
    if (date > S.today) return body;
    SLOTS.forEach((s) => { const a = num($(`#ad-att-${s}`).value); if (a !== null) body.attendance.push({ meal_slot: s, attendance: a, students_present: present }); });
    SLOTS.forEach((s) => Object.entries(S.rows[s]).forEach(([id, r]) => {
      if (r.prepared === "" || r.prepared === null) return;
      body.kitchen.push({ meal_slot: s, dish_id: id, prepared_qty: num(r.prepared), topup_qty: num(r.topup) ?? 0, consumed_qty: num(r.eaten), leftover_qty: num(r.left),
        ran_out_early: !!r.ran, unmet_qty: r.ran ? num(r.unmet) : null });
    }));
    body.ingredients = S.ing.filter((i) => i.ingredient && i.used_kg !== "").map((i) => ({ ingredient: i.ingredient, used_kg: Number(i.used_kg) }));
    return body;
  }
  const warnHtml = (ws) => (ws.length ? `<div class="ad-msg warn"><strong>${ws.length} warning${ws.length > 1 ? "s" : ""}</strong>${list(ws.map((w) => w.message))}</div>` : "");

  $("#ad-check").addEventListener("click", async () => {
    try {
      const r = await api.post("/admin/validate", payload());
      $("#ad-msg").innerHTML = r.warnings.length ? warnHtml(r.warnings) : `<div class="ad-msg ok">No problems found. Nothing looks unusual.</div>`;
    } catch (e) { showMsg(errText(e), "bad"); }
  });
  $("#ad-save").addEventListener("click", async () => {
    try {
      const r = await api.post("/admin/day", payload());
      const c = r.saved;
      $("#ad-msg").innerHTML = `<div class="ad-msg ok" role="status"><strong>Saved ${esc($("#ad-date").value)}.</strong> ${c.day_context} day context, ${c.attendance} attendance, ${c.kitchen_log} dish rows and ${c.ingredient_usage} ingredient rows. Forecasts now use this day.</div>${warnHtml(r.warnings)}`;
      refreshSide();
    } catch (e) { showMsg(errText(e), "bad"); }
  });

  // ---------- recent entries, export, forecast versus actual
  async function refreshSide() {
    try {
      const { days } = await api.get("/admin/recent");
      $("#ad-recent").innerHTML = days.map((d) => `<tr><td>${esc(d.date)} ${esc(d.weekday.slice(0, 3))}</td><td>${d.day_context}</td><td>${d.attendance}</td><td>${d.kitchen_log}</td><td>${d.ingredient_usage}</td>
        <td>${esc(d.entered_at.replace("T", " "))}</td><td><button class="btn btn-small" data-edit="${d.date}" type="button">Edit</button> <button class="btn btn-small" data-del="${d.date}" type="button">Delete</button></td></tr>`).join("")
        || `<tr><td colspan="7" class="ad-help">Nothing saved yet. Save a day above and it appears here.</td></tr>`;
      const cmp = await api.get("/admin/forecast-vs-actual");
      $("#ad-cmp").innerHTML = cmp.summary ? `<p class="ad-help">${cmp.summary.rows} dishes compared. ${cmp.summary.inside_range_pct} percent landed inside the likely range. Average miss of the most likely amount: ${fmt(cmp.summary.mean_abs_error_most_likely)} portions, of the usual plan: ${fmt(cmp.summary.mean_abs_error_usual_plan)}.</p>
        <div class="ad-tablewrap"><table><thead><tr><th>Date</th><th>Slot</th><th>Dish</th><th>Likely range</th><th>Most likely</th><th>Usual plan</th><th>Cooked or approved</th><th>Actual wanted</th><th>Result</th></tr></thead><tbody>${cmp.rows.map((r) =>
          `<tr><td>${esc(r.date)}</td><td>${esc(r.meal_slot)}</td><td>${esc(r.dish_id)}</td><td>${fmt(r.p10)} to ${fmt(r.p90)}</td><td>${fmt(r.p50)}</td><td>${fmt(r.usual_plan)}</td><td>${fmt(r.recommended)}</td><td>${fmt(r.actual_demand)}</td>
          <td class="${r.inside_range ? "ad-inside" : "ad-outside"}">${r.inside_range ? "Inside range" : "Outside range"}</td></tr>`).join("")}</tbody></table></div>`
        : `<p class="ad-help">No approved forecast has logged actuals yet. Approve a plan on the Service board, then log what happened on that day here.</p>`;
    } catch (e) { $("#ad-cmp").innerHTML = `<div class="ad-msg bad">${errText(e)}</div>`; }
  }
  $("#ad-recent").addEventListener("click", async (e) => {
    const t = e.target;
    if (t.dataset.edit) { $("#ad-date").value = t.dataset.edit; await loadDay(t.dataset.edit); scrollTo({ top: 0, behavior: "smooth" }); }
    if (t.dataset.del && confirm(`Delete everything saved for ${t.dataset.del}? The rows stay in the file marked as deleted, and forecasts ignore them.`)) {
      for (const table of TABLES) await api.del("/admin/entry", { table, date: t.dataset.del });
      showMsg(`Deleted the entries of ${esc(t.dataset.del)}.`, "ok");
      if ($("#ad-date").value === t.dataset.del) await loadDay(t.dataset.del);
      refreshSide();
    }
  });
  root.querySelectorAll("[data-export]").forEach((b) => b.addEventListener("click", async () => {
    try {
      const text = await api.text("/admin/export", { table: b.dataset.export });
      const a = Object.assign(document.createElement("a"), { href: URL.createObjectURL(new Blob([text], { type: "text/csv" })), download: `${b.dataset.export}.csv` });
      a.click();
      URL.revokeObjectURL(a.href);
    } catch (e) { showMsg(errText(e), "bad"); }
  }));

  let saved = "";
  try { saved = sessionStorage.getItem("ffpin") || ""; } catch { /* storage blocked */ }
  if (saved) unlock(saved);
}
