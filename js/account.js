// View: Account. Sign in, or create an account for a kitchen (a mess, hostel or kitchen: needs the invite code from
// the kitchen's administrator) or for an NGO or help group (starts waiting until a kitchen approves it). Signed in,
// it shows the profile; a kitchen also approves or switches off NGO accounts here.
import { api } from "./api.js";
import { liquid, setHTML } from "./fx.js";
import { icon } from "./icons.js";
import { demoSignIn, notify, refreshUser, register, signIn, signOut, state, subscribe } from "./state.js";
import { esc, whenText } from "./util.js";

const ROLE = { kitchen: "Kitchen, hostel or mess", ngo: "NGO or help group" };
const NGO_TYPES = { food_bank: "Food bank", shelter: "Night shelter", children: "Children's home", elders: "Home for the elderly",
  community_kitchen: "Community kitchen", relief: "Relief group", other: "Other help group" };
const STATUS = { active: ["approve", "Active"], pending: ["pending", "Waiting for a kitchen to approve"], disabled: ["send_back", "Switched off"] };

const SKELETON = `
  <header class="ac-top"><p class="eyebrow">${icon("person")}Account</p><h1 class="ac-title" id="ac-title">Sign in</h1>
    <p class="ac-sub">Kitchens plan meals and offer their surplus food. NGOs and help groups see the offers and collect the food.
      Everything else in FeedForward can be used without an account.</p></header>
  <div id="ac-body"></div>`;

const field = (id, label, type = "text", extra = "") => `<div class="ad-field"><label for="${id}">${label}</label><input id="${id}" type="${type}" ${extra}></div>`;

export const DEMO_BUTTONS = `<div class="ac-demo"><p class="ac-demo-t">${icon("spark")}Just looking around? Try it with a demo account, no sign up:</p>
  <div class="ac-demo-row"><button class="btn btn-primary" type="button" data-demo="kitchen">${icon("service")}Try as a demo kitchen</button>
  <button class="btn" type="button" data-demo="ngo">${icon("users")}Try as a demo NGO</button></div></div>`;

function signedOut(mode, role, demo) {
  return `${demo ? `<section class="ad-card glass ac-demo-card">${DEMO_BUTTONS}</section>` : ""}<div class="ac-grid">
    <section class="ad-card glass ac-card" aria-labelledby="ac-in-t">
      <div class="seg ac-mode" role="group" aria-label="Sign in or create an account">
        <button type="button" data-mode="in" aria-pressed="${mode === "in"}">Sign in</button><button type="button" data-mode="up" aria-pressed="${mode === "up"}">Create an account</button></div>
      ${mode === "in" ? `<form id="ac-in" class="ac-form"><h2 id="ac-in-t">Welcome back</h2>
        ${field("ac-email", "Email", "email", 'autocomplete="email" required')}${field("ac-pass", "Password", "password", 'autocomplete="current-password" required')}
        <button class="btn btn-primary" type="submit">${icon("arrow")}Sign in</button></form>`
    : `<form id="ac-up" class="ac-form"><h2 id="ac-in-t">Create an account</h2>
        <div class="ac-roles" role="radiogroup" aria-label="Account type">${Object.entries(ROLE).map(([k, t]) => `<label class="ev-option ${role === k ? "on" : ""}">
          <input type="radio" name="ac-role" value="${k}" ${role === k ? "checked" : ""}><span><strong>${t}</strong><small>${k === "kitchen"
            ? "Plans meals, approves NGOs, uploads SOPs and offers surplus food. Needs the invite code."
            : "Sees surplus food offers near you and asks to collect them, once a kitchen has approved you."}</small></span></label>`).join("")}</div>
        <div class="ad-grid">${field("ac-org", role === "kitchen" ? "Kitchen, hostel or mess name" : "Organisation name", "text", "required maxlength=120")}
          ${field("ac-name", "Your name", "text", "required maxlength=80")}${field("ac-email", "Email", "email", 'autocomplete="email" required')}
          ${field("ac-pass", "Password (at least 8 characters)", "password", 'autocomplete="new-password" minlength="8" required')}
          ${field("ac-phone", "Phone (shown to the other side of a donation)", "tel", "maxlength=40")}${field("ac-area", "Area or address", "text", "maxlength=120")}
          ${role === "kitchen" ? field("ac-code", "Invite code", "password", "required") : field("ac-cap", "Portions you can take at a time", "number", 'min="1" max="50000"')}
          ${role === "ngo" ? `<div class="ad-field"><label for="ac-type">Type of group</label><select id="ac-type">${Object.entries(NGO_TYPES).map(([k, v]) => `<option value="${k}">${v}</option>`).join("")}</select></div>` : ""}</div>
        <button class="btn btn-primary" type="submit">${icon("check")}Create the account</button></form>`}
      <div id="ac-msg" aria-live="polite"></div>
    </section>
    <aside class="ad-card glass ac-card ac-why"><h2>${icon("shield")}How accounts work</h2><ul>
      <li><strong>Kitchens</strong> (a mess, a hostel, a central kitchen) need the invite code, the same code as the Daily log PIN, so strangers cannot sign up as a kitchen. A kitchen account opens the Daily log without the PIN.</li>
      <li><strong>NGOs and help groups</strong> can register any time. A kitchen approves the account before it can ask for food, so food only goes to groups someone has checked.</li>
      <li>Passwords are stored only as salted hashes. You stay signed in on this browser for 14 days, or until you sign out.</li></ul></aside></div>`;
}

