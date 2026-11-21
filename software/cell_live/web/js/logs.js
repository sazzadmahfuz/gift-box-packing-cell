// Logs screen: the live event stream (with filters) and the HARDWARE RUN logs in testing/live_runs.
// Per-box times, failures and the mean are computed by the backend (/api/logs/<file>).
import { getJSON, onChange, store } from "./api.js";
import { clock, h, seconds, text } from "./ui.js";

const FILTERS = { all: () => true, info: (e) => e.kind !== "fault" && !/WARN|PAUSED/.test(e.event || ""), warning: (e) => /WARN|PAUSED/.test(e.event || ""), fault: (e) => e.kind === "fault" || /FAIL|FAULT/.test(e.event || "") };

function summaryView(log) {
  const summary = log.summary || {};
  const boxes = (summary.boxes || []).map((box) => h("tr", {},
    h("td", { class: "num" }, box.box), h("td", {}, box.result), h("td", { class: "num" }, seconds(box.duration_s, 3)),
    h("td", { class: "num" }, seconds(box.start_s, 3)), h("td", { class: "num" }, seconds(box.end_s, 3))));
  const failures = (summary.failures || []).map((failure) => h("tr", {},
    h("td", { class: "num" }, seconds(failure.time_s, 3)), h("td", { class: "num" }, failure.box), h("td", {}, failure.event)));
  const mean = summary.mean_box_s === null || summary.mean_box_s === undefined ? "unknown" : seconds(summary.mean_box_s, 3);
  const stat = (value, label) => h("div", { class: "stat" }, h("span", { class: "num stat-n" }, value), h("span", { class: "muted small" }, label));
  return h("div", {},
    h("p", { class: "mono banner-line" }, log.banner || "(no banner line)"),
    h("div", { class: "stats" }, stat(summary.boxes_done ?? 0, "box(es) done"),
      stat(mean, summary.mean_box_s === null || summary.mean_box_s === undefined ? "mean time per done box (no box done)" : "mean time per done box"),
      stat((summary.failures || []).length, "pause(s) or fault(s)")),
    h("table", { class: "data ledger" }, h("thead", {}, h("tr", {}, ...["box", "result", "time per box", "start", "end"].map((t, i) => h("th", { class: i === 1 ? "" : "num" }, t)))),
      h("tbody", {}, boxes.length ? boxes : [h("tr", {}, h("td", { colspan: 5, class: "muted" }, "no box finished in this log"))])),
    h("h2", {}, "Pauses and faults"),
    h("table", { class: "data" }, h("thead", {}, h("tr", {}, h("th", {}, "time"), h("th", {}, "box"), h("th", {}, "event"))),
      h("tbody", {}, failures.length ? failures : [h("tr", {}, h("td", { colspan: 3, class: "muted" }, "none"))])));
}

export function render(root) {
  let filter = "all";
  let selected = [];
  const filterRow = h("div", { class: "segments" });
  const events = h("div", { class: "feed" });
  const list = h("div");
  const detail = h("div", { class: "panel" }, h("p", { class: "muted" }, "Select a run log. Ctrl+click a second one to compare."));
  const folder = h("p", { class: "muted mono small" });

  root.append(
    h("div", { class: "screen-head" }, h("h1", {}, "Logs"), h("span", { class: "muted" }, "Real runs only: the files in testing/live_runs, line 1 says HARDWARE RUN.")),
    h("section", { class: "panel feed-panel" }, h("div", { class: "feed-head" }, h("h2", {}, "Live events"), filterRow), events),
    h("div", { class: "split" },
      h("section", { class: "panel" }, h("h2", {}, "Run logs"), folder, list),
      detail));

  function drawFilters() {
    filterRow.replaceChildren(...Object.keys(FILTERS).map((name) =>
      h("button", { type: "button", class: name === filter ? "on" : "", onclick: () => { filter = name; drawFilters(); drawEvents(); } }, name)));
  }

  function drawEvents() {
    const rows = store.trace.filter(FILTERS[filter]).slice(-120).reverse().map((entry) => h("tr", {},
      h("td", { class: "num" }, clock(entry.received_at)), h("td", {}, entry.kind || ""), h("td", {}, entry.source || entry.state || ""),
      h("td", { class: "mono" }, entry.command || entry.event || ""), h("td", { class: "mono" }, entry.reply || entry.fault || "")));
    events.replaceChildren(h("table", { class: "data" }, h("tbody", {}, rows.length ? rows : [h("tr", {}, h("td", { class: "muted" }, "no events in this filter yet"))])));
  }

  async function loadList() {
    try {
      const reply = await getJSON("/api/logs");
      folder.textContent = reply.folder;
      list.replaceChildren(...(reply.logs.length ? reply.logs.map((log) => h("div", {
        class: `list-item${selected.includes(log.name) ? " on" : ""}`, title: log.banner,
        onclick: (event) => choose(log.name, event.ctrlKey || event.metaKey),
      }, h("div", { class: "mono" }, log.name), h("div", { class: "muted small" }, text(log.banner).slice(0, 90))))
        : [h("p", { class: "muted" }, "No real run has been logged yet. Each run writes one CSV here.")]));
    } catch (error) {
      list.replaceChildren(h("p", { class: "result-fail" }, `Logs not available: ${error.message}`));
    }
  }

  async function choose(name, add) {
    selected = add ? [...selected.filter((n) => n !== name), name].slice(-2) : [name];
    loadList();
    try {
      const logs = await Promise.all(selected.map((n) => getJSON(`/api/logs/${encodeURIComponent(n)}`)));
      detail.replaceChildren(...(logs.length === 2
        ? [h("h2", {}, "Compare"), h("div", { class: "compare" },
          ...logs.map((log) => h("div", {}, h("h2", { class: "mono" }, log.name), summaryView(log))))]
        : [h("h2", { class: "mono" }, logs[0].name), summaryView(logs[0])]));
    } catch (error) {
      detail.replaceChildren(h("p", { class: "result-fail" }, `Could not read the log: ${error.message}`));
    }
  }

  drawFilters();
  drawEvents();
  loadList();
  const stop = onChange((what) => { if (what === "trace") drawEvents(); });
  const timer = setInterval(loadList, 10000);
  return () => { stop(); clearInterval(timer); };
}
