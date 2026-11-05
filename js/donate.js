// View: Donations. Surplus food goes from kitchens to NGOs and help groups.
// A kitchen builds an offer from what the Daily log says was left over, or from the surplus an approved plan is expected
// to leave, edits it, sets where and until when it can be collected (the hand over time comes from its documents), and
// posts it. Approved NGOs ask for portions with a pickup time; the kitchen accepts, and marks the food collected.
import { api } from "./api.js";
import { liquid, setHTML } from "./fx.js";
import { icon } from "./icons.js";
import { DEMO_BUTTONS } from "./account.js";
import { demoSignIn, notify, state, subscribe, synced } from "./state.js";
import { SLOTS, cap, esc, fmt, shortDate, whenText } from "./util.js";

const OFFER_STATUS = { open: ["approve", "Open"], spoken_for: ["pending", "All portions requested"], completed: ["approve", "Completed"],
  expired: ["send_back", "Expired"], cancelled: ["send_back", "Cancelled"] };
const CLAIM_STATUS = { requested: ["pending", "Requested"], accepted: ["approve", "Accepted"], collected: ["approve", "Collected"],
  declined: ["send_back", "Declined"], withdrawn: ["send_back", "Withdrawn"] };
const pad = (n) => String(n).padStart(2, "0");
const localInput = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
const inHours = (h) => localInput(new Date(Date.now() + h * 3600 * 1000));
const pill = (map, k) => `<span class="status-pill ${map[k]?.[0] ?? ""}">${map[k]?.[1] ?? esc(k)}</span>`;
const until = (iso) => {
  const mins = Math.round((new Date(iso) - Date.now()) / 60000);
  if (mins <= 0) return "deadline passed";
  return mins < 90 ? `${mins} min left` : `${Math.floor(mins / 60)} h ${mins % 60} min left`;
};

const SKELETON = `
  <header class="dn-top"><p class="eyebrow">${icon("leaf")}Donations</p><h1 class="dn-title">Surplus food to people who need it</h1>
    <p class="dn-sub">Kitchens offer what is left over, or what an approved plan is expected to leave; NGOs and help groups ask for it and collect it
      while it is still safe. The hand over time comes from the kitchen's own documents.</p></header>
  <section class="pl-stats" id="dn-stats"></section>
  <div id="dn-rules"></div>
  <div id="dn-body"></div>`;

function offerItems(o) {
  return `<ul class="dn-items">${o.items.map((i) => `<li><span>${esc(i.dish_name || i.dish_id)}</span><b class="num">${fmt(i.portions)}</b></li>`).join("")}</ul>`;
}

const TYPE_ICON = { food_bank: "leaf", shelter: "home", children: "users", elders: "person", community_kitchen: "service", relief: "alert", other: "users" };

function offerHead(o, forNgo = false) {
  const to = o.to_ngo ? `<span class="pl-chip auto">${icon("send")}${forNgo ? "Sent to you" : `Sent to ${esc(o.to_ngo.org_name)}`}</span>` : "";
  return `<div class="dn-offer-head"><div><h3>${esc(o.kitchen_name)} ${to}</h3><p>${esc(cap(o.meal_slot))}, ${esc(shortDate(o.date))} · ${esc(o.location)}${o.contact ? ` · ${esc(o.contact)}` : ""}</p></div>
    ${pill(OFFER_STATUS, o.status)}</div>
    <div class="dn-offer-nums"><span><b class="num">${fmt(o.remaining)}</b> of ${fmt(o.total_portions)} portions left</span>
      <span>${icon("clock")}Collect by ${esc(o.pickup_until.replace("T", " "))}${o.status === "open" ? ` (${until(o.pickup_until)})` : ""}</span></div>`;
}

