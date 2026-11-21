// Talking to the cell_live backend: JSON requests and the Server-Sent Events stream.
// One store holds what the backend reported; screens subscribe to changes.

export const store = {
  components: new Map(), // id -> status (as sent by the backend)
  run: null, // latest GET /api/run or "run" event
  trace: [], // newest last, at most TRACE_MAX
  latency: new Map(), // id -> last latencies in ms since this page opened (for the small bars), at most LATENCY_KEEP
  connected: false,
  everConnected: false,
  serverOffsetS: 0, // server clock minus this browser's clock (same PC, so small)
  unconfirmed: [],
};
const TRACE_MAX = 400;
const LATENCY_KEEP = 24;
const listeners = new Set();

export class ApiError extends Error {
  constructor(message, status, body) {
    super(message);
    this.status = status;
    this.body = body;
  }
}

export function onChange(listener) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function emit(what, payload) {
  for (const listener of [...listeners]) {
    try { listener(what, payload); } catch (error) { console.error(error); }
  }
}

async function request(method, path, body) {
  const options = { method, cache: "no-store", headers: {} };
  if (body !== undefined) {
    options.headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(body);
  }
  let response;
  try {
    response = await fetch(path, options);
  } catch (error) {
    throw new ApiError(`backend not reachable (${error.message})`, 0, null);
  }
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new ApiError(data.error || (data.problems || []).join("; ") || response.statusText, response.status, data);
  return data;
}

export const getJSON = (path) => request("GET", path);
export const postJSON = (path, body = {}) => request("POST", path, body);

export function serverNow() {
  return Date.now() / 1000 + store.serverOffsetS;
}

export function isStale(component) {
  if (!store.connected) return true;
  if (!component || !component.checked_at) return false; // never checked: shown as UNKNOWN, not stale
  return serverNow() - component.checked_at > 2 * (component.interval_s || 5);
}

export async function loadComponents() {
  const body = await getJSON("/api/components");
  store.serverOffsetS = body.server_time - Date.now() / 1000;
  for (const component of body.components) store.components.set(component.id, component);
  store.unconfirmed = body.unconfirmed_config || [];
  emit("components");
  return body;
}

// An answer to GET /api/run can arrive after a newer "run" event from the stream. It is used only
// if nothing newer has been shown since its request started, so the box marker never jumps back.
let runRequests = 0; // number of GET /api/run started
let runShown = 0; // answers to requests up to this number are older than what the page shows

export async function loadRun() {
  const mine = (runRequests += 1);
  let run = null;
  try { run = await getJSON("/api/run"); } catch (error) { /* shown as "run state unknown" */ }
  if (mine <= runShown) return store.run;
  runShown = mine;
  store.run = run;
  emit("run");
  return store.run;
}

function addTrace(entry) {
  store.trace.push({ received_at: serverNow(), ...entry });
  if (store.trace.length > TRACE_MAX) store.trace.splice(0, store.trace.length - TRACE_MAX);
  emit("trace");
}

// The backend sends an event at least every 5 s (heartbeat). Silence for longer than this means
// the backend or the network hangs, even when the browser still holds the connection open.
const SILENCE_LIMIT_MS = 12000;
let stream = null;
let lastHeardMs = 0;

export function connectStream() {
  openStream();
  setInterval(() => {
    if (store.connected && Date.now() - lastHeardMs > SILENCE_LIMIT_MS) {
      store.connected = false;
      emit("connection");
      stream.close();
      openStream();
    }
  }, 1000);
}

function openStream() {
  stream = new EventSource("/api/stream");
  const heard = () => { lastHeardMs = Date.now(); };
  for (const kind of ["status", "run", "trace", "heartbeat"]) stream.addEventListener(kind, heard);
  stream.addEventListener("open", () => {
    heard();
    store.connected = store.everConnected = true;
    emit("connection");
    loadComponents().catch(() => {});
    loadRun();
  });
  stream.addEventListener("error", () => {
    store.connected = false;
    emit("connection");
  });
  stream.addEventListener("status", (event) => {
    const component = JSON.parse(event.data);
    const before = store.components.get(component.id);
    store.components.set(component.id, component);
    if (component.latency_ms !== null && component.latency_ms !== undefined) {
      const seen = store.latency.get(component.id) || [];
      seen.push(component.latency_ms);
      store.latency.set(component.id, seen.slice(-LATENCY_KEEP));
    }
    emit("components");
    emit("status", component); // one finished check: the cell map sends a pulse along that cable
    if (!before || before.state !== component.state) {
      addTrace({ kind: "status", source: component.name, event: `${component.state}: ${component.detail}` });
    }
  });
  stream.addEventListener("run", (event) => {
    runShown = runRequests; // answers still on their way were asked before this event
    store.run = { ...(store.run || {}), ...JSON.parse(event.data) };
    emit("run");
  });
  stream.addEventListener("trace", (event) => {
    const data = JSON.parse(event.data);
    addTrace({ kind: data.fault ? "fault" : data.source ? "check" : "run", ...data });
  });
  stream.addEventListener("heartbeat", (event) => {
    store.serverOffsetS = JSON.parse(event.data).server_time - Date.now() / 1000;
    emit("tick");
  });
}
