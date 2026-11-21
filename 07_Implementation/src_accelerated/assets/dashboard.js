"use strict";

const $ = id => document.getElementById(id);
const tabs = ["Overview", "Network", "Simulation", "BESS", "Economics", "Optimization", "Diagnostics"];
const colors = ["#087c80", "#b84c37", "#275fa5", "#79568c", "#806509", "#257647"];
const state = {runs: [], run: 0, scenario: "", tab: "Overview", hour: 0,
  equipment: ["Bus", ""], zoom: 1, offsetX: 0, offsetY: 0, redraw: null};
const empty = {label: "Summary only", hours: [], buses: {}, branches: {}, metrics: [], events: []};
const number = value => typeof value === "number" && Number.isFinite(value);
const fmt = (value, digits = 5) => number(value) ? new Intl.NumberFormat("en", {
  maximumFractionDigits: digits, maximumSignificantDigits: 9
}).format(value) : value === null || value === undefined || value === "" ? "Unavailable" :
  typeof value === "boolean" ? (value ? "Yes" : "No") :
  typeof value === "object" ? JSON.stringify(value) : String(value);
const nameOf = key => key.replaceAll("_", " ").replace(/^./, letter => letter.toUpperCase());
const manifest = () => state.runs[state.run].manifest;
const current = () => state.runs[state.run];
const active = () => current().scenarios[state.scenario] || empty;
const staticCase = () => active().hours[0]?.timestamp === "Static base case";
const hourAt = () => active().hours[state.hour]?.timestamp || null;
const eventAt = () => active().eventIndex?.get(hourAt()) || null;
const metricsOf = rows => Object.fromEntries(rows.map(row => [row.metric, row.value]));
const textMetric = (key, fallback) => metricsOf(active().metrics)[key] ?? fallback ?? null;

function el(tag, value, className) {
  const node = document.createElement(tag);
  if (value !== undefined) node.textContent = value;
  if (className) node.className = className;
  return node;
}

function label(text, control, className) {
  const box = el("label", text, className);
  box.append(control);
  return box;
}

function button(text, action) {
  const control = el("button", text);
  control.type = "button";
  control.addEventListener("click", action);
  return control;
}

function select(options, selected) {
  const control = el("select");
  options.forEach(([value, text]) => control.add(new Option(text, value)));
  if (selected !== undefined && options.some(([key]) => String(key) === String(selected))) control.value = selected;
  return control;
}

function section(root, title) {
  const block = el("section", undefined, "block");
  block.append(el("h2", title));
  root.append(block);
  return block;
}

function note(root, value) {
  root.append(el("p", value, "muted"));
}

function table(root, headings, rows) {
  const wrap = el("div", undefined, "table-wrap");
  const grid = el("table");
  const header = grid.createTHead().insertRow();
  headings.forEach(value => header.append(el("th", value)));
  const body = grid.createTBody();
  rows.forEach(row => {
    const entry = body.insertRow();
    row.forEach(value => {
      const cell = entry.insertCell();
      if (value instanceof Node) cell.append(value);
      else cell.textContent = fmt(value);
      if (number(value)) cell.className = "num";
    });
  });
  wrap.append(grid);
  root.append(wrap);
  return wrap;
}

function kv(root, entries) {
  return table(root, ["Measure", "Value"], entries);
}

function details(root, title, value) {
  const container = el("details");
  container.append(el("summary", title), el("pre", typeof value === "string" ? value : JSON.stringify(value, null, 2)));
  root.append(container);
  return container;
}

function cards(root, entries) {
  const deck = el("div", undefined, "grid");
  for (const [caption, value] of entries) {
    const tile = el("div", undefined, "card");
    tile.append(el("span", caption, "muted"), el("strong", fmt(value)));
    deck.append(tile);
  }
  root.append(deck);
}

function stable(object) {
  if (object && typeof object === "object" && !Array.isArray(object)) {
    return "{" + Object.keys(object).sort().map(key => JSON.stringify(key) + ":" + stable(object[key])).join(",") + "}";
  }
  return Array.isArray(object) ? "[" + object.map(stable).join(",") + "]" : JSON.stringify(object);
}

function compare(a, b) {
  if (a.run_id === b.run_id) return {align: true, economics: true, inputMatch: true, reasons: []};
  const equal = (first, second) => stable(first) === stable(second);
  const reasons = [];
  const test = (value, reason) => { if (!value) reasons.push(reason); return Boolean(value); };
  const topology = test(a.topology_sha256 && a.topology_sha256 === b.topology_sha256, "network topology or electrical parameters");
  const timestamps = test(a.timestamp_count && a.timestamp_sha256 === b.timestamp_sha256, "timestamp coverage");
  const clock = test(a.clock && equal(a.clock, b.clock), "timezone / clock definition");
  const units = test(a.dt_hours && a.dt_hours === b.dt_hours && equal(a.units, b.units), "units or time step");
  const limits = settings => {
    const {legacy_proportional_validation, shedding_penalty_per_kwh, curtailment_penalty_per_kwh, ...rest} = settings || {};
    return rest;
  };
  const engineering = test(a.simulation && b.simulation && equal(limits(a.simulation), limits(b.simulation)) && equal(a.solver, b.solver),
    "solver or operating limits");
  const profileFiles = ["inputs/network.xlsx", "inputs/load_profile.csv", "inputs/pv_profile.csv"];
  const inputMatch = test(a.source && a.source === b.source && equal(a.forecast, b.forecast) && profileFiles.every(
    file => a.input_hashes?.[file] && a.input_hashes[file] === b.input_hashes?.[file]), "input profiles or provenance");
  const economics = test(a.economics && equal(a.economics, b.economics) && a.objective === b.objective &&
    a.currency === b.currency, "tariffs, currency or annual objective");
  return {align: topology && timestamps && clock && units && engineering,
    economics: economics && engineering && topology && timestamps && clock && units,
    inputMatch, reasons};
}

function checkNotice() {
  const reports = state.runs.slice(1);
  const messages = reports.map(run => {
    const status = compare(state.runs[0].manifest, run.manifest);
    return run.manifest.folder + " · " + (status.reasons.length ?
      "Differences: " + status.reasons.join(", ") + (status.align ?
        ". Hourly overlays show distinct scenarios; verify assumptions before comparing outcomes." :
        ". Use the run selector to inspect this report separately.") : "Matched data and comparison basis.");
  });
  if (current().metadata.legacy) messages.unshift("Archived run. Fields without saved records are unavailable.");
  const rawBytes = Number($("report-data").dataset.bytes);
  if (rawBytes >= 85 * 1024 * 1024) {
    messages.push("This annual report contains large hourly tables. A portable ZIP with the original files is available from the desktop dashboard menu.");
  }
  $("notice").textContent = messages.join(" ");
}

function indexRun(run) {
  if (run.manifest?.schema_version !== 1 || typeof run.manifest.run_id !== "string" ||
      !run.scenarios || !run.metadata) throw Error("Unsupported report or manifest schema.");
  for (const scenario of Object.values(run.scenarios)) {
    scenario.timeIndex = new Map(scenario.hours.map((row, index) => [row.timestamp, index]));
    scenario.eventIndex = new Map(scenario.events.map(event => [event.timestamp, event]));
  }
  return run;
}

async function unpack(data) {
  if (typeof DecompressionStream !== "function") throw Error("This report needs a browser with gzip decompression support.");
  const text = atob(data.trim());
  const bytes = Uint8Array.from(text, character => character.charCodeAt(0));
  const stream = new Blob([bytes]).stream().pipeThrough(new DecompressionStream("gzip"));
  return indexRun(await new Response(stream).json());
}

function payloadFromHtml(source) {
  const match = source.match(/<script id="report-data" type="application\/octet-stream"[^>]*>\s*([A-Za-z0-9+/=]+)\s*<\/script>/);
  if (!match) throw Error("The HTML does not contain an EE499 run.");
  return unpack(match[1]);
}