function kitchenView(s, V) {
  const mine = V.offers.filter((o) => o.kitchen_id === s.user.id);
  const rows = V.items.map((i, n) => `<tr><td>${esc(i.dish_name)}</td><td><input type="number" min="0" step="5" value="${i.portions}" data-item="${n}" aria-label="Portions of ${esc(i.dish_name)}"></td>
    <td><button class="btn btn-small" type="button" data-rm-item="${n}" aria-label="Remove ${esc(i.dish_name)}">${icon("trash")}</button></td></tr>`).join("");
  const total = V.items.reduce((a, i) => a + (Number(i.portions) || 0), 0);
  const min = V.rules.find((r) => r.key === "min_donation_portions");
  return `<div class="dn-grid">
    <div class="dn-col"><section class="ad-card glass" aria-labelledby="dn-new-t"><h2 id="dn-new-t">${icon("plans")}Offer surplus food</h2>
      <div class="ad-grid"><div class="ad-field"><label for="dn-date">Day</label><input id="dn-date" type="date" value="${V.date}"></div>
        <div class="ad-field"><span class="ad-label">Meal</span><div class="seg" id="dn-slot" role="group" aria-label="Meal">${SLOTS.map((x) => `<button type="button" data-slot="${x}" aria-pressed="${x === V.slot}">${cap(x)}</button>`).join("")}</div></div></div>
      <div class="ad-actions"><button class="btn btn-small" type="button" data-suggest="log">${icon("log")}Fill from the Daily log leftovers</button>
        <button class="btn btn-small" type="button" data-suggest="plan">${icon("plans")}Fill from the plan's expected surplus</button></div>
      <p class="ad-help" id="dn-suggest-note">${esc(V.note)}</p>
      <div class="ad-tablewrap"><table class="dn-table"><thead><tr><th>Dish</th><th>Portions</th><th><span class="sr-only">Remove</span></th></tr></thead>
        <tbody>${rows || `<tr><td colspan="3" class="ad-help">No dishes yet. Fill from the log or the plan, or add one below.</td></tr>`}</tbody></table></div>
      <div class="ad-actions"><label class="sr-only" for="dn-add">Add a dish</label><select id="dn-add" class="ad-add-select"><option value="">Add a dish</option>${V.catalogue.map((d) => `<option value="${d.dish_id}">${esc(d.dish_name)}</option>`).join("")}</select>
        <button class="btn btn-small" type="button" id="dn-add-btn">Add</button><span class="dn-total">${fmt(total)} portions</span></div>
      ${min && total && total < min.value ? `<p class="ad-note">Your documents say ${min.value} portions is the smallest donation worth arranging (${esc(min.source)}).</p>` : ""}
      <div class="ad-grid" style="margin-top:14px"><div class="ad-field"><label for="dn-until">Collect by</label><input id="dn-until" type="datetime-local" value="${V.until}"></div>
        <div class="ad-field"><label for="dn-loc">Where</label><input id="dn-loc" maxlength="200" value="${esc(V.location)}" placeholder="Main mess, back gate"></div></div>
      <div class="ad-grid" style="margin-top:12px"><div class="ad-field"><label for="dn-to">Send to</label><select id="dn-to">
          <option value="">Every approved NGO (first to ask)</option>${Object.entries(V.types).map(([k, label]) => {
            const list = V.ngos.filter((n) => n.status === "active" && (n.ngo_type || "other") === k);
            return list.length ? `<optgroup label="${esc(label)}">${list.map((n) => `<option value="${n.id}" ${V.to === n.id ? "selected" : ""}>${esc(n.org_name)}${n.area ? `, ${esc(n.area)}` : ""}${n.capacity ? ` (takes ${n.capacity})` : ""}</option>`).join("")}</optgroup>` : "";
          }).join("")}</select></div>
        <div class="ad-field"><label for="dn-notes">Notes for the NGO (optional)</label><input id="dn-notes" maxlength="500" placeholder="Bring your own containers"></div></div>
      <div class="ad-actions"><button class="btn btn-primary" type="button" id="dn-post" ${total ? "" : "disabled"}>${icon("send")}${V.to ? `Send to ${esc(V.ngos.find((n) => n.id === V.to)?.org_name ?? "the NGO")}` : "Offer to every NGO"}</button></div>
    </section>
    <section class="ad-card glass dn-dir" aria-labelledby="dn-dir-t"><h2 id="dn-dir-t">${icon("users")}NGOs and help groups</h2>
      <p class="ad-help">Pick one to send the food straight to them, or leave "Every approved NGO" and the first group to ask gets it.</p>
      <div class="dn-dir-grid">${V.ngos.filter((n) => n.status === "active").map((n) => `<button type="button" class="dn-ngo ${V.to === n.id ? "on" : ""}" data-to="${n.id}">
        <span class="dn-ngo-ic">${icon(TYPE_ICON[n.ngo_type] || "users")}</span><span><strong>${esc(n.org_name)}</strong>
        <small>${esc(V.types[n.ngo_type] || "Help group")}${n.area ? ` · ${esc(n.area)}` : ""}${n.capacity ? ` · takes ${n.capacity}` : ""}</small></span></button>`).join("")
        || `<p class="ad-help">No approved NGO yet.</p>`}</div>
      ${V.pendingNgos ? `<p class="ad-help">${V.pendingNgos} more waiting for approval: <a href="#account">review them</a>.</p>` : ""}
    </section></div>
    <section class="dn-list dn-mine" aria-labelledby="dn-mine-t"><h2 id="dn-mine-t" class="dn-h">${icon("list")}Your offers</h2>
      ${mine.length ? mine.map((o) => `<article class="dn-offer glass-lite">${offerHead(o)}${offerItems(o)}
        ${o.claims.length ? `<ul class="dn-claims">${o.claims.map((c) => `<li><div><strong>${esc(c.ngo_name)}</strong> asks for <b class="num">${fmt(c.portions)}</b> portions,
          pickup ${esc(c.pickup_at.replace("T", " "))}${c.contact ? ` · ${esc(c.contact)}` : ""}${c.note ? `<small>${esc(c.note)}</small>` : ""}</div>
          <div class="dn-claim-act">${pill(CLAIM_STATUS, c.status)}
            ${c.status === "requested" ? `<button class="btn btn-small btn-primary" type="button" data-claim="${o.id}|${c.id}|accept">${icon("check")}Accept</button>` : ""}
            ${["requested", "accepted"].includes(c.status) ? `<button class="btn btn-small" type="button" data-claim="${o.id}|${c.id}|collected">${icon("leaf")}Collected</button>
              <button class="btn btn-small btn-danger" type="button" data-claim="${o.id}|${c.id}|decline">${icon("close")}Decline</button>` : ""}</div></li>`).join("")}</ul>`
          : `<p class="ad-help">No requests yet.</p>`}
        ${["open", "spoken_for"].includes(o.status) ? `<button class="btn btn-small btn-danger" type="button" data-cancel="${o.id}">${icon("close")}Cancel the offer</button>` : ""}</article>`).join("")
        : `<div class="glass-lite empty"><strong>No offers yet.</strong>Post one on the left and approved NGOs see it at once.</div>`}
    </section></div>`;
}

