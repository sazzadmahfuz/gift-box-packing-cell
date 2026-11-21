// The cycle drawn as a belt: six stations, a box marker at the current one, the state in big type.
// Everything comes from /api/run (store.run). The marker jumps when the backend reports a new step;
// it never slides, because the backend only knows the step, not a position between steps.
import { store } from "./api.js";
import { h, seconds } from "./ui.js";

export const STEPS = ["WAIT_BOX", "FEED_OBJECTS", "LOOK", "PICK_PLACE", "CLOSE_LID", "RELEASE_BOX"];
export const STEP_LABELS = {
  WAIT_BOX: "Wait for the box", FEED_OBJECTS: "Feed objects", LOOK: "Look", PICK_PLACE: "Pick and place",
  CLOSE_LID: "Close the lid", RELEASE_BOX: "Release the box",
};
export const STEP_WORDS = {
  WAIT_BOX: "wait for the open box", FEED_OBJECTS: "object belt runs until the set is in the pick area or an item reaches the stop line", LOOK: "robot home, pictures",
  PICK_PLACE: "pick and place each item", CLOSE_LID: "put the lid on", RELEASE_BOX: "the closed box leaves",
};
export const STATE_LABELS = {
  IDLE: "Idle", WAIT_BOX: "Waiting for a box", FEED_OBJECTS: "Feeding objects", LOOK: "Looking", PICK_PLACE: "Picking and placing",
  CLOSE_LID: "Closing the lid", RELEASE_BOX: "Releasing the box", BOX_DONE: "Box done", PAUSED: "Paused", FAULT: "Fault",
};
export const ACTIVE = (run) => Boolean(run) && !["IDLE", undefined].includes(run.state) && !run.finished;

export function cycleStrip({ large = false, compact = false } = {}) {
  const word = h("div", { class: "cycle-word display" });
  const code = h("span", { class: "chip mono" });
  const where = h("div", { class: "cycle-where" });
  const why = h("div", { class: "cycle-why" });
  const stations = STEPS.map((step) => h("li", { class: "station", "data-step": step },
    h("span", { class: "marker" }), h("strong", {}, STEP_LABELS[step]), h("span", { class: "station-words" }, STEP_WORDS[step]),
    h("span", { class: "num station-time" })));
  const el = h("section", { class: `cycle${large ? " large" : ""}${compact ? " compact" : ""}`, "aria-label": "Cycle" },
    h("div", { class: "cycle-head" }, word, h("div", { class: "cycle-info" }, h("div", {}, code, " ", where), why)),
    h("ol", { class: "belt" }, ...stations));

  function update() {
    const run = store.run;
    const state = run ? run.state : "UNKNOWN";
    el.dataset.state = state;
    word.textContent = run ? STATE_LABELS[state] || state : "Run state unknown";
    code.textContent = run ? state : "";
    code.classList.toggle("hidden", !run || (STATE_LABELS[state] || "").toUpperCase() === state);
    where.textContent = !run ? "No answer from /api/run yet." : state === "IDLE" ? "No run active." : `Box ${run.box} of ${run.boxes}`;
    why.replaceChildren(...[
      run && run.pause_reason ? h("span", { class: "result-fail" }, `Paused: ${run.pause_reason}`) : null,
      // After the run has ended the fault text stays in the snapshot: say that it belongs to the last run.
      run && run.fault ? h("span", { class: "result-fail" }, `${run.finished ? "Last run ended with a fault" : "Fault"}: ${run.fault}`) : null].filter(Boolean));
    const now = run ? STEPS.indexOf(run.step) : -1;
    stations.forEach((station, index) => {
      station.className = `station${index === now ? " now" : index < now ? " done" : ""}`;
      station.querySelector(".station-time").textContent = index === now && run.step_elapsed_s !== null && run.step_elapsed_s !== undefined ? seconds(run.step_elapsed_s) : "";
    });
  }
  update();
  return { el, update };
}