function profile(u, ngos) {
  const [tone, label] = STATUS[u.status];
  const approvals = u.role === "kitchen" ? `<section class="ad-card glass" aria-labelledby="ac-ngo-t"><h2 id="ac-ngo-t">${icon("users")}NGOs and help groups</h2>
    <p class="ad-help">Approve a group before it can ask for food. Switch one off and it can no longer sign in.</p>
    ${ngos.length ? `<div class="ad-tablewrap"><table><thead><tr><th>Organisation</th><th>Contact</th><th>Area</th><th>Can take</th><th>Joined</th><th>Status</th><th><span class="sr-only">Actions</span></th></tr></thead><tbody>${ngos.map((n) => {
      const [t, l] = STATUS[n.status];
      return `<tr><td>${esc(n.org_name)}<br><small>${esc(NGO_TYPES[n.ngo_type] || "Help group")}</small></td><td>${esc(n.name)}<br><small>${esc(n.email)}${n.phone ? `, ${esc(n.phone)}` : ""}</small></td><td>${esc(n.area || "")}</td>
        <td>${n.capacity ? `${n.capacity} portions` : ""}</td><td>${esc(whenText(n.created_at))}</td><td><span class="status-pill ${t}">${l}</span></td>
        <td>${n.status !== "active" ? `<button class="btn btn-small btn-primary" type="button" data-ngo="${n.id}" data-to="active">${icon("check")}Approve</button>` : ""}
          ${n.status !== "disabled" ? `<button class="btn btn-small btn-danger" type="button" data-ngo="${n.id}" data-to="disabled">${icon("close")}Switch off</button>` : ""}</td></tr>`;
    }).join("")}</tbody></table></div>` : `<p class="ad-help">No NGO has registered yet. Share this site with the groups you work with: they create an account here.</p>`}</section>` : "";
  return `${u.demo ? `<div class="ad-note">${icon("spark")} This is the shared demo ${u.role === "kitchen" ? "kitchen" : "NGO"} account: anyone can sign in to it, so do not put real data here.</div>` : ""}
    <section class="ad-card glass ac-profile"><div class="ac-avatar">${esc(u.org_name.slice(0, 1).toUpperCase())}</div>
      <div><h2>${esc(u.org_name)}</h2><p>${esc(u.name)} · ${esc(u.email)}${u.phone ? ` · ${esc(u.phone)}` : ""}</p>
        <p class="ac-tags"><span class="pl-chip">${ROLE[u.role]}</span><span class="status-pill ${tone}">${label}</span>${u.area ? `<span class="pl-chip">${esc(u.area)}</span>` : ""}</p></div>
      <div class="ac-actions"><a class="btn btn-primary" href="#donate">${icon("leaf")}${u.role === "kitchen" ? "Offer surplus food" : "See food offers"}</a>
        ${u.role === "kitchen" ? `<a class="btn" href="#docs">${icon("book")}Documents</a><a class="btn" href="#admin">${icon("log")}Daily log</a>` : ""}
        <button class="btn" type="button" id="ac-out">${icon("back")}Sign out</button></div></section>
    ${u.status === "pending" ? `<div class="ad-note">${icon("clock")} A kitchen has not approved this account yet. You can already see the food offers; you can ask for food once you are approved.</div>` : ""}
    ${approvals}`;
}