function ngoView(s, V) {
  const open = V.offers.filter((o) => o.status === "open");
  const mine = V.offers.filter((o) => o.claims.length);
  const pending = s.user.status !== "active";
  return `${pending ? `<div class="ad-note">${icon("clock")} A kitchen has not approved your account yet. You can see the offers; you can ask for food once you are approved.</div>` : ""}
    <div class="dn-grid ngo">
    <section class="dn-list" aria-labelledby="dn-open-t"><h2 id="dn-open-t" class="dn-h">${icon("leaf")}Food you can collect</h2>
      ${open.length ? open.map((o) => `<article class="dn-offer glass-lite ${o.to_ngo ? "to-you" : ""}">${offerHead(o, true)}${offerItems(o)}${o.notes ? `<p class="ad-help">${esc(o.notes)}</p>` : ""}
        <form class="dn-claim-form" data-offer="${o.id}"><div class="ad-field"><label for="dn-p-${o.id}">Portions</label>
          <input id="dn-p-${o.id}" type="number" min="1" max="${o.remaining}" value="${Math.min(o.remaining, s.user.capacity || o.remaining)}" required></div>
          <div class="ad-field"><label for="dn-t-${o.id}">Pickup time</label><input id="dn-t-${o.id}" type="datetime-local" value="${[inHours(0.5), o.pickup_until.slice(0, 16)].sort()[0]}" max="${o.pickup_until.slice(0, 16)}" required></div>
          <div class="ad-field"><label for="dn-n-${o.id}">Note</label><input id="dn-n-${o.id}" maxlength="300" placeholder="Van arriving at the back gate"></div>
          <button class="btn btn-primary" type="submit" ${pending ? "disabled" : ""}>${icon("check")}Ask for it</button></form></article>`).join("")
        : `<div class="glass-lite empty"><strong>No food on offer right now.</strong>Offers appear here as soon as a kitchen posts them; this page checks every few seconds.</div>`}
    </section>
    <section class="dn-list" aria-labelledby="dn-req-t"><h2 id="dn-req-t" class="dn-h">${icon("list")}Your requests</h2>
      ${mine.length ? mine.map((o) => `<article class="dn-offer glass-lite"><div class="dn-offer-head"><div><h3>${esc(o.kitchen_name)}</h3><p>${esc(cap(o.meal_slot))}, ${esc(shortDate(o.date))} · ${esc(o.location)}${o.contact ? ` · ${esc(o.contact)}` : ""}</p></div></div>
        <ul class="dn-claims">${o.claims.map((c) => `<li><div><b class="num">${fmt(c.portions)}</b> portions, pickup ${esc(c.pickup_at.replace("T", " "))}<small>asked ${esc(whenText(c.created_at))}</small></div>
          <div class="dn-claim-act">${pill(CLAIM_STATUS, c.status)}${["requested", "accepted"].includes(c.status) ? `<button class="btn btn-small btn-danger" type="button" data-claim="${o.id}|${c.id}|decline">${icon("close")}Withdraw</button>` : ""}</div></li>`).join("")}</ul></article>`).join("")
        : `<div class="glass-lite empty"><strong>No requests yet.</strong>Ask for food from an offer on the left.</div>`}
    </section></div>`;
}

