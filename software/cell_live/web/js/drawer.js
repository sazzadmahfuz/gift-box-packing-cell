// Component drawer: every field of one component, its last checks and the raw reply.
import { getJSON, isStale, postJSON, serverNow, store } from "./api.js";
import { ago, badge, clock, h, ms, say, text } from "./ui.js";

let openId = null;
let opener = null; // the element that had focus before the drawer opened, so Close can give it back

function fieldRows(data) {
  return Object.entries(data || {})
    .filter(([key]) => key !== "raw")
    .map(([key, value]) => h("tr", {}, h("th", {}, key), h("td", { class: "mono" }, text(value))));
}

function rawBlock(detail) {
  const raw = detail.data && detail.data.raw;
  if (!raw) {
    const why = detail.kind === "file" ? "its check reads a file on this PC" : "no reply came back in the last check, or this check has no text protocol";
    return h("p", { class: "muted" }, `No raw reply (${why}).`);
  }
  return h("div", {}, ...Object.entries(raw).map(([command, reply]) =>
    h("div", { class: "raw" }, h("div", { class: "mono muted small" }, `sent: ${command}`), h("pre", { class: "mono" }, `reply: ${reply}`))));
}

// Redraw without losing the keyboard focus (the drawer refreshes itself every 3 s)
function redraw(host, detail) {
  const key = host.contains(document.activeElement) ? document.activeElement.dataset.key : null;
  draw(host, detail);
  if (key) host.querySelector(`[data-key="${key}"]`)?.focus();
}

function draw(host, detail) {
  const stale = isStale(detail);
  const close = h("button", { type: "button", class: "ghost", onclick: closeDrawer, title: "Close (Esc)", "data-key": "close" }, "Close");
  const check = h("button", {
    type: "button", class: "primary", "data-key": "check",
    onclick: async (event) => {
      event.target.disabled = true;
      try { redraw(host, await postJSON(`/api/components/${detail.id}/check`)); } catch (error) { say(`Check failed: ${error.message}`, "fail"); event.target.disabled = false; }
    },
  }, "Check now");
  const history = (detail.history || []).map((entry) => h("tr", {},
    h("td", { class: "num" }, clock(entry.checked_at)), h("td", {}, badge(entry.state)),
    h("td", { class: "num" }, ms(entry.latency_ms)), h("td", {}, entry.detail)));
  host.replaceChildren(
    h("div", { class: "screen-head" }, h("h1", {}, detail.name), h("span", { class: "spacer" }), check, close),
    h("div", { class: "drawer-state" }, badge(detail.state, stale, "big"), stale ? h("span", { class: "stale-note" }, "  stale: data is old") : null),
    h("p", {}, detail.detail),
    h("table", { class: "data" }, h("tbody", {},
      h("tr", {}, h("th", {}, "component id"), h("td", { class: "mono" }, detail.id)),
      h("tr", {}, h("th", {}, "kind"), h("td", {}, detail.kind === "file" ? "file on this PC" : "hardware")),
      h("tr", {}, h("th", {}, "checked"), h("td", { class: "num" }, `${clock(detail.checked_at)} (${ago(detail.checked_at ? serverNow() - detail.checked_at : null)})`)),
      h("tr", {}, h("th", {}, "last OK"), h("td", { class: "num" }, clock(detail.last_ok_at))),
      h("tr", {}, h("th", {}, "latency"), h("td", { class: "num" }, ms(detail.latency_ms))),
      h("tr", {}, h("th", {}, "check interval"), h("td", { class: "num" }, `${detail.interval_s} s`)),
      ...fieldRows(detail.data))),
    h("h2", {}, "Raw reply"),
    rawBlock(detail),
    h("h2", {}, `History (last ${(detail.history || []).length} checks, newest first)`),
    h("table", { class: "data" },
      h("thead", {}, h("tr", {}, h("th", {}, "time"), h("th", {}, "state"), h("th", {}, "latency"), h("th", {}, "detail"))),
      h("tbody", {}, history)));
}

export async function open(id) {
  const host = document.getElementById("drawer");
  if (openId === null) opener = document.activeElement;
  openId = id;
  host.classList.remove("hidden");
  host.replaceChildren(h("p", { class: "muted" }, "Loading…"));
  try {
    draw(host, await getJSON(`/api/components/${id}`));
    host.querySelector('[data-key="close"]')?.focus();
  } catch (error) {
    host.replaceChildren(h("p", { class: "result-fail" }, `Could not load ${id}: ${error.message}`), h("button", { onclick: closeDrawer }, "Close"));
  }
}

export function closeDrawer() {
  openId = null;
  document.getElementById("drawer").classList.add("hidden");
  if (opener && document.contains(opener)) opener.focus();
  opener = null;
}

document.addEventListener("keydown", (event) => { if (event.key === "Escape" && openId) closeDrawer(); });

// Keep the open drawer fresh when a new status for it arrives
setInterval(async () => {
  if (!openId || !store.components.has(openId)) return;
  try { redraw(document.getElementById("drawer"), await getJSON(`/api/components/${openId}`)); } catch (error) { /* keep the last view */ }
}, 3000);
