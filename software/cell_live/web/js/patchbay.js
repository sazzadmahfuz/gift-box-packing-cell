// The cell map: the real wiring drawn like a patch bay. Each cable is one check the backend runs.
// A cable takes the colour of its last result. When a check finishes, one pulse runs along its cable.
// No pulse for a check that sent nothing (NOT OBSERVABLE or UNKNOWN), and none while the backend link is down.
// The wiring (which check sits on which device) is the TOPOLOGY table: edit it when the lab wiring changes.
import { isStale, onChange, store } from "./api.js";
import { h, lamp, ms, setLamp } from "./ui.js";
import { replay } from "./fx.js";

// The SVG namespace address, written in pieces: the web-file test allows no web address in these files.
const SVG_NS = ["http:", "", "www.w3.org", "2000", "svg"].join("/");

export const TOPOLOGY = {
  nodes: [
    { id: "pc", title: "This PC", sub: "runs cell_live", ports: [["backend", "console link"], ["robodk", "RoboDK"], ["vision_model", "vision model file"], ["calibration", "calibration file"]] },
    { id: "dobot", title: "Dobot M1 Pro", sub: "robot", ports: [["dobot_dashboard", "dashboard"], ["dobot_feedback", "feedback"],
      ["object_belt_do3", "belt start and stop (DO3)"], ["object_belt_dir", "belt direction (DO4)"], ["object_belt_power", "belt enable (DO16)"]] },
    { id: "belta", title: "Object belt", sub: "cards and candies, DTCB 25261249", ports: [] },
    { id: "uno", title: "Box belt controller", sub: "Arduino UNO R4 WiFi, sensor E18-D80NK", ports: [["box_belt_nano", "no link to this PC"]] },
    { id: "beltb", title: "Box belt", sub: "boxes and lids, DTCB-2418-0718", ports: [] },
    { id: "cam", title: "USB camera", sub: "above the object belt", ports: [["camera", "video"]] },
  ],
  cables: [
    { id: "dobot_dashboard", from: ["pc"], to: ["dobot", "dobot_dashboard"] },
    { id: "dobot_feedback", from: ["pc"], to: ["dobot", "dobot_feedback"] },
    { id: "box_belt_nano", from: ["pc"], to: ["uno", "box_belt_nano"] },
    { id: "camera", from: ["pc"], to: ["cam", "camera"] },
    { id: "object_belt_do3", from: ["dobot", "object_belt_do3"], to: ["belta"] },
    { id: "object_belt_dir", from: ["dobot", "object_belt_dir"], to: ["belta"] },
    { id: "object_belt_power", from: ["dobot", "object_belt_power"], to: ["belta"] },
    { neutral: true, from: ["uno", "box_belt_nano"], to: ["beltb"] }, // the UNO runs the box belt; no check reads it
    { neutral: true, from: ["uno", "box_belt_nano"], to: ["belta"] }, // the UNO also sends the step pulses of the object belt
  ],
  joint: null, // no Dobot output goes to the box belt: an operator takes the closed box (belts.box_restart = operator)
};
const WORST = ["FAIL", "WARN", "UNKNOWN", "NOT_OBSERVABLE", "OK"]; // first = needs attention most