async function htmlFromZip(file) {
  // Read the central directory and stored HTML entry only. Numerical files stay untouched.
  const tailOffset = Math.max(0, file.size - 65557);
  const tail = new DataView(await file.slice(tailOffset).arrayBuffer());
  let end = tail.byteLength - 22;
  while (end >= 0 && (tail.getUint32(end, true) !== 0x06054b50 ||
         end + 22 + tail.getUint16(end + 20, true) !== tail.byteLength)) end--;
  if (end < 0) throw Error("Invalid ZIP directory.");
  const size = tail.getUint32(end + 12, true);
  const start = tail.getUint32(end + 16, true);
  if (start + size > file.size || size > 16 * 1024 * 1024) throw Error("Unsupported ZIP directory.");
  const directory = new DataView(await file.slice(start, start + size).arrayBuffer());
  let at = 0;
  while (at + 46 <= directory.byteLength && directory.getUint32(at, true) === 0x02014b50) {
    const length = directory.getUint16(at + 28, true);
    const name = new TextDecoder().decode(new Uint8Array(directory.buffer, at + 46, length));
    if (name === "dashboard.html") {
      const bytes = directory.getUint32(at + 20, true);
      const offset = directory.getUint32(at + 42, true);
      if (directory.getUint16(at + 10, true) !== 0 || directory.getUint16(at + 8, true) & 1 ||
          bytes > 240 * 1024 * 1024 || offset + 30 > start) throw Error("Use the ZIP generated by the desktop report exporter.");
      const local = new DataView(await file.slice(offset, offset + 30).arrayBuffer());
      const first = offset + 30 + local.getUint16(26, true) + local.getUint16(28, true);
      if (local.getUint32(0, true) !== 0x04034b50 || first + bytes > start) throw Error("Invalid dashboard ZIP entry.");
      return file.slice(first, first + bytes).text();
    }
    at += 46 + length + directory.getUint16(at + 30, true) + directory.getUint16(at + 32, true);
  }
  throw Error("The ZIP has no saved dashboard.");
}

async function readImport(file) {
  if (file.name.toLowerCase().endsWith(".zip")) return payloadFromHtml(await htmlFromZip(file));
  if (file.name.toLowerCase().endsWith(".html")) return payloadFromHtml(await file.text());
  const data = JSON.parse(await file.text());
  if (data.schema_version !== 1 || !data.run_id || !Array.isArray(data.summary)) {
    throw Error("Unsupported EE499 manifest.");
  }
  return indexRun({manifest: data, metadata: {legacy: true, context: {}},
    scenarios: {summary: {...empty, metrics: data.summary}},
    evaluations: [], convergence: [], economic_comparison: []});
}

function pickRun(index) {
  state.run = index;
  $("run").value = String(index);
  const keys = Object.keys(current().scenarios);
  const requested = current().metadata.optimizer?.no_bess_selected ? "no_bess" :
    (keys.includes("best_bess") && current().metadata.optimizer?.best_bess_feasible ? "best_bess" : keys[0]);
  const choice = $("scenario");
  choice.replaceChildren(...keys.map(key => new Option(current().scenarios[key].label, key)));
  state.hour = 0;
  state.equipment = ["Bus", ""];
  state.zoom = 1;
  state.offsetX = state.offsetY = 0;
  state.chartStart = state.chartEnd = null;
  state.visibleSeries = null;
  pickScenario(requested);
}

function pickScenario(key) {
  const previous = hourAt();
  state.scenario = key;
  $("scenario").value = key;
  state.hour = active().timeIndex?.get(previous) ?? 0;
  updateHour();
  checkNotice();
  render();
}

function updateHour() {
  const input = $("hour");
  input.max = Math.max(0, active().hours.length - 1);
  input.disabled = active().hours.length < 2;
  input.value = state.hour;
  $("timestamp").textContent = hourAt() || "Hourly data unavailable";
}

function setHour(timestamp) {
  const index = active().timeIndex?.get(timestamp);
  if (index === undefined) return;
  state.hour = index;
  updateHour();
  if (state.tab === "Simulation") state.redraw?.();
  else render();
}

function render() {
  const run = current();
  $("title").textContent = (run.manifest.kind === "base case" ? "Static base case" :
    run.manifest.kind === "optimization" ? "Storage optimization" :
    run.manifest.kind === "simulation" ? "Hourly simulation" : "Archived results");
  $("subtitle").textContent = [run.metadata.context?.Network, run.manifest.folder, run.manifest.solver?.name]
    .filter(Boolean).join(" · ");
  $("tabs").querySelectorAll("button").forEach(control =>
    control.setAttribute("aria-selected", control.textContent === state.tab));
  const root = $("panel");
  root.replaceChildren();
  state.redraw = null;
  ({Overview: overview, Network: network, Simulation: simulation, BESS: bess,
    Economics: economics, Optimization: optimization, Diagnostics: diagnostics})[state.tab](root);
}

function batteryName(candidate) {
  return candidate ? "Bus " + candidate.bus_id + " · " + candidate.power_rating_kw + " kW / " +
    candidate.energy_capacity_kwh + " kWh" : "Unavailable";
}

function overview(root) {
  const run = current();
  const optimizer = run.metadata.optimizer;
  const summary = section(root, "Run summary");
  const row = active().hours[state.hour] || {};
  const vMin = textMetric("voltage_min_pu", staticCase() ? row.voltage_min_pu : null);
  const vMax = textMetric("voltage_max_pu", staticCase() ? row.voltage_max_pu : null);
  cards(summary, [
    ["Selected option", optimizer ? (optimizer.no_bess_selected ? "No BESS" :
      optimizer.best_bess_feasible ? batteryName(optimizer.best_bess_candidate) : "No feasible design") :
      run.metadata.context?.["Manual BESS"] ? batteryName(run.metadata.context["Manual BESS"]) : active().label],
    ["Run voltage range (pu)", vMin === null || vMax === null ? null : fmt(vMin) + " to " + fmt(vMax)],
    ["Annual cost (USD/year)", textMetric("annual_total_cost")],
    ["Feasible", textMetric("feasible", row.feasible)]
  ]);
  kv(summary, [
    ["Run ID", run.manifest.run_id], ["Source", run.manifest.source], ["Time basis", run.manifest.clock],
    ["Selected interval", run.manifest.interval], ["Dispatch", run.metadata.context?.Dispatch],
    ["Network control", run.manifest.network_control ? nameOf(run.manifest.network_control) : null],
    ["Demand normalization", run.metadata.context?.["Demand normalization"]],
    ["Requested load energy (kWh)", textMetric("requested_load_energy_kwh")],
    ["Curtailed energy (kWh)", textMetric("curtailment_energy_kwh")],
    ["Unserved energy (kWh)", textMetric("load_shedding_energy_kwh")],
    ["Power flow", staticCase() ? row.fbs_message : null]
  ]);
  if (optimizer) {
    const best = section(root, "Evaluated alternatives");
    note(best, batteryName(optimizer.best_bess_candidate));
    economicAlternatives(best);
    if (optimizer.best_bess_replay_mismatch) note(best, optimizer.best_bess_replay_mismatch);
  }
  if (state.runs.length > 1) {
    const imports = section(root, "Imported runs");
    table(imports, ["Run", "Hourly alignment", "Profiles", "Economic basis", "Differences"],
      state.runs.filter(item => item !== run).map(item => {
        const peers = compare(run.manifest, item.manifest);
        return [item.manifest.folder, peers.align, peers.inputMatch, peers.economics, peers.reasons.join(", ") || "Matched"];
      }));
  }
  details(summary, "Saved settings and provenance", run.manifest);
}

function canvasFrame(root, caption, className) {
  const box = el("div", undefined, "chart-box");
  const canvas = el("canvas", undefined, className);
  canvas.setAttribute("role", "img");
  canvas.setAttribute("aria-label", caption);
  const hint = el("div", caption, "chart-caption");
  box.append(canvas, hint);
  root.append(box);
  return {canvas, hint};
}

function sizeCanvas(canvas) {
  const width = canvas.clientWidth || 720, height = canvas.clientHeight || 300;
  const scale = Math.min(2, window.devicePixelRatio || 1);
  canvas.width = Math.round(width * scale);
  canvas.height = Math.round(height * scale);
  const context = canvas.getContext("2d");
  context.setTransform(scale, 0, 0, scale, 0, 0);
  context.fillStyle = "#fff";
  context.fillRect(0, 0, width, height);
  context.font = "12px system-ui, sans-serif";
  return {context, width, height};
}

function png(root, canvas, name) {
  const save = button("Save chart PNG", () => {
    canvas.toBlob(blob => {
      if (!blob) return void ($("notice").textContent = "PNG export failed in this browser.");
      const url = URL.createObjectURL(blob);
      const link = el("a");
      link.download = name + ".png";
      link.href = url;
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    });
  });
  root.append(save);
}

function comparableScenarios() {
  return state.runs.flatMap((run, runIndex) => {
    if (run !== current() && !compare(manifest(), run.manifest).align) return [];
    return Object.entries(run.scenarios).filter(([, scenario]) => scenario.hours.length).map(([key, scenario]) => ({
      id: runIndex + ":" + key, label: (run === current() ? "" : run.manifest.folder + " · ") + scenario.label, scenario
    }));
  });
}

function entityAt(scenario, type, id, timestamp) {
  const index = scenario.timeIndex?.get(timestamp);
  const entity = (type === "Bus" ? scenario.buses : scenario.branches)[id];
  if (!entity || index === undefined) return {};
  return Object.fromEntries(Object.entries(entity).map(([field, values]) => [field, values[index]]));
}

