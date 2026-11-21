// Projector view (#/show, open with ?viewer=1): the cell's state and the camera side by side, in large type.
// Read-only: no Check, Arm or Start here. The SOFTWARE STOP stays in the top bar.
import { getJSON, isStale, onChange, store } from "./api.js";
import { cycleStrip } from "./cycle.js";
import { badge, h } from "./ui.js";
import { cameraPanel } from "./vision.js";

export function render(root) {
  const strip = cycleStrip({ large: true });
  const list = h("ul", { class: "show-list" });
  const rows = new Map();
  const camera = cameraPanel();
  root.append(h("div", { class: "show" },
    h("section", { class: "show-left" }, strip.el, list),
    h("section", { class: "show-right" }, camera.picture, camera.note, h("div", { class: "panel show-counts" }, camera.counts, camera.ready, camera.cell))));

  function draw() {
    strip.update();
    for (const component of store.components.values()) {
      let row = rows.get(component.id);
      if (!row) {
        row = { state: h("span", { class: "show-state" }), el: null };
        row.el = h("li", { class: "show-row", title: component.detail }, row.state, h("span", { class: "show-name" }, component.name));
        rows.set(component.id, row);
        list.append(row.el);
      }
      const stale = isStale(component);
      const key = `${component.state}|${stale}`;
      row.el.className = `show-row st-${component.state}${stale ? " stale" : ""}`;
      if (row.key !== key) { row.state.replaceChildren(badge(component.state, stale, "big")); row.key = key; }
      row.el.title = component.detail;
    }
  }

  let busy = false;
  async function refreshVision() {
    if (busy) return;
    busy = true;
    try { camera.update(await getJSON("/api/vision")); } catch (error) { camera.update({ state: "UNKNOWN", reason: error.message }); }
    busy = false;
  }
  draw();
  refreshVision();
  const stop = onChange((what) => { if (["components", "run", "connection", "tick"].includes(what)) draw(); });
  const timers = [setInterval(draw, 1000), setInterval(refreshVision, 1000)];
  return () => { stop(); timers.forEach(clearInterval); };
}
