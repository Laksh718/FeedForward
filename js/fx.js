// Motion and surface helpers shared by every view: the liquid pill under segmented controls, the pointer glow on
// glass cards, numbers that roll to their new value, scroll reveals and toasts. All of it respects
// prefers-reduced-motion, and none of it changes what a control does.
import { fmt } from "./util.js";

const motionQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
export const reducedMotion = () => motionQuery.matches;

// Replace an element's markup only when it actually changed, so re-renders do not restart animations or
// throw away focus and scroll positions. Returns true when the markup was replaced.
export function setHTML(el, html) {
  if (el._ffHTML === html) return false;
  el.innerHTML = html;
  el._ffHTML = html;
  return true;
}

const ACTIVE = ':scope > [aria-pressed="true"], :scope > [aria-selected="true"], :scope > [aria-current="page"]';

// A pill that slides, with a little overshoot and squash, to whichever child is pressed, selected or current.
// Works for rows and columns, and survives the container's buttons being re-rendered.
export function liquid(container) {
  if (!container || container.classList.contains("has-thumb")) return;
  const thumb = document.createElement("span");
  thumb.className = "liquid-thumb";
  thumb.setAttribute("aria-hidden", "true");
  let at = null, squash;

  const place = () => {
    if (!container.contains(thumb)) container.prepend(thumb);
    const on = container.querySelector(ACTIVE);
    if (!on || !on.offsetWidth) { thumb.style.opacity = "0"; at = null; return; }
    const next = `${on.offsetLeft},${on.offsetTop},${on.offsetWidth},${on.offsetHeight}`;
    if (next === at) return;
    const first = at === null;
    thumb.classList.toggle("instant", first);
    if (!first && !reducedMotion()) {
      thumb.classList.add("moving");
      clearTimeout(squash);
      squash = setTimeout(() => thumb.classList.remove("moving"), 220);
    }
    Object.assign(thumb.style, { opacity: "1", width: `${on.offsetWidth}px`, height: `${on.offsetHeight}px`,
      transform: `translate(${on.offsetLeft}px, ${on.offsetTop}px)` });
    at = next;
    if (first) requestAnimationFrame(() => thumb.classList.remove("instant"));
  };

  container.classList.add("has-thumb");
  container.prepend(thumb);
  let frame = 0;
  const schedule = () => { cancelAnimationFrame(frame); frame = requestAnimationFrame(place); };
  new MutationObserver(schedule).observe(container, { subtree: true, childList: true, attributes: true,
    attributeFilter: ["aria-pressed", "aria-selected", "aria-current", "hidden"] });
  new ResizeObserver(schedule).observe(container);
  document.fonts?.ready.then(schedule);
  schedule();
}

// Glass cards with the class "glow" get a soft light that follows the pointer.
export function initGlow() {
  let frame = 0, last = null;
  document.addEventListener("pointermove", (e) => {
    last = e;
    if (frame) return;
    frame = requestAnimationFrame(() => {
      frame = 0;
      const el = last.target instanceof Element ? last.target.closest(".glow") : null;
      if (!el) return;
      const r = el.getBoundingClientRect();
      el.style.setProperty("--mx", `${last.clientX - r.left}px`);
      el.style.setProperty("--my", `${last.clientY - r.top}px`);
    });
  }, { passive: true });
}

// Roll a number from one value to another (ease out). Ends on exactly the formatted target.
export function rollNumber(el, from, to, ms = 650, format = fmt) {
  if (reducedMotion() || from === to || !Number.isFinite(from) || !Number.isFinite(to)) { el.textContent = format(to); return; }
  const t0 = performance.now();
  el.textContent = format(from);
  const step = (t) => {
    const k = Math.min(1, (t - t0) / ms);
    el.textContent = format(from + (to - from) * (1 - (1 - k) ** 3));
    if (k < 1 && el.isConnected) requestAnimationFrame(step);
    else el.textContent = format(to);
  };
  requestAnimationFrame(step);
}

// Elements with the class "reveal" fade and rise into place the first time they scroll into view.
export function reveal(root) {
  const els = root.querySelectorAll(".reveal:not(.in)");
  if (!("IntersectionObserver" in window) || reducedMotion()) { els.forEach((el) => el.classList.add("in")); return; }
  const io = new IntersectionObserver((entries) => {
    entries.forEach((e) => { if (e.isIntersecting) { e.target.classList.add("in"); io.unobserve(e.target); } });
  }, { threshold: 0.12, rootMargin: "0px 0px -6% 0px" });
  els.forEach((el) => io.observe(el));
}

// Short confirmations in a glass pill at the bottom of the screen. Decorative: every message is also written
// into the view's own status line, which is the live region screen readers hear.
export function toast(message, kind = "ok", ms = 3600) {
  const host = document.getElementById("toasts");
  if (!host || !message) return;
  const el = document.createElement("div");
  el.className = `toast ${kind}`;
  el.innerHTML = `<span class="toast-dot"></span><span class="toast-text"></span>`;
  el.querySelector(".toast-text").textContent = message;
  host.append(el);
  while (host.children.length > 3) host.firstElementChild.remove();
  setTimeout(() => {
    el.classList.add("out");
    setTimeout(() => el.remove(), reducedMotion() ? 0 : 320);
  }, ms);
}

// Restart a CSS entrance animation on an element by toggling a class.
export function replay(el, cls, ms = 900) {
  if (!el || reducedMotion()) return;
  el.classList.remove(cls);
  void el.offsetWidth;
  el.classList.add(cls);
  clearTimeout(el._ffReplay);
  el._ffReplay = setTimeout(() => el.classList.remove(cls), ms);
}