function guestView(V) {
  const open = V.offers.filter((o) => o.status === "open");
  return `<div class="dn-grid ngo"><section class="ad-card glass dn-join"><h2>${icon("person")}Take part</h2>
      <p>Kitchens, hostels and messes: sign in to offer your surplus food. NGOs and help groups: create an account to ask for it; a kitchen approves new groups.</p>
      <div class="ad-actions"><a class="btn" href="#account">${icon("person")}Sign in or create an account</a></div>${DEMO_BUTTONS}</section>
    <section class="dn-list"><h2 class="dn-h">${icon("leaf")}Open offers</h2>${open.length ? open.map((o) => `<article class="dn-offer glass-lite">${offerHead(o)}${offerItems(o)}</article>`).join("")
      : `<div class="glass-lite empty"><strong>No food on offer right now.</strong></div>`}</section></div>`;
}

export function mountDonate(root) {
  root.innerHTML = SKELETON;
  const q = (s) => root.querySelector(s);
  const V = { offers: [], stats: null, rules: [], handover: 2, items: [], note: "", date: null, slot: "lunch", until: inHours(2), location: "",
    catalogue: [], ngos: [], types: {}, to: "", pendingNgos: 0, loaded: false };
  let lastVersion = -1, timer = null;

  async function load() {
    try {
      const r = await api.get("/donations");
      Object.assign(V, { offers: r.offers, stats: r.stats, rules: r.rules, handover: r.handover_hours, loaded: true });
      if (state.user?.role === "kitchen") {
        if (!V.catalogue.length) V.catalogue = (await api.get("/dishes")).dishes;
        const acc = await api.get("/accounts", { role: "ngo" }).catch(() => ({ accounts: [], ngo_types: {} }));
        V.ngos = acc.accounts;
        V.types = acc.ngo_types || {};
        V.pendingNgos = acc.accounts.filter((a) => a.status === "pending").length;
      }
    } catch (e) { setHTML(q("#dn-body"), `<div class="banner" style="width:auto">${esc(e.message)} ${esc(e.fix || "")}</div>`); return; }
    render();
  }

  function readForm() {   // keep what the kitchen typed before redrawing
    if (q("#dn-until")) V.until = q("#dn-until").value;
    if (q("#dn-loc")) V.location = q("#dn-loc").value;
    if (q("#dn-date")) V.date = q("#dn-date").value;
  }

  function render() {
    const s = state, st = V.stats;
    if (st) setHTML(q("#dn-stats"), [["leaf", fmt(st.portions_collected), "portions collected", "ok"], ["plans", fmt(st.portions_offered), "portions offered", ""],
      ["users", st.ngos_helped, `NGO${st.ngos_helped === 1 ? "" : "s"} helped`, ""], ["clock", st.open, `open offer${st.open === 1 ? "" : "s"}`, st.open ? "warn" : ""]]
      .map(([ic, n, l, tone]) => `<div class="pl-stat glass-lite ${tone}">${icon(ic)}<span class="pl-stat-n num">${n}</span><span class="pl-stat-l">${l}</span></div>`).join(""));
    setHTML(q("#dn-rules"), V.rules.length ? `<div class="pl-auto glass-lite">${icon("book")}<span><strong>From your documents:</strong> ${V.rules.map((r) => `${esc(r.label.toLowerCase())} ${r.value} ${esc(r.unit)}`).join("; ")}.</span><a class="btn btn-small" href="#docs">Documents</a></div>`
      : `<div class="pl-auto glass-lite">${icon("book")}<span>No hand over rule in the kitchen's documents yet, so offers can be collected for ${V.handover} hours. Upload the SOP on Documents to use your own rule.</span><a class="btn btn-small" href="#docs">Documents</a></div>`);
    readForm();
    const html = !s.user ? guestView(V) : s.user.role === "kitchen" ? kitchenView(s, V) : ngoView(s, V);
    if (setHTML(q("#dn-body"), html)) root.querySelectorAll(".seg").forEach(liquid);
  }

  root.addEventListener("click", async (e) => {
    const t = e.target;
    const demo = t.closest("[data-demo]");
    if (demo) { try { await demoSignIn(demo.dataset.demo); } catch (ex) { notify(`${ex.message} ${ex.fix || ""}`, "bad"); } return; }
    const pickNgo = t.closest("[data-to]");
    if (pickNgo) {
      readForm();
      V.to = V.to === pickNgo.dataset.to ? "" : pickNgo.dataset.to;
      render(); q("#dn-new-t")?.scrollIntoView({ behavior: "smooth", block: "start" }); return; }
    const slot = t.closest("[data-slot]");
    if (slot) { V.slot = slot.dataset.slot; render(); return; }
    const sug = t.closest("[data-suggest]");
    if (sug) {
      readForm();
      try {
        const r = await api.get("/donations/suggest", { date: V.date, slot: V.slot, source: sug.dataset.suggest });
        V.items = r.items.map((i) => ({ ...i }));
        V.note = r.note;
      } catch (ex) { V.note = `${ex.message} ${ex.fix || ""}`; }
      render();
      return;
    }
    const rm = t.closest("[data-rm-item]");
    if (rm) { V.items.splice(Number(rm.dataset.rmItem), 1); render(); return; }
    if (t.closest("#dn-add-btn")) {
      const id = q("#dn-add").value, d = V.catalogue.find((x) => x.dish_id === id);
      if (d && !V.items.some((i) => i.dish_id === id)) { V.items.push({ dish_id: id, dish_name: d.dish_name, portions: 50 }); render(); }
      return;
    }
    if (t.closest("#dn-post")) {
      readForm();
      try {
        const r = await api.post("/donations", { date: V.date, meal_slot: V.slot, items: V.items, pickup_until: V.until || null,
          location: V.location, notes: q("#dn-notes").value, to_ngo_id: V.to || null });
        notify(r.message, "ok");
        V.items = [];
        V.note = "";
        V.until = inHours(V.handover);
        V.to = "";
        await synced();
      } catch (ex) { notify(`${ex.message} ${ex.fix || ""}`, "bad"); }
      return;
    }
    const claim = t.closest("[data-claim]");
    if (claim) {
      const [oid, cid, action] = claim.dataset.claim.split("|");
      try { notify((await api.post(`/donations/${oid}/claims/${cid}`, { action })).message, action === "decline" ? "warn" : "ok"); await synced(); }
      catch (ex) { notify(`${ex.message} ${ex.fix || ""}`, "bad"); }
      return;
    }
    const cancel = t.closest("[data-cancel]");
    if (cancel && confirm("Cancel this offer? Open requests are declined.")) {
      try { notify((await api.post(`/donations/${cancel.dataset.cancel}/cancel`, {})).message, "warn"); await synced(); }
      catch (ex) { notify(`${ex.message} ${ex.fix || ""}`, "bad"); }
    }
  });
  root.addEventListener("input", (e) => { const n = e.target.dataset.item; if (n !== undefined) { V.items[Number(n)].portions = Math.max(0, Number(e.target.value) || 0); } });
  root.addEventListener("change", (e) => {
    if (e.target.id === "dn-to") V.to = e.target.value;   // the recipient changes only when someone picks one
    if (e.target.dataset.item !== undefined || e.target.id === "dn-to") { readForm(); render(); }
  });
  root.addEventListener("submit", async (e) => {
    const f = e.target.closest(".dn-claim-form");
    if (!f) return;
    e.preventDefault();
    const id = f.dataset.offer;
    try {
      const r = await api.post(`/donations/${id}/claim`, { portions: Number(q(`#dn-p-${id}`).value), pickup_at: q(`#dn-t-${id}`).value, note: q(`#dn-n-${id}`).value });
      notify(r.message, "ok");
      await synced();
    } catch (ex) { notify(`${ex.message} ${ex.fix || ""}`, "bad"); }
  });

  let shown = false, lastUser = null;
  window.addEventListener("ff:view", (e) => {
    clearInterval(timer);
    if (e.detail !== "donate") return;
    shown = true;
    load();
    timer = setInterval(() => { if (!document.hidden) load(); }, 20000);   // offers and requests move quickly
  });
  subscribe((s) => {
    if (s.donationPreset) {
      const p = s.donationPreset;
      s.donationPreset = null;
      Object.assign(V, { date: p.date, slot: p.slot, items: p.items.map((i) => ({ ...i })), note: p.note || "" });
      if (V.loaded) render();
    }
    if (!V.date && s.health) { V.date = s.health.today; V.until = inHours(V.handover); }
    if (s.user?.area && !V.location) V.location = s.user.area;
    const who = s.user ? `${s.user.id}|${s.user.status}` : "";
    if (!shown && location.hash.slice(1) === "donate") { shown = true; load(); }
    if (shown && (s.dataVersion !== lastVersion || who !== lastUser)) { lastVersion = s.dataVersion; lastUser = who; load(); }
  });
}