function network(root) {
  const run = current();
  const geometry = run.metadata.layout;
  const top = run.metadata.topology;
  if (!geometry || !top || !active().hours.length) {
    note(root, "Saved schematic layout or hourly network values unavailable.");
    return;
  }
  const bar = el("div", undefined, "chart-controls");
  const objects = [["", "Select a bus or line"], ...top.buses.map(bus => ["Bus:" + bus.bus_id, "Bus " + bus.bus_id]),
    ...top.lines.map(line => ["Line:" + line.line_id, "Line " + line.line_id])];
  const object = select(objects, state.equipment[0] + ":" + state.equipment[1]);
  const peers = comparableScenarios().filter(peer => peer.scenario !== active());
  const other = select([["", "None"], ...peers.map(peer => [peer.id, peer.label])], state.networkPeer);
  const overlay = el("input");
  overlay.type = "checkbox";
  overlay.checked = Boolean(state.sheddingOverlay);
  overlay.addEventListener("change", () => { state.sheddingOverlay = overlay.checked; draw(); });
  bar.append(label("Equipment", object), label("Compare voltage by bus", other), label("Show load shedding", overlay),
    button("Zoom in", () => { state.zoom *= 1.25; draw(); }),
    button("Zoom out", () => { state.zoom /= 1.25; draw(); }),
    button("Fit feeder", () => { state.zoom = 1; state.offsetX = state.offsetY = 0; draw(); }));
  root.append(bar);
  const {canvas, hint} = canvasFrame(root, "Use the wheel to zoom, drag to pan, and select a bus or line for details.", "network");
  const detail = el("div");
  root.append(detail);
  png(root, canvas, "feeder");
  const low = run.metadata.simulation?.voltage_min_pu;
  const high = run.metadata.simulation?.voltage_max_pu;
  note(root, "Voltage bands (pu) · Below " + fmt(low) + " amber · Within limits teal · Above " +
    fmt(high) + " red · Unavailable or nonconverged gray.");
  let targets = [], segments = [];
  let drag = null;
  const positions = Object.values(geometry.positions);
  const xs = positions.map(position => position[0]), ys = positions.map(position => position[1]);
  const left = Math.min(...xs), right = Math.max(...xs), topY = Math.min(...ys), bottom = Math.max(...ys);

  function draw() {
    const {context: ctx, width, height} = sizeCanvas(canvas);
    const scale = Math.max(.015, Math.min((width - 60) / Math.max(1, right - left),
      (height - 70) / Math.max(160, bottom - topY))) * state.zoom;
    const xy = ([x, y]) => [width / 2 + (x - (right + left) / 2) * scale + state.offsetX,
      height / 2 + (y - (bottom + topY) / 2) * scale + state.offsetY];
    targets = [];
    segments = [];
    const [type, id] = state.equipment;
    for (const line of top.lines) {
      const route = geometry.routes[line.line_id];
      if (!route?.length) continue;
      const points = route.map(xy);
      ctx.strokeStyle = type === "Line" && id === line.line_id ? "#087c80" : "#78929d";
      ctx.lineWidth = type === "Line" && id === line.line_id ? 3 : 1.3;
      ctx.beginPath();
      points.forEach(([x, y], index) => {
        if (index) {
          ctx.lineTo(x, y);
          segments.push([line.line_id, points[index - 1], points[index]]);
        } else ctx.moveTo(x, y);
      });
      ctx.stroke();
    }
    for (const bus of top.buses) {
      const key = String(bus.bus_id);
      const position = geometry.positions[key];
      if (!position) continue;
      const [x, y] = xy(position);
      targets.push([key, x, y]);
      const data = entityAt(active(), "Bus", key, hourAt());
      const voltage = data.voltage_pu;
      const converged = active().hours[state.hour]?.converged;
      ctx.fillStyle = !number(voltage) || data.diagnostic_only || converged === false || !number(low) || !number(high) ?
        "#879aa2" : voltage < low ? "#b56a05" : voltage > high ? "#b84c37" : "#087c80";
      ctx.beginPath();
      ctx.arc(x, y, type === "Bus" && id === key ? 8 : 5, 0, Math.PI * 2);
      ctx.fill();
      if (state.sheddingOverlay && data.shedding_kw > 0 && !data.diagnostic_only) {
        const requested = data.requested_load_kw ?? (data.load_input_kw + data.shedding_kw);
        ctx.strokeStyle = "#79568c";
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.arc(x, y, 9 + 8 * Math.min(1, data.shedding_kw / requested), 0, Math.PI * 2);
        ctx.stroke();
      }
      ctx.fillStyle = "#102c3a";
      const installed = state.scenario === "best_bess" ? run.metadata.optimizer?.best_bess_candidate :
        state.scenario === "." ? run.metadata.context?.["Manual BESS"] : null;
      ctx.font = "11px system-ui, sans-serif";
      const icons = [bus.is_slack ? "Grid" : null, run.metadata.pv_buses?.includes(bus.bus_id) ? "☀ PV" : null,
        installed?.bus_id === bus.bus_id ? "▣ BESS" : null].filter(Boolean);
      ctx.fillText("B" + key, x + 8, y - 6);
      if (icons.length) ctx.fillText(icons.join(" · "), x + 8, y + 12);
    }
  }

  function showEquipment() {
    detail.replaceChildren();
    const [type, id] = state.equipment;
    if (!id) return;
    const data = entityAt(active(), type, id, hourAt());
    const object = type === "Bus" ? top.buses.find(bus => String(bus.bus_id) === id) :
      top.lines.find(line => line.line_id === id);
    const otherRun = peers.find(item => item.id === other.value);
    const compared = otherRun ? entityAt(otherRun.scenario, type, id, hourAt()) : {};
    const entries = type === "Bus" ?
      [["Voltage (pu)", data.voltage_pu, compared.voltage_pu], ["Pre-control voltage (pu)", data.pre_control_voltage_pu, compared.pre_control_voltage_pu],
        ["Requested load (kW)", data.requested_load_kw, compared.requested_load_kw], ["Delivered load (kW)", data.load_input_kw, compared.load_input_kw],
        ["Requested load (kvar)", data.requested_load_kvar, compared.requested_load_kvar], ["Delivered load (kvar)", data.load_input_kvar, compared.load_input_kvar],
        ["Available PV (kW)", data.available_pv_kw, compared.available_pv_kw], ["Delivered PV (kW)", data.pv_input_kw, compared.pv_input_kw],
        ["Battery injection (kW)", data.bess_input_kw, compared.bess_input_kw],
        ["Shedding (kW)", data.shedding_kw, compared.shedding_kw], ["Shedding (kvar)", data.shedding_kvar, compared.shedding_kvar],
        ["Curtailment (kW)", data.curtailment_kw, compared.curtailment_kw]] :
      [["Current (A)", data.current_a, compared.current_a], ["Sending power (kW)", data.sending_p_kw ?? data.p_kw, compared.sending_p_kw ?? compared.p_kw],
        ["Reactive power (kvar)", data.sending_q_kvar ?? data.q_kvar, compared.sending_q_kvar ?? compared.q_kvar],
        ["Loss (kW)", data.loss_p_kw ?? data.loss_kw, compared.loss_p_kw ?? compared.loss_kw]];
    const pane = section(detail, type + " " + id + (object?.name ? " · " + object.name : ""));
    if (otherRun) table(pane, ["Measure", active().label, otherRun.label, "Δ active − comparison"],
      entries.map(([key, actual, peer]) => [key, actual, peer, number(actual) && number(peer) ? actual - peer : null]));
    else kv(pane, entries.map(([key, actual]) => [key, actual]));
    if (type === "Line") note(pane, "Bus " + object?.from_bus + " to " + object?.to_bus + " · Ampacity " + fmt(object?.ampacity_a) + " A");
    if (data.diagnostic_only || active().hours[state.hour]?.converged === false) note(pane, "Nonconverged. Last electrical iterate is diagnostic only.");
  }

  function selection(type, id) {
    state.equipment = [type, id];
    object.value = type + ":" + id;
    draw();
    showEquipment();
  }
  object.addEventListener("change", () => {
    if (!object.value) return selection("Bus", "");
    const separator = object.value.indexOf(":");
    selection(object.value.slice(0, separator), object.value.slice(separator + 1));
  });
  other.addEventListener("change", () => { state.networkPeer = other.value; showEquipment(); });
  canvas.addEventListener("wheel", event => { event.preventDefault(); state.zoom = Math.max(.15, Math.min(15,
    state.zoom * (event.deltaY < 0 ? 1.12 : .9))); draw(); }, {passive: false});
  canvas.addEventListener("pointerdown", event => { drag = [event.offsetX, event.offsetY, state.offsetX, state.offsetY];
    canvas.setPointerCapture(event.pointerId); });
  canvas.addEventListener("pointermove", event => {
    if (!drag) return;
    state.offsetX = drag[2] + event.offsetX - drag[0];
    state.offsetY = drag[3] + event.offsetY - drag[1];
    draw();
  });
  canvas.addEventListener("pointerup", event => {
    if (!drag) return;
    const clicked = Math.hypot(event.offsetX - drag[0], event.offsetY - drag[1]) < 6;
    drag = null;
    if (!clicked) return;
    const px = event.offsetX, py = event.offsetY;
    const target = targets.find(([, x, y]) => Math.hypot(x - px, y - py) < 13);
    if (target) return selection("Bus", target[0]);
    const line = segments.find(([, [x, y], [x2, y2]]) => {
      const fraction = Math.max(0, Math.min(1, ((px - x) * (x2 - x) + (py - y) * (y2 - y)) /
        ((x2 - x) ** 2 + (y2 - y) ** 2 || 1)));
      return Math.hypot(px - x - fraction * (x2 - x), py - y - fraction * (y2 - y)) < 7;
    });
    if (line) selection("Line", line[0]);
  });
  hint.textContent = (hourAt() || "") + " · Wheel to zoom, drag to pan, select equipment for exact values.";
  state.redraw = draw;
  draw();
  showEquipment();
}