export function mountAccount(root) {
  root.innerHTML = SKELETON;
  const q = (s) => root.querySelector(s);
  const V = { mode: "in", role: "ngo", ngos: [], loadedFor: null, demo: true };
  api.get("/auth/options").then((o) => { V.demo = o.demo; shownFor = ""; render(state); }).catch(() => {});
  const msg = (html, kind) => { const m = q("#ac-msg"); if (m) m.innerHTML = html ? `<div class="ad-msg ${kind}">${html}</div>` : ""; };
  const err = (e) => msg(`${esc(e.message)} ${esc(e.fix || "")}`, "bad");

  async function loadNgos() {
    try { V.ngos = (await api.get("/accounts", { role: "ngo" })).accounts; } catch { V.ngos = []; }
    render(state);
  }

  root.addEventListener("click", async (e) => {
    const m = e.target.closest("[data-mode]");
    if (m) { V.mode = m.dataset.mode; render(state); return; }
    if (e.target.closest("#ac-out")) { await signOut(); return; }
    const d = e.target.closest("[data-demo]");
    if (d) {
      try { await demoSignIn(d.dataset.demo); location.hash = d.dataset.demo === "kitchen" ? "plans" : "donate"; } catch (ex) { err(ex); notify(`${ex.message} ${ex.fix || ""}`, "bad"); }
      return;
    }
    const b = e.target.closest("[data-ngo]");
    if (b) {
      try {
        const r = await api.post(`/accounts/${b.dataset.ngo}/status`, { status: b.dataset.to });
        notify(r.message, b.dataset.to === "active" ? "ok" : "warn");
        loadNgos();
      } catch (ex) { notify(`${ex.message} ${ex.fix || ""}`, "bad"); }
    }
  });
  root.addEventListener("change", (e) => { if (e.target.name === "ac-role") { V.role = e.target.value; render(state); } });
  root.addEventListener("submit", async (e) => {
    e.preventDefault();
    const val = (id) => q(id)?.value.trim() ?? "";
    try {
      if (e.target.id === "ac-in") await signIn(val("#ac-email"), q("#ac-pass").value);
      else {
        await register({ role: V.role, org_name: val("#ac-org"), name: val("#ac-name"), email: val("#ac-email"), password: q("#ac-pass").value,
          phone: val("#ac-phone"), area: val("#ac-area"), invite_code: V.role === "kitchen" ? val("#ac-code") : null,
          capacity: V.role === "ngo" && val("#ac-cap") ? Number(val("#ac-cap")) : null, ngo_type: V.role === "ngo" ? val("#ac-type") : null });
      }
    } catch (ex) { err(ex); }
  });

  let shownFor = "";
  function render(s) {
    const u = s.user;
    q("#ac-title").textContent = u ? "Your account" : V.mode === "in" ? "Sign in" : "Create an account";
    const key = u ? `${u.id}|${u.status}|${V.ngos.map((n) => n.id + n.status).join()}` : `out|${V.mode}|${V.role}|${V.demo}`;
    if (key === shownFor) return;
    shownFor = key;
    setHTML(q("#ac-body"), u ? profile(u, V.ngos) : signedOut(V.mode, V.role, V.demo));
    root.querySelectorAll(".seg").forEach(liquid);
    if (u?.role === "kitchen" && V.loadedFor !== u.id) { V.loadedFor = u.id; loadNgos(); }
  }
  window.addEventListener("ff:view", (e) => { if (e.detail === "account") refreshUser(); });
  subscribe(render);
}
