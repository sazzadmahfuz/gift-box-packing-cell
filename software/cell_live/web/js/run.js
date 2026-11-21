// Run screen: live gate checklist, Arm -> Start (60 s token), the cycle belt, Pause / Resume / Skip / Abort.
// Every action goes to the run endpoints; the gate in the backend decides. Nothing is decided here.
import { loadRun, onChange, postJSON, serverNow, store } from "./api.js";
import { ACTIVE, cycleStrip } from "./cycle.js";
import { badge, confirmDialog, h, say } from "./ui.js";

export function render(root) {
  const inputs = { speed: null, boxes: 1, handOnEstop: false, acceptOpenBox: false };
  let gate = null;
  let token = null;
  let gateBusy = false;

  const strip = cycleStrip();
  const gateList = h("ol", { class: "gate-list" });
  const gateNote = h("p", { class: "muted" }, "Checking the gate…");
  const speedInput = h("input", { type: "number", min: 1, step: 1, class: "num", id: "speed" });
  const speedHint = h("span", { class: "muted small" });
  const boxInput = h("input", { type: "number", min: 1, step: 1, value: 1, class: "num box-count", "aria-label": "Number of boxes" });
  const boxButtons = h("div", { class: "segments" });
  const estopBox = h("input", { type: "checkbox", id: "hand-estop" });
  const openBox = h("input", { type: "checkbox", id: "open-box" });
  const armButton = h("button", { type: "button", class: "primary" }, "Arm");
  const startButton = h("button", { type: "button", class: "primary", disabled: true }, "Start");
  const drain = h("span", { class: "drain" }, h("i"));
  const tokenNote = h("span", { class: "muted num small" });
  const armResult = h("div", { class: "arm-result", "aria-live": "polite" });
  const events = h("div", { class: "events" });
  let eventsSeen = "";
  // The control keys are built once and only switched on or off, so a click is never lost to a redraw.
  const pauseButton = h("button", { type: "button", onclick: () => act("pause", "Pause") }, "Pause");
  const resumeButton = h("button", { type: "button", onclick: () => act("resume", "Resume"), title: "Repeats the paused step (after a pick or the lid: new pictures first)" }, "Resume");
  const skipButton = h("button", { type: "button", onclick: () => act("skip", "Skip box") }, "Skip box");
  const abortButton = h("button", { type: "button", class: "danger", onclick: () => askAbort() }, "Abort");
  const clearButton = h("button", { type: "button", onclick: () => act("clear-alarm", "Clear alarm") }, "Clear alarm");
  const beltButton = h("button", { type: "button", class: "danger", onclick: () => act("belt-stop", "Stop object belt"),
    title: "Any time: during a run it pauses the run (belt off); otherwise DO3 and DO16 go to their off levels. The box belt stops only at its sensor." }, "Stop object belt");
  const actions = h("div", { class: "actions" }, pauseButton, resumeButton, skipButton, abortButton, clearButton, beltButton);

  for (const count of [1, 3, 5]) {
    boxButtons.append(h("button", { type: "button", onclick: () => { inputs.boxes = count; boxInput.value = count; drawControls(); } }, String(count)));
  }
  boxInput.addEventListener("input", () => { inputs.boxes = Number(boxInput.value); drawControls(); });
  speedInput.addEventListener("input", () => { inputs.speed = Number(speedInput.value); token = null; drawControls(); });
  estopBox.addEventListener("change", () => { inputs.handOnEstop = estopBox.checked; token = null; drawControls(); });
  openBox.addEventListener("change", () => { inputs.acceptOpenBox = openBox.checked; token = null; drawControls(); });
  armButton.addEventListener("click", arm);
  startButton.addEventListener("click", start);

  root.append(
    h("div", { class: "screen-head" }, h("h1", {}, "Run"),
      h("span", { class: "muted" }, "Real robot: teacher present, hand on the physical emergency stop. Start only works after Arm passes the gate.")),
    strip.el,
    h("div", { class: "run-grid" },
      h("section", { class: "panel" }, h("h2", {}, "Safety gate"), h("p", { class: "small muted" }, "Checked by the backend, every 3 s."), gateNote, gateList),
      h("section", { class: "panel" }, h("h2", {}, "Run settings"),
        h("div", { class: "field" }, h("label", { for: "speed" }, "Speed percent"), h("div", { class: "choice-row" }, speedInput, speedHint)),
        h("div", { class: "field" }, h("label", {}, "Boxes"), h("div", { class: "choice-row" }, boxButtons, boxInput)),
        h("label", { class: "switch" }, estopBox, h("span", {}, h("strong", {}, "My hand is on the physical emergency stop"), h("br"),
          h("span", { class: "muted small" }, "The SOFTWARE STOP is only a software stop."))),
        h("label", { class: "switch" }, openBox, h("span", {}, "Accept an open box", h("br"), h("span", { class: "muted small" }, "Only if the lid heights are not taught."))),
        h("div", { class: "arm-row" }, armButton, startButton, h("div", { class: "arm-time" }, tokenNote, drain)), armResult),
      h("section", { class: "panel" }, h("h2", {}, "Control"), actions, h("h2", {}, "Recent run events"), events)));

  function body() {
    return { hand_on_estop: inputs.handOnEstop, boxes: inputs.boxes, speed_percent: inputs.speed ?? undefined, accept_open_box: inputs.acceptOpenBox };
  }

  async function refreshGate() {
    // While the cycle works the gate is asked only once (for the limits); the backend answers "a run is active".
    // PAUSED or FAULT: asked on, for the box and lid lines (what a Resume would find, as things lie now).
    if (gateBusy || (ACTIVE(store.run) && gate && !["PAUSED", "FAULT"].includes(store.run.state))) return;
    gateBusy = true;
    try {
      gate = await postJSON("/api/run/gate", body());
    } catch (error) {
      gate = { items: [], problems: [error.message], notes: [], error: true };
    }
    gateBusy = false;
    drawGate();
    drawControls();
  }

  function drawGate() {
    // What the camera shows of the box and the lid right now. It does not block Arm.
    const cell = ((gate && gate.cell) || []).map((part) => h("li", { class: `gate-item st-${part.ok ? "OK" : "WARN"}` }, h("span", { class: "gate-no" }),
      h("div", {}, h("div", { class: "gate-title" }, badge(part.ok ? "OK" : "WARN"), h("strong", {}, `${part.name} in the camera picture now`)), h("div", { class: "why" }, part.words))));
    if (ACTIVE(store.run) || (gate && gate.active)) {
      gateNote.textContent = "A run is active: the gate was passed at Start.";
      gateNote.className = "muted";
      gateList.replaceChildren(...cell);
      return;
    }
    if (!gate) return;
    gateNote.textContent = gate.error ? `Gate not reachable: ${gate.problems[0]}` : gate.ok ? "All items pass: Arm is possible." : `${gate.problems.length} problem(s): Arm is refused until they are fixed.`;
    gateNote.className = gate.ok ? "result-ok" : "result-fail";
    gateList.replaceChildren(...(gate.items || []).map((item) => h("li", { class: `gate-item st-${item.ok ? "OK" : "FAIL"}` },
      h("span", { class: "gate-no num" }, item.number), h("div", {}, h("div", { class: "gate-title" }, badge(item.ok ? "OK" : "FAIL"), h("strong", {}, item.title)),
        ...item.problems.map((problem) => h("div", { class: "why" }, problem))))));
    if (gate.notes && gate.notes.length) gateList.append(...gate.notes.map((note) => h("li", { class: "gate-item st-WARN" }, h("span", { class: "gate-no" }), h("div", { class: "gate-title" }, badge("WARN"), note))));
    gateList.append(...cell);
  }

  function drawControls() {
    const max = gate ? gate.speed_percent_max : null;
    if (inputs.speed === null && gate && gate.speed_percent) { inputs.speed = gate.speed_percent; speedInput.value = gate.speed_percent; }
    if (max) speedInput.max = max;
    speedHint.textContent = max ? `maximum ${max} % (control.speed_percent_max)` : ACTIVE(store.run) ? "" : "maximum not set yet (CONFIRM in Settings)";
    for (const button of boxButtons.children) button.classList.toggle("on", Number(button.textContent) === inputs.boxes);
    const running = ACTIVE(store.run);
    armButton.disabled = running;
    const left = token ? token.expiresAt - serverNow() : 0;
    if (token && left <= 0) token = null;
    startButton.disabled = running || !token;
    tokenNote.textContent = token ? `armed: Start within ${Math.ceil(left)} s` : running ? "run active" : "not armed";
    drain.firstChild.style.setProperty("--p", token ? `${Math.max(0, (left / token.total) * 100)}%` : "0%");
    drain.classList.toggle("armed", Boolean(token));
  }

  async function arm() {
    armButton.disabled = true;
    try {
      const reply = await postJSON("/api/run/arm", body());
      if (reply.armed) {
        token = { value: reply.token, expiresAt: serverNow() + reply.expires_in_s, total: reply.expires_in_s };
        armResult.replaceChildren(h("p", { class: "result-ok" }, "Gate passed. Start within the time shown."),
          ...(reply.notes || []).map((note) => h("p", { class: "muted" }, `Note: ${note}`)));
      } else {
        token = null;
        armResult.replaceChildren(h("p", { class: "result-fail" }, "Arm refused:"), h("ul", {}, ...reply.problems.map((p) => h("li", {}, p))));
      }
    } catch (error) {
      armResult.replaceChildren(h("p", { class: "result-fail" }, `Arm failed: ${error.message}`));
    }
    drawControls();
  }

  async function start() {
    if (!token) return;
    startButton.disabled = true;
    try {
      const reply = await postJSON("/api/run/start", { boxes: inputs.boxes, speed_percent: inputs.speed, token: token.value });
      token = null;
      armResult.replaceChildren(reply.started
        ? h("p", { class: "result-ok" }, `Run started. Log: ${reply.run_log}`)
        : h("div", {}, h("p", { class: "result-fail" }, "Start refused:"), h("ul", {}, ...reply.problems.map((p) => h("li", {}, p)))));
    } catch (error) {
      armResult.replaceChildren(h("p", { class: "result-fail" }, `Start failed: ${error.message}`));
    }
    loadRun();
    drawControls();
  }

  async function act(action, label) {
    try {
      const reply = await postJSON(`/api/run/${action}`);
      say(`${label}: ${reply.message}`, reply.ok ? "info" : "warn");
    } catch (error) {
      say(`${label} failed: ${error.message}`, "fail");
    }
    loadRun();
  }

  const askAbort = async () => {
    const yes = await confirmDialog({ title: "Abort the run?", body: "Outputs go off and the run ends. This cannot be resumed.", ok: "Abort run", danger: true });
    if (yes) act("abort", "Abort");
  };

  function drawRun() {
    strip.update();
    const run = store.run;
    const state = run ? run.state : "UNKNOWN";
    const running = ACTIVE(run) && !["PAUSED", "FAULT"].includes(state);
    pauseButton.disabled = !running;
    resumeButton.disabled = state !== "PAUSED";
    skipButton.disabled = state !== "PAUSED";
    abortButton.disabled = !ACTIVE(run);
    clearButton.disabled = state !== "FAULT";
    const list = run && run.events ? run.events : [];
    const signature = `${run ? "run" : "none"}:${list.length}:${list.length ? list[list.length - 1].time_s : ""}`;
    if (signature === eventsSeen) return;
    eventsSeen = signature;
    if (!run) { events.replaceChildren(h("p", { class: "muted" }, "Run state unknown (no answer from /api/run).")); return; }
    events.replaceChildren(h("table", { class: "data" }, h("tbody", {}, ...list.slice().reverse().map((event) =>
      h("tr", {}, h("td", { class: "num" }, event.time_s), h("td", {}, event.state), h("td", {}, event.event, event.fault ? ` (${event.fault})` : ""))))));
  }

  drawRun();
  drawControls();
  drawGate();
  loadRun().then(() => { drawRun(); drawGate(); });
  refreshGate();
  const gateTimer = setInterval(refreshGate, 3000);
  const tick = setInterval(drawControls, 500);
  const stop = onChange((what) => {
    if (what !== "run") return;
    drawRun(); drawControls();
    if (!ACTIVE(store.run) && gate && gate.active) refreshGate(); // the run just ended: ask the gate again now
    else drawGate();
  });
  return () => { clearInterval(gateTimer); clearInterval(tick); stop(); };
}