const variables = [
  ["Served load (kW)", "load_input_kw", "average"], ["PV dispatched (kW)", "pv_input_kw", "average"],
  ["Grid import (kW)", "grid_import_kw", "average"], ["Grid export (kW)", "grid_export_kw", "average"],
  ["Peak grid import (kW)", "grid_import_kw", "max"], ["Grid import energy (kWh)", "grid_import_kw", "energy"],
  ["Grid export energy (kWh)", "grid_export_kw", "energy"], ["Grid reactive power (kvar)", "slack_q_kvar", "average"],
  ["Loss (kW)", "loss_p_kw", "average"], ["Energy lost (kWh)", "loss_p_kw", "energy"],
  ["Lowest voltage (pu)", "voltage_min_pu", "min"], ["Highest voltage (pu)", "voltage_max_pu", "max"],
  ["Curtailment (kW)", "curtailment_kw", "average"], ["Curtailed energy (kWh)", "curtailment_kw", "energy"],
  ["Load shedding (kW)", "shedding_kw", "average"], ["Unserved energy (kWh)", "shedding_kw", "energy"],
  ["Bus voltage (pu)", "voltage_pu", "min", "Bus"], ["Bus load (kW)", "load_input_kw", "average", "Bus"],
  ["Bus PV (kW)", "pv_input_kw", "average", "Bus"], ["Bus BESS injection (kW)", "bess_input_kw", "average", "Bus"],
  ["Line current (A)", "current_a", "max", "Line"], ["Line power (kW)", "sending_p_kw", "average", "Line"],
  ["Line reactive power (kvar)", "sending_q_kvar", "average", "Line"], ["Line loss (kW)", "loss_p_kw", "average", "Line"]
];
const aggregationLabel = {average: "mean power or current", max: "period maximum", min: "period minimum",
  last: "end-of-period sample", energy: "sum of hourly power × step duration"};

function periodKey(timestamp, cadence) {
  if (cadence === "Hourly") return timestamp;
  const day = timestamp.slice(0, 10);
  if (cadence === "Daily") return day;
  if (cadence === "Monthly") return day.slice(0, 7);
  const monday = new Date(day + "T00:00:00Z");
  if (!Number.isFinite(monday.valueOf())) return timestamp;
  monday.setUTCDate(monday.getUTCDate() - (monday.getUTCDay() + 6) % 7);
  return monday.toISOString().slice(0, 10);
}

function bucketed(records, cadence, method) {
  const bins = new Map();
  for (const [timestamp, value, hours] of records) {
    const key = periodKey(timestamp, cadence);
    if (!bins.has(key)) bins.set(key, {first: timestamp, total: 0, hours: 0, max: -Infinity, min: Infinity, last: null, incomplete: false});
    const bin = bins.get(key);
    bin.last = value;
    if (!number(value) || (method === "energy" && !number(hours))) bin.incomplete = true;
    else {
      const weight = number(hours) ? hours : 1;
      bin.total += value * weight;
      bin.hours += weight;
      bin.max = Math.max(bin.max, value);
      bin.min = Math.min(bin.min, value);
    }
  }
  return [...bins].map(([label, bin]) => ({
    label, timestamp: bin.first,
    value: method === "last" ? bin.last : bin.incomplete || !bin.hours ? null :
      {energy: bin.total, average: bin.total / bin.hours, min: bin.min, max: bin.max}[method]
  }));
}

function plot(root, series, title) {
  const {canvas, hint} = canvasFrame(root, title);
  if (series.length > 1) {
    const legend = el("div", undefined, "chart-legend");
    for (const [index, set] of series.entries()) {
      const key = el("span", set.label);
      key.style.borderColor = set.color || colors[index % colors.length];
      legend.append(key);
    }
    root.append(legend);
  }
  png(root, canvas, title.toLowerCase().replace(/[^a-z0-9]+/g, "-"));
  const feature = new Map();
  for (const set of series) for (const point of set.points) feature.set(point.label, point.timestamp);
  const ticks = [...feature.keys()];
  const data = series.map(set => new Map(set.points.map(point => [point.label, point.value])));
  let lo = 0, hi = Math.max(0, ticks.length - 1), hover = null, drag = null, plotWidth = 1;
  const drawn = canvas.getContext("2d");
  if (!drawn) return note(root, "Canvas graphics unavailable.");
  const nearest = pixel => Math.max(lo, Math.min(hi, Math.round(lo +
    (pixel - 68) * Math.max(1, hi - lo) / plotWidth)));

  function draw() {
    const {context: ctx, width, height} = sizeCanvas(canvas);
    plotWidth = Math.max(30, width - 94);
    const plotHeight = height - 64;
    const range = ticks.slice(lo, hi + 1);
    const visible = series.map((set, index) => ({...set, values: range.map(key => data[index].get(key))}));
    let min = Infinity, max = -Infinity;
    for (const set of visible) for (const value of set.values) if (number(value)) {
      min = Math.min(min, value);
      max = Math.max(max, value);
    }
    if (!Number.isFinite(min)) {
      ctx.fillStyle = "#506876";
      ctx.fillText("No recorded values in this selection", 22, 40);
      hint.textContent = title + " · Unavailable";
      return;
    }
    if (min === max) {
      const margin = Math.max(.01, Math.abs(min) * .03);
      min -= margin;
      max += margin;
    }
    const x = index => 68 + index * plotWidth / Math.max(1, range.length - 1);
    const y = value => 20 + (max - value) * plotHeight / (max - min);
    for (let index = 0; index <= 4; index++) {
      const value = min + (max - min) * index / 4;
      const line = y(value);
      ctx.strokeStyle = "#e1e9eb";
      ctx.beginPath();
      ctx.moveTo(68, line);
      ctx.lineTo(width - 26, line);
      ctx.stroke();
      ctx.fillStyle = "#506876";
      ctx.fillText(fmt(value, 4), 7, line + 4, 57);
    }
    for (const [setIndex, set] of visible.entries()) {
      ctx.strokeStyle = set.color || colors[setIndex % colors.length];
      ctx.fillStyle = ctx.strokeStyle;
      ctx.lineWidth = 1.7;
      ctx.beginPath();
      let prev = false;
      const stride = Math.max(1, Math.ceil(set.values.length / Math.max(500, plotWidth * 2)));
      // Preserve local extrema and actual gaps while sampling the viewport.
      for (let index = 0; index < set.values.length; index += stride) {
        const chunk = set.values.slice(index, index + stride);
        const finite = chunk.map((value, offset) => ({value, offset})).filter(point => number(point.value));
        if (!finite.length || finite.length !== chunk.length) prev = false;
        if (!finite.length) continue;
        const lowest = finite.reduce((a, b) => a.value <= b.value ? a : b);
        const highest = finite.reduce((a, b) => a.value >= b.value ? a : b);
        for (const point of [...new Set([finite[0], lowest, highest, finite.at(-1)])].sort((a, b) => a.offset - b.offset)) {
          const px = x(index + point.offset), py = y(point.value);
          if (!prev) { ctx.moveTo(px, py); ctx.fillRect(px - 1, py - 1, 2, 2); }
          else ctx.lineTo(px, py);
          prev = true;
        }
      }
      ctx.stroke();
    }
    ctx.fillStyle = "#506876";
    const last = range.at(-1);
    ctx.fillText(range[0] || "", 68, height - 20, plotWidth * .48);
    if (last !== range[0]) {
      ctx.textAlign = "right";
      ctx.fillText(last || "", width - 23, height - 20, plotWidth * .48);
      ctx.textAlign = "left";
    }
    const cursor = hover ?? ticks.findIndex(key => feature.get(key) === hourAt());
    if (cursor >= lo && cursor <= hi) {
      ctx.beginPath();
      ctx.strokeStyle = "#738894";
      ctx.lineWidth = 1;
      ctx.moveTo(x(cursor - lo), 15);
      ctx.lineTo(x(cursor - lo), 24 + plotHeight);
      ctx.stroke();
      hint.textContent = ticks[cursor] + " · " + series.map((set, index) =>
        set.label + " " + fmt(data[index].get(ticks[cursor]))).join(" · ");
    } else hint.textContent = title + " · Wheel to zoom, drag to pan, click to select a saved hour.";
  }

  canvas.addEventListener("pointermove", event => {
    if (drag) {
      const span = drag.hi - drag.lo;
      const offset = Math.round((drag.x - event.offsetX) * span / plotWidth);
      lo = Math.max(0, Math.min(ticks.length - 1 - span, drag.lo + offset));
      hi = lo + span;
    } else hover = nearest(event.offsetX);
    draw();
  });
  canvas.addEventListener("pointerleave", () => { hover = null; draw(); });
  canvas.addEventListener("pointerdown", event => {
    drag = {x: event.offsetX, lo, hi};
    canvas.setPointerCapture(event.pointerId);
  });
  canvas.addEventListener("pointerup", event => {
    if (drag && Math.abs(event.offsetX - drag.x) < 4) setHour(feature.get(ticks[nearest(event.offsetX)]));
    drag = null;
  });
  canvas.addEventListener("wheel", event => {
    if (ticks.length < 2) return;
    event.preventDefault();
    const center = nearest(event.offsetX);
    const oldSpan = hi - lo, span = Math.min(ticks.length - 1, Math.max(1, Math.round(oldSpan *
      (event.deltaY < 0 ? .75 : 1.35))));
    lo = Math.max(0, Math.min(ticks.length - 1 - span, Math.round(center - span / 2)));
    hi = lo + span;
    draw();
  }, {passive: false});
  canvas.addEventListener("dblclick", () => { lo = 0; hi = Math.max(0, ticks.length - 1); draw(); });
  state.redraw = draw;
  draw();
}

