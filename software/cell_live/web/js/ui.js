// Small helpers: DOM building, status lamps (shape + word + colour), formatting, the toast and the confirm dialog.
// Nothing here computes anything about the hardware: it only shows what the backend sent.

export const STATES = {
  OK: { shape: "●", word: "OK" },
  WARN: { shape: "▲", word: "WARN" },
  FAIL: { shape: "✖", word: "FAIL" },
  UNKNOWN: { shape: "?", word: "UNKNOWN" },
  NOT_OBSERVABLE: { shape: "⊘", word: "NOT OBSERVABLE" },
};

export function h(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs || {})) {
    if (value === undefined || value === null || value === false) continue;
    if (key === "class") node.className = value;
    else if (key.startsWith("on") && typeof value === "function") node.addEventListener(key.slice(2), value);
    else if (value === true) node.setAttribute(key, "");
    else node.setAttribute(key, String(value));
  }
  for (const child of children.flat()) {
    if (child === undefined || child === null || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

const known = (state) => (STATES[state] ? state : "UNKNOWN");

// The lamp is drawn in CSS (status.css): disc, triangle, cross, ring, slashed ring. "old" = dashed ring.
export function lamp(state, { stale = false, size = "" } = {}) {
  return h("span", { class: `lamp${stale ? " old" : ""}${size ? ` ${size}` : ""}`, "data-state": known(state), "aria-hidden": "true" });
}

export function setLamp(node, state, stale = false) {
  node.dataset.state = known(state);
  node.classList.toggle("old", stale);
}

export function badge(state, stale = false, size = "") {
  const key = known(state);
  const meta = STATES[key];
  return h("span", { class: `status st-${key}${stale ? " stale" : ""}`, title: stale ? "old data (stale)" : `${meta.shape} ${meta.word}` },
    lamp(key, { stale, size }), meta.word);
}

export function ago(seconds) {
  if (seconds === null || seconds === undefined || Number.isNaN(seconds)) return "never";
  if (seconds < 1) return "just now";
  if (seconds < 60) return `${Math.round(seconds)} s ago`;
  if (seconds < 3600) return `${Math.round(seconds / 60)} min ago`;
  return `${(seconds / 3600).toFixed(1)} h ago`;
}

export function ms(value) {
  return value === null || value === undefined ? "unknown" : `${Number(value).toFixed(value < 10 ? 1 : 0)} ms`;
}

export function seconds(value, digits = 1) {
  return value === null || value === undefined ? "unknown" : `${Number(value).toFixed(digits)} s`;
}

export function clock(epochSeconds) {
  if (!epochSeconds) return "never";
  return new Date(epochSeconds * 1000).toLocaleTimeString([], { hour12: false });
}

export function text(value) {
  if (value === null || value === undefined || value === "") return "unknown";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

export function clear(node) {
  while (node.firstChild) node.removeChild(node.firstChild);
  return node;
}

// Toast at the bottom right (does not push the page down). timeoutMs 0 keeps it until the next message.
export function say(message, kind = "info", timeoutMs = 6000) {
  const toast = document.getElementById("message");
  toast.className = `toast toast-${kind}`;
  toast.textContent = message;
  clearTimeout(say.timer);
  if (timeoutMs) say.timer = setTimeout(() => toast.classList.add("hidden"), timeoutMs);
}

// Asks before something that cannot be undone. Resolves true (OK) or false (Cancel or Esc).
export function confirmDialog({ title, body, ok = "OK", danger = false }) {
  return new Promise((resolve) => {
    const cancel = h("button", { type: "button" }, "Cancel");
    const yes = h("button", { type: "button", class: danger ? "danger" : "primary" }, ok);
    const dialog = h("dialog", { class: "dlg", "aria-labelledby": "dlg-title" },
      h("h2", { id: "dlg-title" }, title), h("p", {}, body), h("div", { class: "dlg-actions" }, cancel, yes));
    const done = (answer) => { dialog.close(); dialog.remove(); resolve(answer); };
    cancel.addEventListener("click", () => done(false));
    yes.addEventListener("click", () => done(true));
    dialog.addEventListener("cancel", (event) => { event.preventDefault(); done(false); });
    document.body.append(dialog);
    dialog.showModal();
    cancel.focus();
  });
}
