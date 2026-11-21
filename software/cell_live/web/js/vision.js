// Vision screen: the camera picture with Choton's overlay, the pick area and the stop line (drawn by
// the backend), the counts, whether the object belt would stop, and the table of detections.
// All numbers come from /api/vision.
import { getJSON, postJSON } from "./api.js";
import { badge, h, say, seconds, text } from "./ui.js";

const KINDS = ["card", "candy", "box", "lid"];

export function cameraPanel() {
  const content = h("div", { class: "vf-content" });
  const chip = h("span", { class: "vf-chip" }, "no picture");
  const picture = h("div", { class: "viewfinder on-ink" }, content,
    h("div", { class: "vf-frame", "aria-hidden": "true" }, h("i"), h("i"), h("i"), h("i")), chip);
  const counts = h("div", { class: "counts" });
  const ready = h("div", { class: "ready st-UNKNOWN" }, "Ready flag: unknown");
  const cell = h("div", { class: "cell-notes" }); // what a run would do with the box and the lid now
  const note = h("p", { class: "muted small" });
  let streaming = false;
  let shown = ""; // the state and reason the no-camera block shows now

  // Rebuilt only when the state or the reason changes, so a click on Start camera is never lost to a redraw.
  function noCamera(summary) {
    streaming = false;
    chip.textContent = "no picture";
    const key = `${summary.state}|${summary.reason || ""}`;
    if (key === shown) return;
    shown = key;
    const start = h("button", { type: "button", "data-operator": true, onclick: async () => {
      try { const reply = await postJSON("/api/vision/start"); say(reply.message, reply.ok ? "info" : "warn"); } catch (error) { say(error.message, "fail"); }
    } }, "Start camera");
    content.replaceChildren(h("div", { class: "no-camera" }, badge(summary.state), h("p", {}, summary.reason || "no camera picture"), start));
  }

  function update(summary) {
    if (summary.state === "OK") {
      if (!streaming) {
        content.replaceChildren(h("img", { src: `/api/camera.mjpg?t=${Date.now()}`, alt: "Live camera picture with the detections" }));
        streaming = true;
        shown = "";
      }
      const camera = summary.camera || {};
      chip.textContent = `${summary.source === "run" ? "running cycle" : "live view"} ${text(camera.width_px)}×${text(camera.height_px)}`;
    } else {
      noCamera(summary);
    }
    const seen = summary.counts || {};
    const usable = summary.usable || {};
    counts.replaceChildren(...KINDS.map((kind) => h("div", { class: "count" },
      h("span", { class: "num count-n" }, seen[kind] === undefined ? "?" : seen[kind]), h("span", { class: "count-kind" }, kind),
      usable[kind] !== undefined ? h("span", { class: "muted small" }, `${usable[kind]} usable`) : null)));
    if (summary.state !== "OK") {
      ready.className = "ready st-NOT_OBSERVABLE";
      ready.replaceChildren(badge("NOT_OBSERVABLE"), "Ready flag: no camera");
    } else {
      // The run's own stop rule: the full set in the pick area, or a needed object at the stop line.
      const want = Object.entries(summary.want || {}).map(([kind, n]) => `${n} ${kind}`).join(" + ");
      const feed = summary.feed || {};
      const line = typeof feed.stop_y_mm === "number" ? `stop line y = ${feed.stop_y_mm} mm` : "no stop line";
      ready.className = `ready ${feed.stop ? "st-OK" : "st-WARN"}`;
      ready.replaceChildren(badge(feed.stop ? "OK" : "WARN"), feed.stop
        ? `Object belt would stop: ${feed.reason}`
        : `Object belt would keep running: ${feed.counts || `${want} needed`} (${line})`);
    }
    const view = summary.view_note ? { ok: false, words: summary.view_note } : null;
    cell.replaceChildren(...[["Box", summary.box], ["Lid", summary.lid], ["Camera view", view]].filter(([, part]) => summary.state === "OK" && part)
      .map(([name, part]) => h("p", { class: "cell-note" }, badge(part.ok ? "OK" : "WARN"), h("span", {}, h("strong", {}, `${name}: `), part.words))));
    note.textContent = summary.state === "OK"
      ? `Detections from the ${summary.source === "run" ? "running cycle" : "live view"}, ${seconds(summary.detections_age_s)} old. Grey boxes: at a picture edge, out of reach or outside the pick area (the rectangle). Red line: the stop line. Yellow circles (cal 1 to 5): the calibration marks; while the tape crosses are in place each circle sits on its cross.`
      : "";
  }

  return { picture, counts, ready, cell, note, update };
}

function detectionTable(rows) {
  if (!rows.length) return h("p", { class: "muted" }, "No detections in the latest picture.");
  return h("table", { class: "data ledger" },
    h("thead", {}, h("tr", {}, ...["type", "score", "colour", "robot X (mm)", "robot Y (mm)", "angle (deg)", "use"].map((title, index) => h("th", { class: index > 0 && index < 6 ? "num" : "" }, title)))),
    h("tbody", {}, ...rows.map((row) => h("tr", {},
      h("td", {}, h("strong", {}, row.type)), h("td", { class: "num" }, text(row.conf)), h("td", {}, text(row.color)),
      h("td", { class: "num" }, text(row.x_robot)), h("td", { class: "num" }, text(row.y_robot)), h("td", { class: "num" }, text(row.angle)),
      h("td", {}, row.edge ? "EDGE (not used)" : row.out_of_reach_mm ? `centre out of reach (${row.out_of_reach_mm} mm)`
        : row.out_of_reach_j1_deg ? `arm cannot reach (J1 ${row.out_of_reach_j1_deg}°)`
        : !row.reachable ? "outside the pick area" : row.top_edge ? "usable (touches the top edge)" : "usable")))));
}

export function render(root) {
  const camera = cameraPanel();
  const table = h("div");
  const status = h("span", { class: "muted" });
  root.append(
    h("div", { class: "screen-head" }, h("h1", {}, "Vision"), status),
    h("div", { class: "vision-grid" },
      h("section", {}, camera.picture, camera.note),
      h("section", { class: "panel" }, h("h2", {}, "In the picture"), camera.counts, camera.ready, camera.cell, h("h2", {}, "Detections"), table)));

  let busy = false;
  async function refresh() {
    if (busy) return;
    busy = true;
    try {
      const summary = await getJSON("/api/vision");
      camera.update(summary);
      table.replaceChildren(detectionTable(summary.detections || []));
      status.textContent = summary.state === "OK" ? `camera ${summary.camera?.width_px}×${summary.camera?.height_px}, ${text(summary.camera?.fps)} frames/s` : "";
    } catch (error) {
      camera.update({ state: "UNKNOWN", reason: `no answer from /api/vision (${error.message})` });
    }
    busy = false;
  }
  refresh();
  const timer = setInterval(refresh, 1000);
  return () => clearInterval(timer);
}
