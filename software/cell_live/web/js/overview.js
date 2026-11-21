// Overview: the cycle, the cell map, and the register with one row per component the backend reports.
// Rows are updated in place (never rebuilt), so keyboard focus and the pulses survive the 1 s refresh.
import { isStale, loadComponents, onChange, postJSON, serverNow, store } from "./api.js";
import { cycleStrip } from "./cycle.js";
import { sparkInto } from "./fx.js";
import { mountMap } from "./patchbay.js";
import { ago, badge, h, ms, say } from "./ui.js";

function registerRow(component, onOpen) {
  const state = h("td", { class: "c-state" });
  const detailText = h("div", { class: "clamp" });
  const detail = h("td", { class: "c-detail" }, detailText);
  const latency = h("span", { class: "num" });
  const bars = h("span", { class: "spark", "aria-hidden": "true" });
  const seen = h("td", { class: "c-seen num" });
  const check = h("button", { type: "button", title: `Check ${component.name} now` }, "Check");
  const el = h("tr", { class: "reg-row", tabindex: 0, "data-id": component.id, title: "Click for every field, the history and the raw reply" },
    state,
    h("td", { class: "c-name" }, h("strong", {}, component.name), " ",
      h("span", { class: "tag", title: component.kind === "file" ? "A file on this PC, not a device" : "A device of the cell" }, component.kind === "file" ? "file" : "hardware")),
    detail, h("td", { class: "c-lat" }, latency, bars), seen, h("td", { class: "c-act" }, check));
  el.addEventListener("click", () => onOpen(component.id));
  el.addEventListener("keydown", (event) => { if (event.key === "Enter" && event.target === el) onOpen(component.id); });
  check.addEventListener("click", async (event) => {
    event.stopPropagation();
    check.disabled = true;
    try { await postJSON(`/api/components/${component.id}/check`); } catch (error) { say(`Check failed: ${error.message}`, "fail"); }
    check.disabled = false;
  });
  let shown = "";
  function update(next) {
    const stale = isStale(next);
    el.className = `reg-row st-${next.state}${stale ? " stale" : ""}`;
    if (shown !== `${next.state}|${stale}`) { state.replaceChildren(badge(next.state, stale)); shown = `${next.state}|${stale}`; }
    if (detailText.textContent !== next.detail) detailText.textContent = next.detail;
    latency.textContent = next.latency_ms === null || next.latency_ms === undefined ? "no reply" : ms(next.latency_ms);
    sparkInto(bars, store.latency.get(next.id) || []);
    seen.textContent = ago(next.checked_at ? serverNow() - next.checked_at : null);
  }
  update(component);
  return { el, update };
}

export function render(root) {
  const openDrawer = (id) => import("./drawer.js").then((drawer) => drawer.open(id));
  const strip = cycleStrip({ compact: true });
  const mapHost = h("div");
  const body = h("tbody");
  const rows = new Map();
  const unconfirmed = h("span", { class: "muted" });
  const allButton = h("button", { type: "button", class: "primary" }, "Check all");
  allButton.addEventListener("click", async () => {
    allButton.disabled = true;
    for (const id of store.components.keys()) {
      try { await postJSON(`/api/components/${id}/check`); } catch (error) { say(`Check ${id} failed: ${error.message}`, "fail"); }
    }
    allButton.disabled = false;
  });
  root.append(
    h("div", { class: "screen-head" }, h("h1", {}, "Overview"), unconfirmed, h("span", { class: "spacer" }), allButton),
    strip.el,
    h("section", { class: "map-plate on-ink", "aria-label": "Cell map" },
      h("div", { class: "map-title" }, h("h2", {}, "Cell map"),
        h("span", { class: "small muted" }, "Each cable is one check. A pulse runs along it when that check finishes. Dashed or dotted: failed, not observable or old. Plain grey: wired, not checked.")),
      mapHost),
    h("section", { class: "register panel", "aria-label": "Components" },
      h("table", { class: "data" },
        h("thead", {}, h("tr", {}, ...["state", "component", "what the last check saw", "latency", "checked", ""].map((title) => h("th", {}, title)))), body)));
  const map = mountMap(mapHost, openDrawer);

  function sync() {
    for (const component of store.components.values()) {
      let row = rows.get(component.id);
      if (!row) { row = registerRow(component, openDrawer); rows.set(component.id, row); body.append(row.el); }
      row.update(component);
    }
    if (!store.components.size && !body.children.length) body.append(h("tr", {}, h("td", { colspan: 6, class: "muted" }, "Waiting for the backend's component list.")));
    unconfirmed.textContent = store.unconfirmed.length ? `${store.unconfirmed.length} config values still CONFIRM (see Settings)` : "";
    strip.update();
  }

  sync();
  loadComponents().catch(() => {});
  const stop = onChange((what) => { if (["components", "connection", "run", "tick"].includes(what)) sync(); });
  const timer = setInterval(sync, 1000); // "x s ago" and the stale state move on by themselves
  return () => { stop(); map.destroy(); clearInterval(timer); };
}