function physicalValue(row, field) {
  if (row.diagnostic_only || row.converged === false) return null;
  if (["grid_import_kw", "grid_export_kw"].includes(field)) return number(row.slack_p_kw) ?
    Math.max(0, row.slack_p_kw * (field === "grid_import_kw" ? 1 : -1)) : null;
  return row[field];
}

function simulation(root) {
  if (!active().hours.length || staticCase()) {
    note(root, "Hourly simulation data unavailable for this view. Use Network for a saved static snapshot.");
    return;
  }
  const widget = el("div", undefined, "chart-controls");
  const choose = select(variables.map(([title], index) => [index, title]), state.variable ?? 0);
  const cadence = select(["Hourly", "Daily", "Weekly", "Monthly"].map(value => [value, value]), state.cadence);
  const firstDay = active().hours[0].timestamp.slice(0, 10);
  const lastDay = active().hours.at(-1).timestamp.slice(0, 10);
  const start = el("input"), end = el("input");
  start.type = end.type = "date";
  start.value = state.chartStart || firstDay;
  end.value = state.chartEnd || lastDay;
  const peers = comparableScenarios();
  const entityBox = el("div", undefined, "chart-controls");
  const legend = el("div", undefined, "chart-controls");
  let chart = el("div");
  widget.append(label("Variable", choose), label("Resolution", cadence), label("Start date", start), label("End date", end));
  root.append(widget, entityBox, legend, chart);
  const selected = state.visibleSeries || new Set(peers.filter(peer => peer.scenario === active() ||
    current().scenarios.no_bess === peer.scenario || current().scenarios.best_bess === peer.scenario).map(peer => peer.id));
  peers.forEach(peer => {
    const toggle = el("input");
    toggle.type = "checkbox";
    toggle.checked = selected.has(peer.id);
    toggle.addEventListener("change", () => {
      if (toggle.checked) selected.add(peer.id); else selected.delete(peer.id);
      state.visibleSeries = selected;
      redraw();
    });
    legend.append(label(peer.label, toggle, "toggle"));
  });

  function redraw() {
    state.variable = Number(choose.value);
    state.cadence = cadence.value;
    state.chartStart = start.value;
    state.chartEnd = end.value;
    const [title, field, method, type] = variables[state.variable];
    const series = [];
    const ids = type ? (state.chartEntities || []).slice(0, 6) : [""];
    for (const peer of peers.filter(item => selected.has(item.id))) for (const id of ids) {
      const scenario = peer.scenario;
      const entity = type === "Bus" ? scenario.buses[id] : scenario.branches[id];
      const records = [];
      for (const row of active().hours) {
        const day = row.timestamp.slice(0, 10);
        if ((start.value && day < start.value) || (end.value && day > end.value)) continue;
        const index = scenario.timeIndex.get(row.timestamp);
        const candidate = scenario.hours[index];
        const value = type ? (index === undefined || entity?.diagnostic_only?.[index] ? null :
          entity?.[field]?.[index]) : candidate ? physicalValue(candidate, field) : null;
        records.push([row.timestamp, value, candidate?.dt_hours]);
      }
      series.push({label: peer.label + (type ? " · " + type + " " + id : ""),
        points: bucketed(records, cadence.value, method)});
    }
    const next = el("div");
    chart.replaceWith(next);
    chart = next;
    if (!series.length) note(chart, "Select at least one stored series.");
    else plot(chart, series, title);
    note(chart, cadence.value + " · " + (cadence.value === "Hourly" && method !== "energy" ? "saved hourly values" :
      aggregationLabel[method]) + " · " + fmt(manifest().clock) +
      (series.length > 1 ? " · " + series.map((set, index) => (index + 1) + " " + set.label).join(" | ") : ""));
  }

  function changeEntities() {
    entityBox.replaceChildren();
    const type = variables[Number(choose.value)][3];
    if (type) {
      const entities = Object.keys(type === "Bus" ? active().buses : active().branches);
      const control = select(entities.map(id => [id, type + " " + id]));
      control.multiple = true;
      control.size = Math.min(4, entities.length || 1);
      state.chartEntities = (state.chartEntities || []).filter(id => entities.includes(id));
      if (!state.chartEntities.length && entities.length) state.chartEntities = [entities[0]];
      [...control.options].forEach(option => { option.selected = state.chartEntities.includes(option.value); });
      control.addEventListener("change", () => {
        state.chartEntities = [...control.selectedOptions].map(option => option.value).slice(0, 6);
        [...control.options].forEach(option => { option.selected = state.chartEntities.includes(option.value); });
        redraw();
      });
      entityBox.append(label(type + " series (choose up to six)", control));
    }
    redraw();
  }
  choose.addEventListener("change", changeEntities);
  [cadence, start, end].forEach(control => control.addEventListener("change", redraw));
  changeEntities();
}

