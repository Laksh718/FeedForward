// View: Documents. The kitchen's own SOPs, food safety rules, donation policies and menus. Upload a PDF, Word, text,
// Markdown or CSV file; FeedForward cuts it into passages and finds the ones that match a question (retrieval
// augmented generation). The copilot quotes them next to the forecast, the Donations view takes the hand over time
// from them, and the rules found are listed here with the sentence they came from.
import { api, auth } from "./api.js";
import { setHTML } from "./fx.js";
import { icon } from "./icons.js";
import { notify, state, subscribe } from "./state.js";
import { esc, whenText } from "./util.js";

const CATEGORY = { sop: "Standard operating procedure", food_safety: "Food safety", donation: "Donation policy", menu: "Menu or recipes", other: "Other" };
const TRY = ["How long can surplus food be kept before it is donated?", "At what temperature must hot food be held?", "What changes during exam week?"];
const USES = {
  handover_hours: "Donations: the default collection deadline of a new offer.",
  hot_holding_c: "Donations: shown to NGOs with every offer.",
  cold_holding_c: "Donations: shown to NGOs with every offer.",
  min_donation_portions: "Donations: shown when a kitchen posts a smaller offer.",
  safety_margin_pct: "Shown here for the kitchen to compare with the recommendation's own safety margin.",
};

const SKELETON = `
  <header class="dc-top"><p class="eyebrow">${icon("book")}Documents</p><h1 class="dc-title">Your kitchen's rules, taken into account</h1>
    <p class="dc-sub">Upload SOPs, food safety rules, donation policies or anything else that decides how food is planned and given away.
      The copilot quotes the matching passages with its answers, the Donations view takes the hand over time from them, and you can ask them questions here.</p></header>
  <div class="dc-grid">
    <div class="dc-main">
      <section class="ad-card glass" aria-labelledby="dc-ask-t"><h2 id="dc-ask-t">${icon("search")}Ask your documents</h2>
        <form class="co-form dc-form" id="dc-ask"><label class="sr-only" for="dc-q">Question</label><input id="dc-q" maxlength="500" autocomplete="off" placeholder="How long can cooked food wait before it is donated?">
          <button class="btn btn-primary" type="submit">${icon("send")}Ask</button></form>
        <div class="co-chips dc-try">${TRY.map((t) => `<button type="button" class="co-chip">${t}</button>`).join("")}</div>
        <div id="dc-answer" aria-live="polite"></div></section>
      <section class="ad-card glass" aria-labelledby="dc-lib-t"><h2 id="dc-lib-t">${icon("list")}Library</h2><div id="dc-lib"></div></section>
    </div>
    <aside class="dc-side">
      <section class="ad-card glass" aria-labelledby="dc-up-t"><h2 id="dc-up-t">${icon("plans")}Add a document</h2><div id="dc-up"></div></section>
      <section class="ad-card glass" aria-labelledby="dc-rules-t"><h2 id="dc-rules-t">${icon("shield")}Rules found</h2><div id="dc-rules"></div></section>
    </aside>
  </div>`;

const UPLOAD = `<label class="dc-drop" id="dc-drop" for="dc-file">${icon("plans")}<strong>Drop a file here or choose one</strong>
    <small>PDF, Word (.docx), text, Markdown or CSV, up to 12 MB</small><input id="dc-file" type="file" accept=".pdf,.docx,.txt,.md,.csv" class="sr-only"></label>
  <p class="dc-file" id="dc-file-name"></p>
  <div class="ad-field"><label for="dc-title">Title (optional)</label><input id="dc-title" maxlength="160" placeholder="Hostel kitchen SOP, 2026"></div>
  <div class="ad-field"><label for="dc-cat">Kind</label><select id="dc-cat">${Object.entries(CATEGORY).map(([k, v]) => `<option value="${k}">${v}</option>`).join("")}</select></div>
  <button class="btn btn-primary" type="button" id="dc-go" disabled>${icon("check")}Upload and read it</button><div id="dc-up-msg" aria-live="polite"></div>`;

const LOCKED = `<p class="ad-help">Sign in with a kitchen account (or unlock the Daily log with the PIN) to add or remove documents. Anyone can ask them questions.</p>
  <a class="btn btn-primary" href="#account">${icon("person")}Sign in</a>`;

const toBase64 = (file) => new Promise((resolve, reject) => {
  const r = new FileReader();
  r.onload = () => resolve(String(r.result).split(",")[1] ?? "");
  r.onerror = () => reject(new Error("The file could not be read in the browser."));
  r.readAsDataURL(file);
});

