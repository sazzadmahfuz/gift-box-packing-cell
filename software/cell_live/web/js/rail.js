// Lamp rail (left edge, every screen): one lamp per component, like the pilot lamps on the cabinet door.
// Hover or focus shows the name and state; a click opens that component's drawer.
import { isStale, onChange, store } from "./api.js";
import { STATES, h, lamp, setLamp } from "./ui.js";
import { replay } from "./fx.js";

export function mountRail(host) {
  const buttons = new Map();

  function sync() {
    for (const component of store.components.values()) {
      let button = buttons.get(component.id);
      if (!button) {
        button = h("button", { type: "button", class: "rail-lamp", onclick: () => import("./drawer.js").then((drawer) => drawer.open(component.id)) }, lamp("UNKNOWN", { size: "big" }));
        buttons.set(component.id, button);
        host.append(button);
      }
      const stale = isStale(component);
      const shape = button.firstChild;
      if (button.dataset.seen && shape.dataset.state !== component.state) replay(shape, "changed");
      button.dataset.seen = "1";
      setLamp(shape, component.state, stale);
      button.className = `rail-lamp st-${component.state}${stale ? " stale" : ""}`;
      const word = stale ? "old data" : (STATES[component.state] || STATES.UNKNOWN).word;
      button.dataset.label = `${component.name}: ${word}`;
      button.setAttribute("aria-label", `${component.name}: ${word}. Open details`);
    }
  }

  sync();
  onChange((what) => { if (["components", "connection", "tick"].includes(what)) sync(); });
}