function bess(root) {
  const scenario = active();
  if (!scenario.hours.some(row => number(row.bess_accepted_soc))) {
    note(root, "Saved hourly battery records unavailable for this alternative.");
    return;
  }
  const widget = el("div", undefined, "chart-controls");
  const variables = select([["power", "Battery injection (kW)"], ["soc", "State of charge (%)"],
    ["energy", "Stored energy (kWh)"], ["headroom", "Physical power headroom (kW)"]], state.bessVariable);
  widget.append(label("Battery series", variables));
  root.append(widget);
  const box = el("div");
  root.append(box);
  const definitions = {
    power: [["Requested", row => row.bess_request_kw], ["Accepted", (row, event) =>
      event ? event.accepted_kw : row.converged ? row.bess_trial_power_kw : null], ["Before terminal adjustment", (_, event) => event?.planned_kw]],
    soc: [["SOC at start", row => number(row.bess_soc_before) ? 100 * row.bess_soc_before : null],
      ["SOC at end", row => number(row.bess_accepted_soc) && row.converged ? 100 * row.bess_accepted_soc : null]],
    energy: [["Stored energy at end", row => row.converged ? row.bess_accepted_energy_kwh : null],
      ["Terminal target", (_, event) => event?.terminal_target_kwh]],
    headroom: [["Charge (magnitude)", (_, event) => event?.charge_available_kw],
      ["Discharge", (_, event) => event?.discharge_available_kw]]
  };
  function chart() {
    state.bessVariable = variables.value;
    box.replaceChildren();
    const title = variables.selectedOptions[0].textContent;
    plot(box, definitions[variables.value].map(([label, get]) => ({label,
      points: scenario.hours.map(row => ({label: row.timestamp, timestamp: row.timestamp,
        value: get(row, scenario.eventIndex.get(row.timestamp))}))})), title);
    const row = scenario.hours[state.hour];
    const event = eventAt();
    const hour = section(box, hourAt() || "Selected hour");
    kv(hour, [
      ["Request (kW)", row?.bess_request_kw], ["Accepted (kW)", event ? event.accepted_kw :
        row?.converged ? row.bess_trial_power_kw : null],
      ["Injection before residual controls (kW)", event?.after_bess_kw],
      ["Energy before (kWh)", event?.energy_before_kwh], ["Energy after (kWh)", event?.energy_after_kwh],
      ["Remaining closure hours", event?.terminal_remaining_hours], ["Terminal target (kWh)", event?.terminal_target_kwh],
      ["Tested remaining electrical charge headroom (kWh)", event?.terminal_charge_headroom_kwh],
      ["Tested remaining electrical discharge headroom (kWh)", event?.terminal_discharge_headroom_kwh],
      ["Cause", event?.reason_codes?.join(", ") || row?.bess_limit_reason]
    ]);
    if (event?.risks?.length) table(hour, ["Look-ahead hour", "Uncontrolled constraints", "Tested injection (kW)"],
      event.risks.map(risk => [risk.timestamp, risk.converged ? risk.constraints.join(", ") : "FBS failed",
        risk.tested_action_kw.join(", ") || null]));
    if (event?.projected_stress_actions?.length) {
      note(hour, "Projection uses the current plan and tested actions for stressed hours. Later hours are planned again as battery state changes.");
      table(hour, ["Stressed hour", "Projected injection (kW)", "Projected energy (kWh)", "Realized injection (kW)"],
        event.projected_stress_actions.map(action => [action.timestamp, action.forecast_kw, action.forecast_energy_kwh,
          scenario.eventIndex.get(action.timestamp)?.accepted_kw]));
    }
  }
  variables.addEventListener("change", chart);
  chart();
}

function economicAlternatives(root) {
  const run = current();
  const base = metricsOf(run.scenarios.no_bess?.metrics || []);
  const best = metricsOf(run.scenarios.best_bess?.metrics || []);
  const comparisons = run.economic_comparison;
  if (!comparisons.length) return note(root, "Matched economic alternatives unavailable.");
  table(root, ["Alternative", "Annual cost (USD/year)", "Feasible", "Selected"],
    comparisons.map(row => [row.alternative, row.annual_cost, row.feasible, row.selected]));
  const match = !run.metadata.optimizer?.best_bess_replay_mismatch;
  const savings = match && base.feasible && best.feasible && number(base.annual_total_cost) && number(best.annual_total_cost) ?
    base.annual_total_cost - best.annual_total_cost : null;
  const avoided = match && base.feasible && best.feasible && number(base.annual_shedding_cost) && number(best.annual_shedding_cost) ?
    base.annual_shedding_cost - best.annual_shedding_cost : null;
  const reduction = key => match && base.feasible && best.feasible && base[key] > 0 && number(best[key]) ?
    (base[key] - best[key]) / base[key] * 100 : null;
  const operatingBenefit = number(savings) && number(best.annual_capital_recovery) ?
    savings + best.annual_capital_recovery : null;
  const payback = savings > 0 && operatingBenefit > 0 && number(best.bess_cost) ? best.bess_cost / operatingBenefit : null;
  kv(root, [["Net annual savings from best tested BESS (USD/year)", savings],
    ["Avoided shedding cost (USD/year)", avoided], ["Simple payback (years)", payback ?? "N/A"]]);
  const targets = [["Unserved energy", "load_shedding_energy_kwh", 5], ["Annual cost", "annual_total_cost", 5],
    ["Curtailed energy", "curtailment_energy_kwh", null]];
  table(root, ["Best feasible BESS vs No BESS", "Reduction (%)", "Annual target (%)", "Target met"],
    targets.map(([name, key, target]) => {
      const change = reduction(key);
      return [name, change, target, change === null || target === null ? null : change >= target];
    }));
}

function economics(root, printable = false) {
  const run = current();
  const report = section(root, "Economic results");
  const m = metricsOf(active().metrics);
  const prices = run.manifest.economics;
  const components = [
    ["Upfront battery CAPEX (USD)", "bess_cost"],
    ["Capital recovery (USD/year)", "annual_capital_recovery"], ["Fixed O&M (USD/year)", "annual_fixed_om"],
    ["Annualized ownership (USD/year)", "annualized_bess_cost"],
    ["Grid purchases (USD/year)", "annual_grid_purchases"], ["Export credit (USD/year)", "annual_export_credit"],
    ["Net grid cost (USD/year)", "annual_grid_cost"],
    ["Curtailment penalty (USD/year)", "annual_curtailment_cost"], ["Unserved load penalty (USD/year)", "annual_shedding_cost"],
    ["Terminal energy adjustment (USD/year)", "annual_terminal_energy_cost"],
    ["Total annual cost (USD/year)", "annual_total_cost"]
  ];
  const scenarios = [active(), ...Object.values(run.scenarios).filter(item => item !== active() && item.metrics.length)];
  const values = scenarios.map(item => metricsOf(item.metrics));
  table(report, ["Component", ...scenarios.map(item => item.label)],
    components.map(([text, field]) => [text, ...values.map(item => item[field])]));
  const rate = prices?.discount_rate, lifetime = prices?.lifetime_years;
  const crf = number(rate) && number(lifetime) && lifetime > 0 ? (rate ? rate / (1 - (1 + rate) ** -lifetime) : 1 / lifetime) : null;
  kv(report, [
    ["Annualization basis", m.annualization_basis], ["Grid import tariff (USD/kWh)", prices?.grid_import_tariff_per_kwh],
    ["Grid export tariff (USD/kWh)", prices?.grid_export_tariff_per_kwh], ["Value of lost load (USD/kWh)", prices?.shedding_penalty_per_kwh],
    ["Curtailment penalty (USD/kWh)", prices?.curtailment_penalty_per_kwh],
    ["Discount rate (%)", number(rate) ? rate * 100 : null], ["Lifetime (years)", lifetime], ["Capital recovery factor", crf],
    ["Terminal energy policy", prices?.terminal_policy]
  ]);
  economicAlternatives(report);
  if (!printable && values.some(item => number(item.annual_total_cost))) {
    const chart = section(root, "Annual cost contributions");
    const {canvas} = canvasFrame(chart, "USD/year · Negative bars are credits.");
    const names = components.filter(([, key]) => !["bess_cost", "annualized_bess_cost", "annual_grid_cost", "annual_total_cost"].includes(key));
    const draw = () => {
      const {context: ctx, width, height} = sizeCanvas(canvas);
      const left = Math.min(220, width * .39), span = Math.max(15, width - left - 24);
      const extrema = values.flatMap(item => names.map(([, field]) => item[field])).filter(number);
      const min = Math.min(0, ...extrema), max = Math.max(1, ...extrema);
      const x = value => left + (value - min) * span / (max - min);
      const step = (height - 20) / names.length;
      names.forEach(([text, key], row) => {
        const top = row * step + 7;
        ctx.fillStyle = "#102c3a";
        ctx.fillText(text, 7, top + 12, left - 12);
        values.forEach((value, index) => {
          const cost = value[key];
          if (!number(cost)) return;
          const y = top + index * Math.min(12, (step - 4) / values.length);
          ctx.fillStyle = colors[index % colors.length];
          ctx.fillRect(Math.min(x(0), x(cost)), y, Math.max(1, Math.abs(x(cost) - x(0))), 7);
        });
      });
      ctx.strokeStyle = "#8e9aa2";
      ctx.beginPath(); ctx.moveTo(x(0), 3); ctx.lineTo(x(0), height - 8); ctx.stroke();
    };
    draw();
    state.redraw = draw;
    png(chart, canvas, "annual-cost-contributions");
  }
  if (!printable && state.runs.length > 1) {
    const cross = section(root, "Saved prices by run");
    const fields = ["grid_import_tariff_per_kwh", "grid_export_tariff_per_kwh", "shedding_penalty_per_kwh",
      "curtailment_penalty_per_kwh", "annualization_basis"];
    table(cross, ["Run", "Import tariff", "Export tariff", "Shedding penalty", "Curtailment penalty", "Annualization", "Basis matched"],
      state.runs.map(other => [other.manifest.folder, ...fields.map(field => other.manifest.economics?.[field]),
        compare(run.manifest, other.manifest).economics]));
  }
}

