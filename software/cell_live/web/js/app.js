// The console shell: router, top bar, theme, Viewer mode (per window), SOFTWARE STOP.
import { connectStream, loadComponents, loadRun, onChange, postJSON, store } from "./api.js";
import { ACTIVE, STEP_LABELS } from "./cycle.js";
import { mountRail } from "./rail.js";
import { confirmDialog, lamp, say } from "./ui.js";

const SCREENS = ["overview", "run", "vision", "logs", "settings", "help", "show"];
const OPERATOR_SCREENS = ["run", "settings"]; // hidden and locked in Viewer mode
let current = { name: null, cleanup: null };

// Viewer mode: this window only (sessionStorage), or ?viewer=1 for the projector window
function viewerOn() {
  const params = new URLSearchParams(location.search);
  if (params.get("viewer") === "1") sessionStorage.setItem("viewer", "1");
  return sessionStorage.getItem("viewer") === "1";
}

function applyViewer(on) {
  document.body.classList.toggle("viewer", on);
  const button = document.getElementById("viewer");
  button.textContent = on ? "Viewer: ON" : "Viewer";
  button.title = on ? "Run and Settings are hidden in this window. Click to leave (asks first)."
    : "Viewer mode hides Run and Settings in this window. The SOFTWARE STOP stays.";
}

async function toggleViewer() {
  if (viewerOn()) {
    const leave = await confirmDialog({ title: "Leave Viewer mode?", body: "Run and Settings come back in this window.", ok: "Leave Viewer mode" });
    if (!leave) return;
    sessionStorage.removeItem("viewer");
    const params = new URLSearchParams(location.search);
    if (params.has("viewer")) {
      params.delete("viewer");
      history.replaceState(null, "", `${location.pathname}${params.toString() ? `?${params}` : ""}${location.hash}`);
    }
  } else {
    sessionStorage.setItem("viewer", "1");
  }
  applyViewer(viewerOn());
  route();
}

// Theme: remembered in this browser. Light (bench) is the default.
function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  document.getElementById("theme").textContent = theme === "dark" ? "Light" : "Dark";
  try { localStorage.setItem("theme", theme); } catch (error) { /* private window: not remembered */ }
}

function savedTheme() {
  try { return localStorage.getItem("theme") || "light"; } catch (error) { return "light"; }
}

// Router: #/overview, #/run, ...
async function route() {
  let name = (location.hash.replace(/^#\/?/, "").split("?")[0] || "overview").toLowerCase();
  if (!SCREENS.includes(name)) name = "overview";
  if (viewerOn() && OPERATOR_SCREENS.includes(name)) {
    say(`${name} is locked in Viewer mode`, "warn");
    name = "overview";
    history.replaceState(null, "", `${location.pathname}${location.search}#/overview`);
  }
  if (current.cleanup) current.cleanup();
  current = { name, cleanup: null };
  document.body.dataset.screen = name;
  for (const link of document.querySelectorAll("#nav a")) link.classList.toggle("active", link.dataset.route === name);
  const host = document.getElementById("screen");
  host.replaceChildren();
  const module = await import(`./${name}.js`);
  if (current.name === name) current.cleanup = module.render(host) || null;
  openDeepLinks();
}

// Deep links: #/overview?component=camera opens that drawer; &trace=open opens the trace panel
function openDeepLinks() {
  const query = new URLSearchParams(location.hash.split("?")[1] || "");
  if (query.get("component")) import("./drawer.js").then((drawer) => drawer.open(query.get("component")));
  if (query.get("trace") === "open") {
    const trace = document.getElementById("trace");
    if (trace.classList.contains("collapsed")) trace.querySelector("button")?.click();
  }
}

// Top bar: the connection lamp and the run state
function updateTopBar() {
  const conn = document.getElementById("conn");
  conn.className = `conn ${store.connected ? "up st-OK" : "down st-FAIL"}`;
  conn.replaceChildren(lamp(store.connected ? "OK" : "FAIL"), store.connected ? "backend" : "backend lost");
  document.getElementById("lost").classList.toggle("hidden", store.connected || !store.everConnected);
  const run = store.run;
  const cycle = document.getElementById("cycle");
  const text = !run ? "run unknown" : run.state === "IDLE" ? "run IDLE" : `${STEP_LABELS[run.state] || run.state} ${run.box}/${run.boxes}`;
  cycle.textContent = text;
  cycle.title = !run ? "State of the real run: no answer from the backend yet"
    : `Run state ${run.state}${run.step && run.step !== run.state ? `, step ${run.step}` : ""}${run.state === "IDLE" ? "" : `, box ${run.box} of ${run.boxes}`}`;
  cycle.className = `cycle-pill${ACTIVE(run) && run.state !== "FAULT" ? " live" : ""}${run?.state === "FAULT" ? " st-FAIL" : ""}`;
}

async function softwareStop() {
  try {
    const reply = await postJSON("/api/run/estop");
    say(reply.ok ? `Software stop sent. ${reply.message}` : reply.message, reply.ok ? "warn" : "info", 12000);
  } catch (error) {
    say(`Software stop could not be sent (${error.message}). USE THE PHYSICAL EMERGENCY STOP.`, "fail", 0);
  }
  loadRun();
}

function tickClock() {
  document.getElementById("clock").textContent = new Date().toLocaleTimeString([], { hour12: false });
}

function start() {
  applyTheme(savedTheme());
  applyViewer(viewerOn());
  document.getElementById("theme").addEventListener("click", () => applyTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark"));
  document.getElementById("viewer").addEventListener("click", toggleViewer);
  document.getElementById("stop").addEventListener("click", softwareStop);
  window.addEventListener("hashchange", route);
  onChange((what) => { if (["connection", "run", "components"].includes(what)) updateTopBar(); });
  connectStream();
  loadComponents().catch((error) => say(`No component list: ${error.message}`, "fail", 0));
  loadRun().then(updateTopBar);
  tickClock();
  setInterval(tickClock, 1000);
  // While a run is active, ask for its state once a second: the backend sends "run" events only when
  // the state changes, so the time under the current step would stand still without this.
  setInterval(() => { if (ACTIVE(store.run)) loadRun(); }, 1000);
  updateTopBar();
  mountRail(document.getElementById("rail"));
  import("./trace.js").then((trace) => trace.mount(document.getElementById("trace"))).catch(() => {});
  route();
}

start();
