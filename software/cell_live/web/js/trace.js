// Trace panel (bottom, collapsible): what was sent, what came back, and when.
import { onChange, store } from "./api.js";
import { clock, h } from "./ui.js";

const SHOWN = 150;

function row(entry) {
  const when = clock(entry.received_at);
  const what = entry.command ? `${entry.command}` : entry.event || "";
  const answer = entry.reply || entry.fault || "";
  return h("tr", { class: entry.kind === "fault" ? "result-fail" : "" },
    h("td", { class: "num" }, when),
    h("td", {}, entry.kind || ""),
    h("td", {}, entry.source || entry.state || ""),
    h("td", { class: "mono" }, what),
    h("td", { class: "mono" }, answer),
    h("td", { class: "num" }, entry.latency_ms !== undefined && entry.latency_ms !== null ? `${Number(entry.latency_ms).toFixed(1)} ms` : ""));
}

export function mount(host) {
  const count = h("span", { class: "muted" }, "");
  const toggle = h("button", { type: "button", class: "ghost", "aria-expanded": "false" }, "Show trace");
  const body = h("div", { class: "trace-body" });
  host.replaceChildren(
    h("div", { class: "trace-head" },
      h("h2", {}, "Trace"), count, h("span", { class: "muted small" }, "commands, replies and events, newest first"),
      h("span", { class: "spacer" }), toggle),
    body);
  toggle.addEventListener("click", () => {
    host.classList.toggle("collapsed");
    toggle.textContent = host.classList.contains("collapsed") ? "Show trace" : "Hide trace";
    toggle.setAttribute("aria-expanded", String(!host.classList.contains("collapsed")));
    draw();
  });

  function draw() {
    count.textContent = `(${store.trace.length})`;
    if (host.classList.contains("collapsed")) return;
    const rows = store.trace.slice(-SHOWN).reverse().map(row);
    body.replaceChildren(h("table", { class: "data ledger" },
      h("thead", {}, h("tr", {}, h("th", {}, "time"), h("th", {}, "kind"), h("th", {}, "source"),
        h("th", {}, "sent / event"), h("th", {}, "reply"), h("th", {}, "latency"))),
      h("tbody", {}, rows.length ? rows : [h("tr", {}, h("td", { colspan: 6, class: "muted" }, "nothing yet"))])));
  }

  onChange((what) => { if (what === "trace") draw(); });
  draw();
}