function optimization(root) {
  const run = current();
  const meta = run.metadata.optimizer;
  if (!run.evaluations.length && !meta) return note(root, "Optimizer evaluations unavailable for this run.");
  const summary = section(root, "Selection");
  kv(summary, [["Selected", meta?.no_bess_selected ? "No BESS" : meta?.best_bess_feasible ?
    batteryName(meta.best_bess_candidate) : null],
    ["Best evaluated feasible BESS", batteryName(meta?.best_bess_candidate)],
    ["Feasible BESS candidates", meta?.feasible_bess_candidates],
    ["Candidates with reserve violations", meta?.reserve_rejected_bess_candidates],
    ["Decision", meta?.decision_message], ["Replay check", meta?.best_bess_replay_mismatch]]);
  economicAlternatives(summary);
  if (run.convergence.length) {
    const convergence = section(root, "Convergence");
    plot(convergence, [{label: "Best annual cost", points: run.convergence.map(row => ({
      label: nameOf(row.axis || "Iteration") + " " + row.index, timestamp: "", value: row.best_annual_cost
    }))}], "Best annual cost (USD/year)");
  }
  const list = section(root, "Candidate rankings");
  const controls = el("div", undefined, "chart-controls");
  const buses = [...new Set(run.evaluations.map(row => row.bus_id))].sort((a, b) => a - b);
  const bus = select([["", "All buses"], ...buses.map(value => [value, "Bus " + value])]);
  const status = select([["", "All candidates"], ["yes", "Feasible"], ["no", "Infeasible"]]);
  const size = select([["power_rating_kw", "Power (kW)"], ["energy_capacity_kwh", "Energy (kWh)"]]);
  const minimum = el("input"), maximum = el("input");
  minimum.type = maximum.type = "number";
  const order = select([["annual_cost", "Annual cost"], ["bus_id", "Bus"], ["power_rating_kw", "Power"],
    ["energy_capacity_kwh", "Energy"], ["feasible", "Feasible first"]]);
  controls.append(label("Bus", bus), label("Feasibility", status), label("Filter size by", size),
    label("Min", minimum), label("Max", maximum), label("Sort by", order));
  list.append(controls);
  const inspection = el("div");
  const chart = section(list, "Evaluated location and sizing");
  const axis = select([["bus_id", "Bus"], ["power_rating_kw", "Power (kW)"], ["energy_capacity_kwh", "Energy (kWh)"]], "power_rating_kw");
  chart.append(label("Horizontal axis", axis));
  const {canvas, hint} = canvasFrame(chart, "Energy capacity (kWh) · Teal feasible · Red infeasible");
  png(chart, canvas, "candidate-sizing");
  const pane = el("div");
  let page = 0;
  list.append(pane, inspection);
  const pageSize = 40;

  const isBest = row => meta?.best_bess_candidate && ["bus_id", "energy_capacity_kwh", "power_rating_kw"].every(
    key => row[key] === meta.best_bess_candidate[key]);
  function inspect(row) {
    inspection.replaceChildren();
    const info = section(inspection, batteryName(row));
    kv(info, [["Feasible", row.feasible], ["Annual cost (USD/year)", row.annual_cost], ["Result", row.message],
      ["Available records", isBest(row) && run.scenarios.best_bess?.hours.length ?
        "Saved replay · Best evaluated feasible BESS" : "Summary only"],
      ["Unserved energy (kWh)", row.load_shedding_energy_kwh],
      ["Curtailment (kWh)", row.curtailment_energy_kwh], ["Reserve violation hours", row.reserve_violation_hours]]);
    if (isBest(row) && run.scenarios.best_bess?.hours.length) info.append(button("Inspect saved battery replay", () => {
      state.tab = "BESS"; pickScenario("best_bess");
    }));
  }

  function scatter(rows) {
    const {context: ctx, width, height} = sizeCanvas(canvas);
    const points = rows.filter(row => number(row[axis.value]) && number(row.energy_capacity_kwh));
    const xs = points.map(row => row[axis.value]), ys = points.map(row => row.energy_capacity_kwh);
    if (!points.length) { ctx.fillText("No matching candidates", 20, 40); return; }
    const lowX = Math.min(...xs), highX = Math.max(...xs), lowY = Math.min(...ys), highY = Math.max(...ys);
    const scaleX = value => lowX === highX ? width / 2 : 70 + (value - lowX) / (highX - lowX) * (width - 110);
    const scaleY = value => lowY === highY ? height / 2 : height - 48 - (value - lowY) / (highY - lowY) * (height - 95);
    ctx.fillStyle = "#506876";
    ctx.fillText("Energy (kWh)", 7, 19);
    ctx.fillText(fmt(highY), 7, 37);
    ctx.fillText(fmt(lowY), 7, height - 46);
    ctx.fillText(fmt(lowX), 65, height - 13);
    ctx.fillText(fmt(highX), width - 60, height - 13);
    const hits = [];
    for (const row of points) {
      const x = scaleX(row[axis.value]), y = scaleY(row.energy_capacity_kwh);
      hits.push([x, y, row]);
      ctx.fillStyle = row.feasible ? "#087c80" : "#b84c37";
      ctx.beginPath();
      ctx.arc(x, y, isBest(row) ? 7 : 4, 0, 2 * Math.PI);
      ctx.fill();
    }
    canvas.onpointermove = event => {
      const nearest = hits.find(([x, y]) => Math.hypot(x - event.offsetX, y - event.offsetY) < 8);
      hint.textContent = nearest ? batteryName(nearest[2]) + " · " + (nearest[2].feasible ? "feasible" : "infeasible") :
        "Energy capacity (kWh) · Teal feasible · Red infeasible";
    };
    canvas.onclick = event => {
      const nearest = hits.find(([x, y]) => Math.hypot(x - event.offsetX, y - event.offsetY) < 8);
      if (nearest) inspect(nearest[2]);
    };
  }

  function refresh() {
    pane.replaceChildren();
    const rows = run.evaluations.filter(row => (!bus.value || String(row.bus_id) === bus.value) &&
      (!status.value || row.feasible === (status.value === "yes")) &&
      (!minimum.value || row[size.value] >= Number(minimum.value)) &&
      (!maximum.value || row[size.value] <= Number(maximum.value)));
    rows.sort((a, b) => order.value === "feasible" ? Number(b.feasible) - Number(a.feasible) :
      (a[order.value] ?? Infinity) - (b[order.value] ?? Infinity));
    page = Math.min(page, Math.max(0, Math.ceil(rows.length / pageSize) - 1));
    table(pane, ["Candidate", "Bus", "Power (kW)", "Energy (kWh)", "Feasible", "Annual cost", "Records", "Result"],
      rows.slice(page * pageSize, (page + 1) * pageSize).map(row => [button("Inspect " + row.evaluation_index, () => inspect(row)),
        row.bus_id, row.power_rating_kw, row.energy_capacity_kwh, row.feasible, row.annual_cost,
        isBest(row) && run.scenarios.best_bess?.hours.length ? "Saved replay" : "Summary only", row.message]));
    const previous = button("Previous", () => { page--; refresh(); });
    const next = button("Next", () => { page++; refresh(); });
    previous.disabled = page === 0;
    next.disabled = (page + 1) * pageSize >= rows.length;
    pane.append(previous, el("span", "  " + rows.length + " matching · Page " + (page + 1) + "  "), next);
    scatter(rows);
    state.redraw = () => scatter(rows);
  }
  [bus, status, order, axis, size, minimum, maximum].forEach(control => control.addEventListener("change", () => {
    page = 0; refresh();
  }));
  refresh();
}

