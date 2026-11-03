// The FeedForward mark: a bowl with a rising forecast line that ends in an arrow, on a glassy green tile.
// Each copy gets its own gradient ids, so several marks (top bar, landing, desk rail) can share a page.
let uid = 0;

export function logoMark({ size = 32, label = "", className = "" } = {}) {
  const id = `ffmark${uid++}`;
  const a11y = label ? `role="img" aria-label="${label}"` : `aria-hidden="true"`;
  return `<svg class="logo-mark ${className}" viewBox="0 0 64 64" width="${size}" height="${size}" ${a11y} focusable="false">
    <defs>
      <linearGradient id="${id}-fill" x1="6" y1="4" x2="58" y2="62" gradientUnits="userSpaceOnUse">
        <stop stop-color="#34D399"/><stop offset=".5" stop-color="#11946A"/><stop offset="1" stop-color="#0F766E"/>
      </linearGradient>
      <linearGradient id="${id}-shine" x1="32" y1="2" x2="32" y2="38" gradientUnits="userSpaceOnUse">
        <stop stop-color="#fff" stop-opacity=".55"/><stop offset="1" stop-color="#fff" stop-opacity="0"/>
      </linearGradient>
    </defs>
    <rect x="2" y="2" width="60" height="60" rx="18" fill="url(#${id}-fill)"/>
    <rect x="2" y="2" width="60" height="60" rx="18" fill="url(#${id}-shine)"/>
    <rect x="2.75" y="2.75" width="58.5" height="58.5" rx="17.25" fill="none" stroke="#fff" stroke-opacity=".4" stroke-width="1.5"/>
    <path class="logo-trend" d="M16 29l8-8 6 6 13-13" pathLength="1" fill="none" stroke="#fff" stroke-width="4.5" stroke-linecap="round" stroke-linejoin="round"/>
    <path class="logo-arrow" d="M35 14h8v8" fill="none" stroke="#fff" stroke-width="4.5" stroke-linecap="round" stroke-linejoin="round"/>
    <path class="logo-bowl" d="M12 36h40a20 20 0 0 1-40 0z" fill="#fff"/>
  </svg>`;
}