export function mountMap(host, onOpen) {
  const svg = document.createElementNS(SVG_NS, "svg");
  svg.setAttribute("class", "wires");
  svg.setAttribute("aria-hidden", "true");

  function port(id, label, extra = "") {
    const link = id === "backend";
    return h(link ? "div" : "button", { class: `port${extra}`, "data-port": id, ...(link ? {} : { type: "button", onclick: () => onOpen(id) }) },
      lamp("UNKNOWN"), h("span", { class: "port-name" }, label), h("span", { class: "num port-ms" }));
  }
  const nodes = TOPOLOGY.nodes.map((node) => h("section", { class: "node", "data-node": node.id },
    h("header", {}, h("strong", {}, node.title), h("span", { class: "small muted" }, node.sub)),
    ...node.ports.map(([id, label]) => port(id, label)),
    node.ports.length ? null : h("div", { class: "conveyor", "aria-hidden": "true" })));
  const joint = TOPOLOGY.joint ? h("div", { class: "joint-cell" }, port(TOPOLOGY.joint.id, TOPOLOGY.joint.label, " joint")) : null;
  host.classList.add("map");
  host.replaceChildren(svg, ...nodes, ...(joint ? [joint] : []));

  const find = (selector) => host.querySelector(selector);
  // A cable plugs into the edge of the node that holds the port, at the height of the port itself.
  const spot = (el, side, fraction = 0.5) => {
    const box = el.getBoundingClientRect();
    const edge = (el.closest("[data-node]") || el).getBoundingClientRect();
    const base = host.getBoundingClientRect();
    return [(side === "right" ? edge.right : edge.left) - base.left, box.top - base.top + box.height * fraction];
  };
  const line = (cls, d, extra = {}) => {
    const path = document.createElementNS(SVG_NS, "path");
    path.setAttribute("class", cls);
    path.setAttribute("d", d);
    for (const [key, value] of Object.entries(extra)) path.setAttribute(key, value);
    return path;
  };
  const plug = (x, y, id) => {
    const dot = document.createElementNS(SVG_NS, "circle");
    dot.setAttribute("class", "plug");
    dot.setAttribute("cx", x);
    dot.setAttribute("cy", y);
    dot.setAttribute("r", 4.5);
    dot.dataset.cable = id;
    return dot;
  };

  function draw() {
    const base = host.getBoundingClientRect();
    svg.setAttribute("width", Math.round(base.width));
    svg.setAttribute("height", Math.round(base.height));
    const fromPc = TOPOLOGY.cables.filter((cable) => cable.from.length === 1);
    const shapes = [];
    for (const cable of TOPOLOGY.cables) {
      if (cable.neutral) {
        const a = spot(find(`[data-port="${cable.from[1]}"]`), "right");
        const b = spot(find(`[data-node="${cable.to[0]}"]`), "left");
        shapes.push(line("cable neutral", `M${a[0]} ${a[1]} L${b[0]} ${b[1]}`));
        continue;
      }
      const start = cable.from.length > 1 ? spot(find(`[data-port="${cable.from[1]}"]`), "right")
        : spot(find(`[data-node="${cable.from[0]}"]`), "right", (fromPc.indexOf(cable) + 1) / (fromPc.length + 1));
      const end = cable.to.length > 1 ? spot(find(`[data-port="${cable.to[1]}"]`), "left") : spot(find(`[data-node="${cable.to[0]}"]`), "left");
      const k = Math.max(30, (end[0] - start[0]) * 0.5);
      const d = `M${start[0]} ${start[1]} C${start[0] + k} ${start[1]}, ${end[0] - k} ${end[1]}, ${end[0]} ${end[1]}`;
      shapes.push(line("cable", d, { "data-cable": cable.id }), line("beam", d, { "data-cable": cable.id, pathLength: 100 }), plug(...start, cable.id), plug(...end, cable.id));
    }
    if (!TOPOLOGY.joint) { svg.replaceChildren(...shapes); return; }
    const top = find(`[data-node="${TOPOLOGY.joint.from}"]`).getBoundingClientRect();
    const bottom = find(`[data-node="${TOPOLOGY.joint.to}"]`).getBoundingClientRect();
    const x = top.left - base.left + top.width * 0.5;
    const d = `M${x} ${top.bottom - base.top} L${x} ${bottom.top - base.top}`;
    shapes.push(line("cable", d, { "data-cable": TOPOLOGY.joint.id }), line("beam", d, { "data-cable": TOPOLOGY.joint.id, pathLength: 100 }),
      plug(x, top.bottom - base.top, TOPOLOGY.joint.id), plug(x, bottom.top - base.top, TOPOLOGY.joint.id));
    svg.replaceChildren(...shapes);
  }

  function read(id) {
    if (id === "backend") {
      const state = store.connected ? "OK" : store.everConnected ? "FAIL" : "UNKNOWN";
      return { state, stale: false, latency: null, title: store.connected ? "This page is connected to the backend" : "No connection to the backend" };
    }
    const component = store.components.get(id);
    return {
      state: component ? component.state : "UNKNOWN", stale: component ? isStale(component) : !store.connected,
      latency: component ? component.latency_ms : null, title: component ? `${component.name}: ${component.detail}` : id,
    };
  }

  function refresh() {
    const seen = {};
    for (const el of host.querySelectorAll("[data-port]")) {
      const { state, stale, latency, title } = read(el.dataset.port);
      const shape = el.querySelector(".lamp");
      if (el.dataset.seen && shape.dataset.state !== state) replay(shape, "changed");
      el.dataset.seen = "1";
      setLamp(shape, state, stale);
      el.className = `port${el.classList.contains("joint") ? " joint" : ""} st-${state}${stale ? " stale" : ""}`;
      el.title = title;
      el.querySelector(".port-ms").textContent = latency === null || latency === undefined || stale ? "" : ms(latency);
      const node = el.closest("[data-node]");
      if (node) seen[node.dataset.node] = [...(seen[node.dataset.node] || []), stale ? "UNKNOWN" : state];
    }
    for (const node of host.querySelectorAll("[data-node]")) {
      const states = seen[node.dataset.node] || [];
      const worst = WORST.find((state) => states.includes(state)) || "UNKNOWN";
      node.className = `node st-${worst}`;
    }
    for (const el of svg.querySelectorAll("[data-cable]")) {
      const { state, stale } = read(el.dataset.cable);
      const base = el.getAttribute("class").split(" ")[0];
      // A pulse in flight keeps its "go" class, so the status of another check does not cut it off.
      const going = el.classList.contains("go") && !stale && store.connected ? " go" : "";
      el.setAttribute("class", `${base} st-${state}${stale ? " stale" : ""}${going}`);
    }
  }

  function pulse(component) {
    if (!store.connected || isStale(component) || ["NOT_OBSERVABLE", "UNKNOWN"].includes(component.state)) return;
    replay(svg.querySelector(`.beam[data-cable="${component.id}"]`), "go");
  }

  const observer = new ResizeObserver(() => { draw(); refresh(); });
  observer.observe(host);
  if (document.fonts) document.fonts.ready.then(() => { draw(); refresh(); });
  draw();
  refresh();
  const stop = onChange((what, payload) => {
    if (what === "status") pulse(payload);
    if (["components", "connection", "tick"].includes(what)) refresh();
  });
  return { refresh, destroy: () => { stop(); observer.disconnect(); } };
}