function diagnostics(root) {
  const scenario = active();
  const event = eventAt();
  if (!scenario.hours.length) return note(root, "Saved hourly diagnostics unavailable.");
  const hour = section(root, hourAt() || "Selected hour");
  const row = scenario.hours[state.hour];
  if (event) {
    const stages = [["Uncontrolled", event.pre], ["After BESS", event.after_bess], ["Final controls", event.final]];
    table(hour, ["State", "FBS converged", "Min voltage (pu)", "Min bus", "Max voltage (pu)", "Max bus",
      "Grid import (kW)", "Grid export (kW)", "Constraint excess"],
      stages.map(([title, flow]) => [title, flow?.converged, flow?.minimum_pu, flow?.minimum_bus,
        flow?.maximum_pu, flow?.maximum_bus, flow?.import_kw, flow?.export_kw,
        flow?.converged ? Object.keys(flow.violations).length ? flow.violations :
          flow.binding?.join(", ") || "None" : null]));
    kv(hour, [["BESS injection (kW)", event.accepted_kw], ["Shedding after controls (kW)", event.shedding_kw],
      ["Curtailment after controls (kW)", event.curtailment_kw], ["Matched No BESS shedding (kW)", event.no_bess_shedding_kw],
      ["Matched No BESS curtailment (kW)", event.no_bess_curtailment_kw],
      ["Avoided shedding (kW)", event.avoided_shedding_kw], ["Avoided curtailment (kW)", event.avoided_curtailment_kw],
      ["Corrector status", event.correction?.status], ["Linear solver status", event.correction?.linear_status],
      ["Corrector iterations", event.correction?.iterations], ["Corrector FBS calls", event.correction?.fbs_trials],
      ["Corrective cost (USD)", event.correction?.objective_usd],
      ["Power balance residual (kW)", row.power_balance_residual_kw], ["Reactive balance residual (kvar)", row.reactive_balance_residual_kvar],
      ["Reason codes", event.reason_codes?.join(", ")], ["Look-ahead hours", event.horizon_hours],
      ["Engineering messages", event.messages?.join(" · ")]]);
    note(hour, "Constraint excess uses pu for voltage, amperes for branch current and kW for grid limits.");
  } else {
    kv(hour, [["FBS converged", row.converged], ["Final minimum voltage (pu)", row.voltage_min_pu],
      ["Final maximum voltage (pu)", row.voltage_max_pu], ["Shedding after controls (kW)", row.shedding_kw],
      ["Curtailment after controls (kW)", row.curtailment_kw], ["Messages", row.messages ?? row.fbs_message]]);
    note(hour, "Pre-correction, BESS-only and matched counterfactual records unavailable.");
  }
  if (row.converged === false) note(hour, "Final electrical values belong to a nonconverged diagnostic iterate.");
  if (row.converged && row.feasible === false) note(hour, "This operating point is infeasible. See the residual limits and engineering messages above.");
  const controlled = Object.keys(scenario.buses).map(id => [id, entityAt(scenario, "Bus", id, hourAt())])
    .filter(([, bus]) => bus.shedding_kw > 0 || bus.curtailment_kw > 0)
    .sort(([, a], [, b]) => b.shedding_kw - a.shedding_kw);
  if (controlled.length) table(hour, ["Bus", "Shed (kW)", "Shed (kvar)", "Curtailed (kW)", "Pre-control voltage (pu)", "Final voltage (pu)"],
    controlled.map(([id, bus]) => [id, bus.shedding_kw, bus.shedding_kvar, bus.curtailment_kw, bus.pre_control_voltage_pu, bus.voltage_pu]));
  if (number(textMetric("load_shedding_energy_kwh"))) {
    const requested = textMetric("requested_load_energy_kwh");
    const shed = textMetric("load_shedding_energy_kwh");
    const totals = section(root, "Feeder shedding over the saved interval");
    const peak = scenario.hours.reduce((current, item) => {
      const demand = item.load_input_kw + item.shedding_kw;
      return number(item.shedding_kw) && demand > 0 ? Math.max(current, item.shedding_kw / demand) : current;
    }, 0);
    kv(totals, [["Unserved energy (kWh)", shed], ["Energy unserved (%)", requested > 0 ? shed / requested * 100 : null],
      ["Peak hourly shedding (%)", peak * 100], ["Curtailed energy (kWh)", textMetric("curtailment_energy_kwh")],
      ["Feeder losses (kWh)", textMetric("loss_energy_kwh")]]);
    const dt = manifest().dt_hours;
    if (number(dt)) {
      const ranking = Object.entries(scenario.buses).map(([id, bus]) => [id,
        (bus.shedding_kw || []).reduce((sum, power) => sum + (power || 0), 0) * dt]);
      ranking.sort((a, b) => b[1] - a[1]);
      if (ranking.some(([, energy]) => energy > 0)) table(totals, ["Bus", "Unserved energy (kWh)"], ranking);
    }
  }
  const run = current();
  const paired = state.runs.filter(other => {
    const comparison = compare(run.manifest, other.manifest);
    return other !== run && comparison.align && comparison.inputMatch &&
      other.manifest.network_control && run.manifest.network_control &&
      other.manifest.network_control !== run.manifest.network_control && other.scenarios[state.scenario] &&
      stable(run.metadata.optimizer?.best_bess_candidate) === stable(other.metadata.optimizer?.best_bess_candidate) &&
      stable(run.metadata.context?.["Manual BESS"]) === stable(other.metadata.context?.["Manual BESS"]);
  });
  if (paired.length) {
    const comparison = section(root, "Matched corrective control policies");
    const entries = [[run.manifest.network_control, scenario], ...paired.map(other =>
      [other.manifest.network_control, other.scenarios[state.scenario]])];
    table(comparison, ["Policy", "Feasible", "Unserved energy (kWh)", "Curtailed (kWh)", "Annual cost (USD/year)"],
      entries.map(([policy, variant]) => {
        const m = metricsOf(variant.metrics);
        return [nameOf(policy), m.feasible, m.load_shedding_energy_kwh, m.curtailment_energy_kwh,
          m.feasible ? m.annual_total_cost : null];
      }));
  }
  if (!scenario.events.length) return;
  const log = section(root, "Dispatch event filter");
  const controls = el("div", undefined, "chart-controls");
  const causes = [...new Set(scenario.events.flatMap(item => item.reason_codes))].sort();
  const cause = select([["", "All saved causes"], ...causes.map(code => [code, code])], state.filterCause);
  const date = el("input"), bus = el("input");
  date.type = "date"; date.value = state.filterDate || "";
  bus.type = "number"; bus.min = 1; bus.value = state.filterBus || "";
  controls.append(label("Cause", cause), label("Study date", date), label("Bus ID", bus));
  log.append(controls);
  const pane = el("div");
  log.append(pane);
  function refresh() {
    state.filterCause = cause.value; state.filterDate = date.value; state.filterBus = bus.value;
    pane.replaceChildren();
    const list = scenario.events.filter(item =>
      (!cause.value || item.reason_codes.includes(cause.value)) &&
      (!date.value || item.timestamp.startsWith(date.value)) &&
      (!bus.value || String(item.bus_id) === bus.value || Object.keys(item.pre.violations).some(
        key => /voltage:/.test(key) && key.split(":")[1] === bus.value) ||
        String(item.pre.minimum_bus) === bus.value || String(item.pre.maximum_bus) === bus.value));
    table(pane, ["Hour", "Battery bus", "Raw voltage min (pu)", "Accepted (kW)", "Final shedding (kW)", "Causes"],
      list.slice(0, 60).map(item => [button(item.timestamp, () => setHour(item.timestamp)), item.bus_id,
        item.pre.minimum_pu, item.accepted_kw, item.shedding_kw, item.reason_codes.join(", ")]));
    if (list.length > 60) note(pane, "Showing the first 60 of " + list.length + " matching records. Select a date or use the study-hour slider.");
  }
  [cause, date, bus].forEach(control => control.addEventListener("change", refresh));
  refresh();
}

function preparePrint() {
  const summary = $("print-summary");
  summary.replaceChildren(el("h1", $("title").textContent));
  overview(summary);
  if (manifest().economics) economics(summary, true);
}

async function start() {
  const run = await unpack($("report-data").textContent);
  state.runs.push(run);
  $("run").add(new Option(run.manifest.folder, 0));
  for (const name of tabs) {
    const control = button(name, () => { state.tab = name; render(); });
    control.setAttribute("role", "tab");
    $("tabs").append(control);
  }
  $("tabs").setAttribute("role", "tablist");
  $("workspace").hidden = false;
  pickRun(0);
  $("run").addEventListener("change", () => pickRun(Number($("run").value)));
  $("scenario").addEventListener("change", () => pickScenario($("scenario").value));
  $("hour").addEventListener("input", () => setHour(active().hours[Number($("hour").value)]?.timestamp));
  $("print").addEventListener("click", () => { preparePrint(); window.print(); });
  window.addEventListener("beforeprint", preparePrint);
  window.addEventListener("resize", () => state.redraw?.());
  $("import").addEventListener("change", async event => {
    const failures = [];
    for (const file of event.target.files) {
      try {
        const run = await readImport(file);
        const existing = state.runs.findIndex(item => item.manifest.run_id === run.manifest.run_id);
        if (existing < 0) {
          $("run").add(new Option(run.manifest.folder, state.runs.length));
          state.runs.push(run);
        } else if (state.runs[existing].scenarios.summary && !run.scenarios.summary) state.runs[existing] = run;
      } catch (error) { failures.push(file.name + " · " + error.message); }
    }
    event.target.value = "";
    checkNotice();
    if (failures.length) $("notice").textContent += " " + failures.join(" ");
    render();
  });
  document.documentElement.dataset.ready = "true";
}

start().catch(error => { $("notice").textContent = "Unable to open saved dashboard: " + error.message; });