export function mountDocs(root) {
  root.innerHTML = SKELETON;
  const q = (s) => root.querySelector(s);
  const V = { docs: [], rules: [], file: null, loaded: false };
  const canEdit = () => state.user?.role === "kitchen" || Boolean(auth.pin);

  async function load() {
    try {
      const r = await api.get("/knowledge");
      Object.assign(V, { docs: r.documents, rules: r.rules, loaded: true });
    } catch (e) { setHTML(q("#dc-lib"), `<div class="ad-msg bad">${esc(e.message)} ${esc(e.fix || "")}</div>`); return; }
    render();
  }

  function render() {
    const up = q("#dc-up"), mode = canEdit() ? "edit" : "locked";
    if (up.dataset.mode !== mode) { up.innerHTML = mode === "edit" ? UPLOAD : LOCKED; up.dataset.mode = mode; V.file = null; }   // keep a chosen file
    setHTML(q("#dc-lib"), V.docs.length ? `<ul class="dc-list">${V.docs.map((d) => `<li class="glass-lite"><span class="dc-ic">${icon("book")}</span>
      <span class="dc-what"><strong>${esc(d.title)}</strong><small>${esc(CATEGORY[d.category] || d.category)} · ${d.pages} page${d.pages === 1 ? "" : "s"}, ${d.passages} passages, ${d.words.toLocaleString()} words
      · added ${esc(whenText(d.uploaded_at))}${d.uploaded_by ? ` by ${esc(d.uploaded_by)}` : ""}</small></span>
      ${canEdit() ? `<button class="btn btn-small btn-danger" type="button" data-del="${d.id}" aria-label="Remove ${esc(d.title)}">${icon("trash")}</button>` : ""}</li>`).join("")}</ul>`
      : `<p class="ad-help">No documents yet. Add the kitchen's SOP or food safety rules, and the copilot starts quoting them.</p>`);
    setHTML(q("#dc-rules"), V.rules.length ? `<ul class="dc-rules">${V.rules.map((r) => `<li><span class="dc-rule-v num">${r.value} ${esc(r.unit)}</span>
      <strong>${esc(r.label)} ${r.value} ${esc(r.unit)}</strong><small>“…${esc(r.quote)}…” (${esc(r.source)}, page ${r.page})</small>
      <em>${esc(USES[r.key] || "")}</em></li>`).join("")}</ul>`
      : `<p class="ad-help">No rules found yet. FeedForward looks for hand over times for surplus food, hot and cold holding temperatures, safety margins and the smallest donation worth arranging.</p>`);
  }

  async function ask(question) {
    const text = question.trim();
    if (!text) return;
    setHTML(q("#dc-answer"), `<p class="typing-line"><span class="dots"><i></i><i></i><i></i></span>Reading the documents</p>`);
    try {
      const r = await api.post("/knowledge/ask", { question: text });
      setHTML(q("#dc-answer"), `<div class="answer"><p class="q">${esc(text)}</p><p class="a">${esc(r.answer)}</p>
        <p class="src">${r.source === "llm" ? "Written by the language model from the passages below only." : "The best matching passage, quoted as written."}</p></div>
        ${r.passages.length ? `<p class="co-group">Passages used</p><ol class="dc-passages">${r.passages.map((p) => `<li><p>${esc(p.text)}</p><small>${esc(p.title)}, page ${p.page} · match ${Math.round(p.score * 100)}%</small></li>`).join("")}</ol>` : ""}`);
    } catch (e) { setHTML(q("#dc-answer"), `<div class="ad-msg bad">${esc(e.message)} ${esc(e.fix || "")}</div>`); }
  }

  q("#dc-ask").addEventListener("submit", (e) => { e.preventDefault(); ask(q("#dc-q").value); });
  root.querySelectorAll(".dc-try .co-chip").forEach((b) => b.addEventListener("click", () => { q("#dc-q").value = b.textContent; ask(b.textContent); }));
  const pick = (file) => {
    V.file = file || null;
    const name = q("#dc-file-name"), go = q("#dc-go");
    if (name) name.textContent = file ? `${file.name} (${Math.ceil(file.size / 1024)} KB)` : "";
    if (go) go.disabled = !file;
  };
  root.addEventListener("change", (e) => { if (e.target.id === "dc-file") pick(e.target.files[0]); });
  root.addEventListener("dragover", (e) => { if (e.target.closest("#dc-drop")) { e.preventDefault(); q("#dc-drop").classList.add("over"); } });
  root.addEventListener("dragleave", (e) => { if (e.target.closest("#dc-drop")) q("#dc-drop").classList.remove("over"); });
  root.addEventListener("drop", (e) => { if (e.target.closest("#dc-drop")) { e.preventDefault(); q("#dc-drop").classList.remove("over"); pick(e.dataTransfer.files[0]); } });
  root.addEventListener("click", async (e) => {
    if (e.target.closest("#dc-go") && V.file) {
      const box = q("#dc-up-msg");
      box.innerHTML = `<div class="ad-msg">Reading ${esc(V.file.name)}&hellip;</div>`;
      try {
        const r = await api.post("/knowledge/upload", { filename: V.file.name, content_base64: await toBase64(V.file),
          title: q("#dc-title").value.trim(), category: q("#dc-cat").value });
        box.innerHTML = `<div class="ad-msg ok">${esc(r.message)}</div>`;
        notify(r.message, "ok");
        q("#dc-title").value = "";
        q("#dc-file").value = "";
        pick(null);
        load();
      } catch (ex) { box.innerHTML = `<div class="ad-msg bad">${esc(ex.message)} ${esc(ex.fix || "")}</div>`; }
    }
    const del = e.target.closest("[data-del]");
    if (del && confirm("Remove this document? The copilot and the rules stop using it.")) {
      try { notify((await api.del(`/knowledge/${del.dataset.del}`, {})).message, "ok"); load(); } catch (ex) { notify(`${ex.message} ${ex.fix || ""}`, "bad"); }
    }
  });

  let lastUser = "";
  window.addEventListener("ff:view", (e) => { if (e.detail === "docs") load(); });
  subscribe((s) => {
    const who = `${s.user?.id ?? ""}|${auth.pin ? "pin" : ""}`;
    if (who !== lastUser) { lastUser = who; if (V.loaded) render(); }
    if (!V.loaded && location.hash.slice(1) === "docs") load();
  });
}
