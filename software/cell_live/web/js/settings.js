// Settings screen: the lab fields of live_config.json. Every save is validated by the backend
// (same loader as at start-up), keeps live_config.json.bak, and needs a new status and source.
import { getJSON, loadComponents, postJSON } from "./api.js";
import { h, say, text } from "./ui.js";

function valueInput(entry) {
  const current = entry.value;
  if (entry.type === "choice" || entry.type === "bool") {
    const options = entry.type === "bool" ? ["true", "false"] : entry.choices;
    return h("select", {}, h("option", { value: "" }, "(not set)"),
      ...options.map((option) => h("option", { value: option, selected: String(current) === option }, option)));
  }
  const kind = entry.type === "int" || entry.type === "number" ? "number" : "text";
  return h("input", { type: kind, step: entry.type === "int" ? 1 : "any", value: current === null ? "" : current, placeholder: "(not set)" });
}

function readValue(entry, input) {
  const raw = input.value.trim();
  if (raw === "") return null;
  if (entry.type === "int" || entry.type === "number") return Number(raw);
  if (entry.type === "bool") return raw === "true";
  return raw;
}

function row(entry, statuses, onSaved) {
  const name = `${entry.section}.${entry.key}`;
  const input = valueInput(entry);
  input.id = `field-${name}`;
  const status = h("select", {}, ...statuses.map((option) => h("option", { value: option, selected: option === entry.status }, option)));
  const source = h("input", { type: "text", placeholder: "new source: who, when", value: "",
    title: "Where the value comes from, for example: lab 17 Nov, Rashmika" });
  const result = h("div", { class: "small" });
  const save = h("button", { type: "button", class: "primary" }, "Save");
  save.addEventListener("click", async () => {
    save.disabled = true;
    try {
      const reply = await postJSON("/api/config", { section: entry.section, key: entry.key, value: readValue(entry, input), status: status.value, source: source.value });
      result.replaceChildren(h("span", { class: "result-ok" }, `Saved (old file kept as ${reply.backup}). ${reply.reloaded || ""}`));
      say(`${name} saved`, "info");
      onSaved();
    } catch (error) {
      const problems = (error.body && error.body.problems) || [error.message];
      result.replaceChildren(h("span", { class: "result-fail" }, "Not saved: "), problems.join("; "));
    }
    save.disabled = false;
  });
  return h("tr", {},
    h("td", {}, h("div", { class: "mono" }, name), h("div", { class: "muted small" }, entry.unit, " ", h("span", { class: `chip ${entry.status === "CONFIRM" ? "chip-confirm" : entry.status === "VERIFIED" ? "chip-verified" : ""}` }, entry.status))),
    h("td", {}, input), h("td", {}, status),
    h("td", {}, h("div", { class: "muted small source-now" }, `now: ${entry.source}`), source),
    h("td", {}, save, result));
}

function portsView(ports) {
  const cameras = ports.cameras || {};
  const serial = ports.serial || {};
  const fill = (id, value) => {
    const input = document.getElementById(id);
    if (input) { input.value = value; input.focus(); say(`Filled ${id.replace("field-", "")} with ${value}: add the source, then Save`, "info"); }
  };
  return h("div", {},
    h("h2", {}, "Cameras on this PC"),
    cameras.detail ? h("p", { class: "result-fail" }, cameras.detail) : null,
    h("ul", { class: "plain" }, ...(cameras.cameras || []).map((camera) => h("li", {},
      `index ${camera.index}: ${camera.opens ? `opens, ${camera.frame || "no frame"}` : "does not open"} `,
      camera.opens ? h("button", { type: "button", onclick: () => fill("field-camera.index", camera.index) }, "use") : null))),
    h("h2", {}, "Serial ports"),
    h("p", { class: "muted" }, `from ${serial.source || "unknown"}${serial.detail ? ` (${serial.detail})` : ""}`),
    h("ul", { class: "plain" }, ...((serial.ports || []).length ? serial.ports.map((port) => h("li", {}, `${port} `,
      h("button", { type: "button", onclick: () => fill("field-arduino.serial_port", port) }, "use")))
      : [h("li", { class: "muted" }, "none found")])));
}

export function render(root) {
  const table = h("div", { class: "panel" }, h("p", { class: "muted" }, "Loading…"));
  const ports = h("div", { class: "panel" }, h("p", { class: "muted" }, "Scanning opens each camera index once (a few seconds)."),
    h("button", { type: "button", onclick: scan }, "Scan cameras and serial ports"));
  const others = h("details", { class: "panel others" });
  root.append(
    h("div", { class: "screen-head" }, h("h1", {}, "Settings"),
      h("span", { class: "muted" }, "Lab values from live_config.json. Every save needs a new source and a confirmed status; the backend checks it.")),
    h("div", { class: "split wide-first" }, table, ports),
    others);

  async function load() {
    try {
      const config = await getJSON("/api/config");
      const lab = config.entries.filter((entry) => entry.editable);
      table.replaceChildren(
        h("h2", {}, `Lab fields (${config.unconfirmed.length} still CONFIRM)`),
        h("table", { class: "data settings-table" },
          h("thead", {}, h("tr", {}, ...["field", "value", "status", "source", ""].map((title) => h("th", {}, title)))),
          h("tbody", {}, ...lab.map((entry) => row(entry, config.allowed_status, () => { load(); loadComponents().catch(() => {}); })))),
        h("p", { class: "muted" }, "The lid heights live in Choton's settings.json (his folder, read-only here): he teaches them with 15_robot_setup.py, keys l and j."));
      others.replaceChildren(h("summary", {}, `All other entries (read-only): ${config.file}`),
        h("table", { class: "data" }, h("tbody", {}, ...config.entries.filter((entry) => !entry.editable).map((entry) => h("tr", {},
          h("td", { class: "mono" }, `${entry.section}.${entry.key}`), h("td", { class: "mono" }, text(entry.value)),
          h("td", {}, entry.status), h("td", { class: "muted" }, entry.source))))));
    } catch (error) {
      table.replaceChildren(h("p", { class: "result-fail" }, `Settings not available: ${error.message}`));
    }
  }

  async function scan(event) {
    event.target.disabled = true;
    try { ports.replaceChildren(portsView(await getJSON("/api/ports"))); } catch (error) { say(`Scan failed: ${error.message}`, "fail"); }
  }

  load();
}
