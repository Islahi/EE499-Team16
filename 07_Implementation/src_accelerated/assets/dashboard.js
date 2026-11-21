"use strict";

const $ = id => document.getElementById(id);
const tabs = ["Overview", "Network", "Charts", "Analysis"];
const analysisTabs = ["BESS", "Economics", "Optimization", "Diagnostics"];
const colors = ["#087c80", "#b84c37", "#275fa5", "#79568c", "#806509", "#257647"];
const state = {runs: [], run: 0, scenario: "", tab: "Overview", analysis: "", hour: 0,
  equipment: ["Bus", ""], zoom: 1, offsetX: 0, offsetY: 0, redraw: null};
const empty = {label: "Summary only", hours: [], buses: {}, branches: {}, metrics: [], events: []};
const number = value => typeof value === "number" && Number.isFinite(value);
const formatters = new Map();
const fmt = (value, digits = 5) => number(value) ? formatNumber(value, digits) : value === null || value === undefined || value === "" ? "Unavailable" :
  typeof value === "boolean" ? (value ? "Yes" : "No") :
  typeof value === "object" ? JSON.stringify(value) : String(value);
const nameOf = key => key.replaceAll("_", " ").replace(/^./, letter => letter.toUpperCase());
const manifest = () => state.runs[state.run].manifest;
const current = () => state.runs[state.run];
const active = () => current().scenarios[state.scenario] || empty;
const hourCount = scenario => scenario?.hour_count ?? scenario?.hours?.length ?? 0;
const staticCase = (scenario = active()) => (scenario.first || scenario.hours[0])?.timestamp === "Static base case";
const hourAt = () => active().hours[state.hour]?.timestamp || (!state.hour ? active().first?.timestamp : null);
const metricsOf = rows => Object.fromEntries(rows.map(row => [row.metric, row.value]));
const textMetric = (key, fallback) => metricsOf(active().metrics)[key] ?? fallback ?? null;

function formatNumber(value, digits) {
  if (!formatters.has(digits)) formatters.set(digits, new Intl.NumberFormat("en", {maximumFractionDigits: digits}));
  return formatters.get(digits).format(value);
}

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
  return advanced(root, title, body => body.append(el("pre", typeof value === "string" ? value : JSON.stringify(value, null, 2))));
}

function advanced(root, title, fill) {
  const box = el("details", undefined, "advanced");
  const summary = el("summary", title);
  const content = el("div", undefined, "advanced-content");
  box.append(summary, content);
  root.append(box);
  const reveal = async () => {
    if (!box.open) return;
    box.removeEventListener("toggle", reveal);
    try { await fill(content); }
    catch (error) { note(content, "Unable to read saved details. " + error.message); }
  };
  box.addEventListener("toggle", reveal);
  return box;
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
  $("notice").textContent = messages.join(" ");
  $("comparison-help").textContent = state.runs.length > 1 ? "Compatibility details appear above the report." :
    "Import a saved HTML report, portable ZIP, or manifest to compare runs.";
  $("run-label").hidden = state.runs.length < 2;
  $("scenario-label").hidden = Object.keys(current().scenarios).length < 2;
}

function indexRun(run, readBlock) {
  if (![1, 2].includes(run.manifest?.schema_version) || typeof run.manifest.run_id !== "string" ||
      !run.scenarios || !run.metadata) throw Error("Unsupported report or manifest schema.");
  run.readBlock = readBlock;
  for (const scenario of Object.values(run.scenarios)) {
    scenario.hours ??= [];
    scenario.buses ??= {};
    scenario.branches ??= {};
    scenario.events ??= [];
    scenario.timeIndex = new Map(scenario.hours.map((row, index) => [row.timestamp, index]));
    scenario.eventIndex = new Map(scenario.events.map(event => [event.timestamp, event]));
    scenario.run = run;
  }
  return run;
}

async function inflate(data) {
  if (typeof DecompressionStream !== "function") throw Error("This report needs a browser with gzip decompression support.");
  const encoded = data.trim();
  let bytes;
  if (typeof Uint8Array.fromBase64 === "function") bytes = Uint8Array.fromBase64(encoded);
  else {
    const raw = atob(encoded);
    bytes = new Uint8Array(raw.length);
    for (let i = 0; i < raw.length; i++) bytes[i] = raw.charCodeAt(i);
  }
  const stream = new Blob([bytes]).stream().pipeThrough(new DecompressionStream("gzip"));
  return new Response(stream).json();
}

const cachedBlocks = new Map();

function block(run, id) {
  if (id === null || id === undefined) return Promise.resolve(null);
  const key = run.manifest.run_id + ":" + id;
  const task = cachedBlocks.get(key) || Promise.resolve().then(() => run.readBlock(id)).then(inflate).catch(error => {
    cachedBlocks.delete(key);
    throw error;
  });
  cachedBlocks.delete(key);
  cachedBlocks.set(key, task);
  if (cachedBlocks.size > 20) cachedBlocks.delete(cachedBlocks.keys().next().value);
  return task;
}

async function loadHours(scenario) {
  if (!scenario.hours.length && hourCount(scenario)) {
    scenario.hours = await block(scenario.run, scenario.hours_block);
    scenario.timeIndex = new Map(scenario.hours.map((row, index) => [row.timestamp, index]));
  }
}

function eventSummaries(scenario) {
  return scenario.event_index_block === null || scenario.event_index_block === undefined ?
    Promise.resolve(scenario.events) : block(scenario.run, scenario.event_index_block);
}

async function hourEvent(scenario, index) {
  const timestamp = scenario.hours[index]?.timestamp;
  if (!scenario.event_blocks) return scenario.eventIndex.get(timestamp);
  const events = await block(scenario.run, scenario.event_blocks[Math.floor(index / scenario.chunk_hours)]);
  return events?.find(event => event.timestamp === timestamp);
}

async function unpack(data, readBlock) {
  return indexRun(await inflate(data), readBlock);
}

function payloadFromHtml(source) {
  const match = source.match(/<script id="report-data" type="application\/octet-stream"[^>]*>\s*([A-Za-z0-9+/=]+)\s*<\/script>/);
  if (!match) throw Error("The HTML does not contain an EE499 run.");
  let blocks;
  return unpack(match[1], id => {
    if (!blocks) {
      blocks = new Map();
      const headers = /<script id="report-block-(\d+)" type="application\/octet-stream"[^>]*>/g;
      let header;
      while ((header = headers.exec(source))) {
        const end = source.indexOf("<\/script>", headers.lastIndex);
        if (end < 0) break;
        blocks.set(Number(header[1]), [headers.lastIndex, end]);
        headers.lastIndex = end + 9;
      }
    }
    if (!blocks.has(id)) throw Error("The saved report is missing data block " + id);
    return source.slice(...blocks.get(id));
  });
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
  if (![1, 2].includes(data.schema_version) || !data.run_id || !Array.isArray(data.summary)) {
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
  state.pendingTimestamp = active().hours.length ? null : previous;
  state.visibleSeries = null;
  checkNotice();
  render();
}

function updateHour() {
  const input = $("hour");
  const count = hourCount(active());
  input.max = Math.max(0, count - 1);
  input.disabled = count < 2;
  input.value = state.hour;
  $("timestamp").textContent = hourAt() || "Hourly data unavailable";
  $("previous-hour").disabled = state.hour === 0;
  $("next-hour").disabled = state.hour >= count - 1;
}

function setHour(timestamp) {
  const index = active().timeIndex?.get(timestamp);
  if (index === undefined) return;
  state.hour = index;
  updateHour();
  if (state.hourChanged) state.hourChanged();
  else state.redraw?.();
}

function availableAnalysis(run, scenario) {
  return analysisTabs.filter(name => ({
    BESS: scenario.has_bess ?? scenario.hours.some(row => number(row.bess_accepted_soc)),
    Economics: run.economic_comparison?.length || number(metricsOf(scenario.metrics).annual_total_cost),
    Optimization: run.candidate_count || run.evaluations?.length || run.metadata.optimizer,
    Diagnostics: hourCount(scenario) && !staticCase(scenario)
  })[name]);
}

function navigate(tab, analysis) {
  state.tab = tab;
  if (analysis) state.analysis = analysis;
  render();
}

function tabKey(event) {
  if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
  const choices = [...event.currentTarget.querySelectorAll("button:not(:disabled)")];
  const index = choices.indexOf(event.target);
  if (index === -1) return;
  event.preventDefault();
  const next = event.key === "Home" ? choices[0] : event.key === "End" ? choices.at(-1) :
    choices[(index + choices.length + (event.key === "ArrowLeft" ? -1 : 1)) % choices.length];
  next.click();
  if (event.currentTarget.id === "analysis-tabs") $(next.id)?.focus();
  else next.focus();
}

function tabControl(name, id, activate, selected) {
  const control = button(name, activate);
  control.id = id;
  control.setAttribute("role", "tab");
  control.setAttribute("aria-controls", "panel");
  control.setAttribute("aria-selected", selected);
  control.tabIndex = selected ? 0 : -1;
  return control;
}

let viewRequest = 0;

async function render() {
  const request = ++viewRequest;
  const run = current();
  const scenario = active();
  const interval = run.manifest.interval || {};
  const begin = interval.start?.slice(0, 10), end = (interval.end_exclusive || interval.last)?.slice(0, 10);
  $("title").textContent = (run.manifest.kind === "base case" ? "Static base case" :
    run.manifest.kind === "optimization" ? "Storage optimization" :
    run.manifest.kind === "simulation" ? "Hourly simulation" : "Archived results");
  $("subtitle").textContent = [run.metadata.context?.Network, run.manifest.source,
    begin && end && begin !== end ? begin + " to " + end : begin, run.manifest.solver?.name]
    .filter(Boolean).join(" · ");
  const analyses = availableAnalysis(run, scenario);
  if (!analyses.includes(state.analysis)) state.analysis = analyses.includes("Optimization") ? "Optimization" : analyses[0];
  const availability = {Overview: true, Network: !!run.metadata.layout && hourCount(scenario) > 0,
    Charts: hourCount(scenario) > 0 && !staticCase(scenario), Analysis: analyses.length > 0};
  if (!availability[state.tab]) state.tab = "Overview";
  $("tabs").querySelectorAll("button").forEach(control => {
    const selected = control.textContent === state.tab;
    control.disabled = !availability[control.textContent];
    control.setAttribute("aria-selected", selected);
    control.tabIndex = selected ? 0 : -1;
  });
  const analysisBar = $("analysis-tabs");
  analysisBar.hidden = state.tab !== "Analysis";
  analysisBar.replaceChildren(...(analysisBar.hidden ? [] : analyses.map(name =>
    tabControl(name, "analysis-" + name.toLowerCase(), () => navigate("Analysis", name), state.analysis === name))));
  const root = $("panel");
  const body = el("div", undefined, "view-content");
  root.replaceChildren(body);
  root.setAttribute("aria-labelledby", (state.tab === "Analysis" ? "analysis-" + state.analysis : "tab-" + state.tab).toLowerCase());
  state.redraw = null;
  state.hourChanged = null;
  const view = state.tab === "Analysis" ? state.analysis : state.tab;
  const timeView = ["Network", "Charts", "BESS", "Diagnostics"].includes(view);
  $("hour-controls").hidden = !timeView || staticCase(scenario) || hourCount(scenario) < 2;
  try {
    if (timeView && !scenario.hours.length) {
      note(body, "Loading saved hourly results…");
      await loadHours(scenario);
      if (request !== viewRequest) return;
      if (state.pendingTimestamp) state.hour = scenario.timeIndex.get(state.pendingTimestamp) ?? 0;
      state.pendingTimestamp = null;
      body.replaceChildren();
    }
    updateHour();
    await ({Overview: overview, Network: network, Charts: simulation, BESS: bess,
      Economics: economics, Optimization: optimization, Diagnostics: diagnostics})[view](body);
  } catch (error) {
    if (request === viewRequest) note(body, "Unable to read saved results. " + error.message);
  }
}

function batteryName(candidate) {
  return candidate ? "Bus " + candidate.bus_id + " · " + candidate.power_rating_kw + " kW / " +
    candidate.energy_capacity_kwh + " kWh" : "Unavailable";
}

function energy(kwh) {
  return number(kwh) ? fmt(kwh / 1000, 2) + " MWh" : null;
}

function currency(value) {
  return number(value) ? fmt(value, 0) + " USD/year" : null;
}

function selectedOutcome(run) {
  const optimizer = run.metadata.optimizer;
  if (!optimizer) return active().label;
  if (optimizer.no_bess_selected) return "No BESS";
  return optimizer.best_bess_feasible ? batteryName(optimizer.best_bess_candidate) : "No feasible design";
}

function savedAlternatives(run) {
  const base = metricsOf(run.scenarios.no_bess?.metrics || []);
  const battery = metricsOf(run.scenarios.best_bess?.metrics || []);
  const selected = run.metadata.optimizer?.no_bess_selected ? base : battery;
  const matched = !run.metadata.optimizer?.best_bess_replay_mismatch && base.feasible === true && battery.feasible === true;
  const savings = (matched || selected === base && base.feasible === true) &&
    number(base.annual_total_cost) && number(selected.annual_total_cost) ? base.annual_total_cost - selected.annual_total_cost : null;
  return {base, battery, selected, matched, savings};
}

function percentChange(before, after) {
  return number(before) && before > 0 && number(after) ? (before - after) * 100 / before : null;
}

function comparisonGraphic(root, base, battery) {
  const rows = [["Annual cost", "annual_total_cost", currency], ["Unserved energy", "load_shedding_energy_kwh", energy],
    ["PV curtailment", "curtailment_energy_kwh", energy]].filter(([, key]) => number(base[key]) && number(battery[key]));
  if (!rows.length) return;
  const box = section(root, "No BESS vs best feasible battery");
  const legend = el("div", undefined, "comparison-legend");
  legend.append(el("span", "No BESS", "base-key"), el("span", "Best feasible battery", "battery-key"));
  box.append(legend);
  for (const [caption, metric, display] of rows) {
    const before = base[metric], after = battery[metric];
    const change = percentChange(before, after);
    const row = el("div", undefined, "comparison-row");
    const title = el("div", undefined, "comparison-label");
    title.append(el("strong", caption));
    if (change !== null) title.append(el("span", fmt(Math.abs(change), 2) + "% " +
      (change > 0 ? "lower" : change < 0 ? "higher" : "change"), "muted"));
    const bars = el("div", undefined, "comparison-bars");
    const max = Math.max(Math.abs(before), Math.abs(after), 1);
    for (const [kind, value] of [["base", before], ["battery", after]]) {
      const line = el("div", undefined, "bar-line");
      const fill = el("span", undefined, "bar-fill " + kind);
      fill.style.width = 100 * Math.abs(value) / max + "%";
      fill.setAttribute("aria-hidden", "true");
      line.append(fill, el("span", display(value), "bar-value"));
      bars.append(line);
    }
    row.append(title, bars);
    box.append(row);
  }
}

function overview(root) {
  const run = current();
  const scenario = active();
  const optimizer = run.metadata.optimizer;
  const snapshot = scenario.first || scenario.hours[0] || {};
  const summary = section(root, staticCase() ? "Feeder benchmark" : "Results at a glance");
  const diagnosis = scenario.diagnostic || {};
  const metrics = metricsOf(scenario.metrics);
  const low = run.metadata.simulation?.voltage_min_pu;
  const high = run.metadata.simulation?.voltage_max_pu;
  if (staticCase()) {
    const vMin = diagnosis.worst_voltage_pu ?? snapshot.voltage_min_pu;
    const bus = diagnosis.worst_bus ?? snapshot.minimum_voltage_bus;
    cards(summary, [["Power flow", snapshot.converged === true ? "Converged" :
      snapshot.converged === false ? "Did not converge" : null],
    ["Minimum voltage", number(vMin) ? fmt(vMin, 5) + " pu" + (bus ? " at bus " + bus : "") : null],
    ["Active power loss", number(snapshot.loss_p_kw) ? fmt(snapshot.loss_p_kw, 2) + " kW" : null]]);
    if (number(vMin) && number(low) && vMin < low) summary.append(el("p",
      "Minimum voltage is below the configured " + fmt(low) + " pu limit.", "warning"));
  } else if (optimizer) {
    const {base, battery, selected, matched, savings} = savedAlternatives(run);
    const fraction = number(selected.load_shedding_energy_kwh) && selected.requested_load_energy_kwh > 0 ?
      100 * selected.load_shedding_energy_kwh / selected.requested_load_energy_kwh : null;
    cards(summary, [["Selected alternative", selectedOutcome(run)],
      ["Modeled annual savings", currency(savings)], ["Unserved energy", energy(selected.load_shedding_energy_kwh)],
      ["PV curtailment", energy(selected.curtailment_energy_kwh)],
      ["Hours with a disconnected bus", selected.hours_with_full_disconnection ?? "Unavailable"],
      ["Feasibility", selected.feasible === true ? "Passed recorded limits" : selected.feasible === false ? "Infeasible" : null]]);
    if (selected.hours_with_full_disconnection > 0) summary.append(el("p", "One or more load buses were fully disconnected during the selected run.", "warning"));
    if (optimizer.decision_message) note(summary, optimizer.decision_message);
    else if (matched && savings > 0) note(summary, "The selected battery has a lower recorded annual objective than No BESS.");
    else if (matched && optimizer.no_bess_selected) note(summary, "No BESS had the lowest recorded annual objective.");
    if (optimizer.best_bess_replay_mismatch) summary.append(el("p", optimizer.best_bess_replay_mismatch, "warning"));
    if (fraction > 0) summary.append(el("p", fmt(fraction, 2) + "% of requested energy was unserved in the selected alternative.", "warning"));
    if (matched) comparisonGraphic(root, base, battery);
  } else {
    const infeasible = metrics.feasible === false || diagnosis.infeasible > 0;
    cards(summary, [["Feasibility", infeasible ? "Infeasible" : metrics.feasible === true ? "Passed recorded limits" : null],
      ["Minimum voltage after controls", number(metrics.voltage_min_pu) ? fmt(metrics.voltage_min_pu) + " pu" : null],
      ["Unserved energy", energy(metrics.load_shedding_energy_kwh)],
      ["PV curtailment", energy(metrics.curtailment_energy_kwh)],
      ["Hours with a disconnected bus", metrics.hours_with_full_disconnection ?? "Unavailable"]]);
    if (metrics.hours_with_full_disconnection > 0) summary.append(el("p", "One or more load buses were fully disconnected.", "warning"));
    if (infeasible) summary.append(el("p", "Saved results contain unresolved constraints or failed hours.", "warning"));
    if (metrics.load_shedding_energy_kwh > 0 && metrics.requested_load_energy_kwh > 0)
      summary.append(el("p", fmt(100 * metrics.load_shedding_energy_kwh / metrics.requested_load_energy_kwh, 2) +
        "% of requested energy was unserved.", "warning"));
  }
  if (!staticCase() && diagnosis.infeasible > 0 && optimizer)
    summary.append(el("p", scenario.label + " has " + fmt(diagnosis.infeasible) + " infeasible or nonconverged hours.", "warning"));
  if (!staticCase()) {
    const policy = run.metadata.simulation?.shedding_policy;
    note(summary, "Load service policy: " + (policy === "progressive" ? "Balanced shedding" :
      policy === "minimum_energy" ? "Minimum energy" : "Unavailable"));
  }
  if (number(low) && number(high)) note(summary, "Configured voltage range " + fmt(low) + "–" + fmt(high) + " pu. " +
    (run.manifest.clock ? "Study clock " + run.manifest.clock + "." : ""));
  const jumps = el("div", undefined, "jump-actions");
  if (run.metadata.layout && hourCount(scenario)) jumps.append(button("Explore network", () => navigate("Network")));
  if (availableAnalysis(run, scenario).includes("Economics")) jumps.append(button("Explore costs", () => navigate("Analysis", "Economics")));
  if (jumps.childElementCount) root.append(jumps);
  advanced(root, "Run details and all metrics", body => {
    for (const item of Object.values(run.scenarios)) {
      if (item.metrics.length) table(section(body, item.label), ["Saved metric", "Exact value", "Unit"],
        item.metrics.map(row => [nameOf(row.metric), row.value == null ? null : String(row.value), row.unit]));
    }
    details(body, "Settings, hashes and provenance", run.manifest);
    details(body, "Source and study configuration", run.metadata.context);
  });
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
    return Object.entries(run.scenarios).filter(([, scenario]) => hourCount(scenario)).map(([key, scenario]) => ({
      id: runIndex + ":" + key, label: (run === current() ? "" : run.manifest.folder + " · ") + scenario.label, scenario
    }));
  });
}

function entityColumns(scenario, type, id) {
  const columns = (type === "Bus" ? scenario.buses : scenario.branches)[id];
  const blocks = type === "Bus" ? scenario.bus_blocks : scenario.branch_blocks;
  return columns ? Promise.resolve(columns) : block(scenario.run, blocks?.[id]);
}

function entityValues(entity, index) {
  if (!entity || index === undefined) return {};
  return Object.fromEntries(Object.entries(entity).map(([field, values]) => [field, values[index]]));
}

function network(root) {
  const run = current();
  const scenario = active();
  const {layout: geometry, topology} = run.metadata;
  if (!geometry || !topology || !scenario.hours.length) return note(root, "Saved network values unavailable.");
  const bar = el("div", undefined, "chart-controls");
  const objects = [["", "Select a bus or line"], ...topology.buses.map(bus => ["Bus:" + bus.bus_id, "Bus " + bus.bus_id]),
    ...topology.lines.map(line => ["Line:" + line.line_id, "Line " + line.line_id])];
  const picker = select(objects, state.equipment.join(":"));
  const peers = comparableScenarios().filter(peer => peer.scenario !== scenario);
  const other = select([["", "None"], ...peers.map(peer => [peer.id, peer.label])], state.networkPeer);
  const overlay = select([["voltage", "Voltage (pu)"], ["served", "Served load (%)"], ["shedding", "Shedding (kW)"], ["resources", "PV and BESS"],
    ["violations", "Electrical violations"]], state.overlay);
  overlay.addEventListener("change", () => { state.overlay = overlay.value; draw(); });
  bar.append(label("Equipment", picker), label("Overlay", overlay),
    button("Zoom in", () => { state.zoom = Math.min(15, state.zoom * 1.25); draw(); }),
    button("Zoom out", () => { state.zoom = Math.max(.15, state.zoom / 1.25); draw(); }),
    button("Fit feeder", () => { state.zoom = 1; state.offsetX = state.offsetY = 0; draw(); }));
  root.append(bar);
  if (peers.length) advanced(root, "Compare network values", body => body.append(label("Comparison alternative", other)));

  const layout = el("div", undefined, "network-layout");
  const drawing = el("div", undefined, "network-drawing");
  const detail = el("aside", undefined, "network-inspector");
  layout.append(drawing, detail);
  root.append(layout);
  const status = el("p", undefined, "network-status");
  drawing.append(status);
  const {canvas, hint} = canvasFrame(drawing, "Select a bus or line for exact saved values.", "network");
  png(drawing, canvas, "feeder");
  const low = run.metadata.simulation?.voltage_min_pu, high = run.metadata.simulation?.voltage_max_pu;
  note(drawing, "Voltage (pu) · Below " + fmt(low) + " amber · Within limits teal · Above " +
    fmt(high) + " red. L and H mark voltage violations. Dashed red lines mark saved ampacity violations.");
  const positions = Object.values(geometry.positions);
  const xs = positions.map(([x]) => x), ys = positions.map(([, y]) => y);
  const left = Math.min(...xs), right = Math.max(...xs), top = Math.min(...ys), bottom = Math.max(...ys);
  const installed = state.scenario === "best_bess" ? run.metadata.optimizer?.best_bess_candidate :
    state.scenario === "." ? run.metadata.context?.["Manual BESS"] : null;
  let targets = [], segments = [], drag, snapshot, snapshotIndex = -1, inspected = 0;

  function draw() {
    const {context: ctx, width, height} = sizeCanvas(canvas);
    const scale = Math.max(.015, Math.min((width - 60) / Math.max(1, right - left),
      (height - 70) / Math.max(160, bottom - top))) * state.zoom;
    const xy = ([x, y]) => [width / 2 + (x - (right + left) / 2) * scale + state.offsetX,
      height / 2 + (y - (bottom + top) / 2) * scale + state.offsetY];
    targets = [];
    segments = [];
    const [kind, selected] = state.equipment;
    const offset = state.hour % scenario.chunk_hours;
    const validHour = scenario.hours[state.hour]?.converged !== false;
    const hourSnapshot = snapshotIndex === state.hour ? snapshot : null;
    for (const line of topology.lines) {
      const route = geometry.routes[line.line_id];
      if (!route?.length) continue;
      const points = route.map(xy);
      const oldAmps = scenario.branches[line.line_id]?.current_a?.[state.hour];
      const overload = overlay.value === "violations" && validHour && (hourSnapshot?.overloads[line.line_id]?.[offset] === "X" ||
        (!hourSnapshot && run.metadata.simulation?.enforce_line_ampacity !== false && number(line.ampacity_a) &&
         number(oldAmps) && oldAmps > line.ampacity_a + 1e-6));
      ctx.strokeStyle = overload ? "#b84c37" : kind === "Line" && selected === line.line_id ? "#087c80" : "#78929d";
      ctx.lineWidth = overload || kind === "Line" && selected === line.line_id ? 3 : 1.3;
      ctx.setLineDash(overload ? [5, 3] : []);
      ctx.beginPath();
      points.forEach(([x, y], index) => {
        if (index) { ctx.lineTo(x, y); segments.push([line.line_id, points[index - 1], points[index]]); }
        else ctx.moveTo(x, y);
      });
      ctx.stroke();
    }
    ctx.setLineDash([]);
    for (const bus of topology.buses) {
      const id = String(bus.bus_id);
      if (!geometry.positions[id]) continue;
      const [x, y] = xy(geometry.positions[id]);
      targets.push([id, x, y]);
      const values = entityValues(scenario.buses[id], state.hour);
      const series = hourSnapshot?.buses[id];
      const voltage = values.voltage_pu;
      const shedKw = series?.[2]?.[offset] ?? values.shedding_kw;
      const servedPercent = series?.[3]?.[offset] ?? (number(values.remaining_load_fraction) ? 100 * values.remaining_load_fraction : null);
      const disconnected = series?.[4]?.[offset] === "Y" || values.fully_disconnected === true;
      const shed = series?.[1]?.length ? series[1][offset] / 100 : (values.shedding_kw > 0 ?
        values.shedding_kw / (values.load_input_kw + values.shedding_kw) : null);
      const valid = validHour && !values.diagnostic_only;
      const band = !valid ? "?" : series?.[0]?.[offset] ?? (!number(voltage) || !number(low) || !number(high) ? "?" :
        voltage < low ? "L" : voltage > high ? "H" : "N");
      const pv = run.metadata.pv_buses?.includes(bus.bus_id), bess = installed?.bus_id === bus.bus_id;
      ctx.fillStyle = overlay.value === "resources" ? (bess ? "#79568c" : pv ? "#087c80" : "#879aa2") :
        overlay.value === "served" ? (number(servedPercent) && valid ? (servedPercent < 80 ? "#b56a05" : "#087c80") : "#879aa2") :
        overlay.value === "shedding" ? (shedKw > 0 && valid ? "#79568c" : "#879aa2") :
        band === "L" ? "#b56a05" : band === "H" ? "#b84c37" :
        band === "N" && overlay.value !== "violations" ? "#087c80" : "#879aa2";
      ctx.beginPath();
      const radius = kind === "Bus" && id === selected ? 8 : 5;
      ctx.arc(x, y, overlay.value === "shedding" && valid && shed > 0 ? radius + 6 * Math.min(1, shed) : radius, 0, Math.PI * 2);
      ctx.fill();
      if (disconnected && valid) {
        ctx.strokeStyle = "#b84c37";
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.arc(x, y, radius + 3, 0, Math.PI * 2);
        ctx.stroke();
      }
      ctx.fillStyle = "#102c3a";
      ctx.font = "11px system-ui, sans-serif";
      const icons = [bus.is_slack ? "Grid" : "", pv ? "PV" : "", bess ? "BESS" : ""].filter(Boolean);
      const loadLabel = overlay.value === "served" && number(servedPercent) ? " " + fmt(servedPercent, 0) + "%" :
        overlay.value === "shedding" && shedKw > 0 ? " " + fmt(shedKw, 1) + " kW" : "";
      ctx.fillText("B" + id + (disconnected && valid ? " Out" : "") +
        (["L", "H"].includes(band) ? " " + band : "") + loadLabel, x + 8, y - 6);
      if (icons.length) ctx.fillText(icons.join(" · "), x + 8, y + 12);
    }
  }

  async function inspect() {
    const request = ++inspected;
    detail.replaceChildren();
    const [kind, id] = state.equipment;
    if (!id) return note(detail, "Select a bus or line on the feeder to see its saved electrical values.");
    const index = state.hour;
    const time = hourAt();
    const equipment = kind === "Bus" ? topology.buses.find(bus => String(bus.bus_id) === id) :
      topology.lines.find(line => line.line_id === id);
    const alternative = peers.find(peer => peer.id === other.value);
    try {
      const [columns, compared] = await Promise.all([entityColumns(scenario, kind, id),
        alternative ? loadHours(alternative.scenario).then(() => entityColumns(alternative.scenario, kind, id)) : null]);
      if (request !== inspected || !detail.isConnected) return;
      const data = entityValues(columns, index);
      const peer = entityValues(compared, alternative?.scenario.timeIndex.get(time));
      const entries = kind === "Bus" ? [
        ["Voltage (pu)", "voltage_pu"], ["Requested load (kW)", "requested_load_kw"], ["Served load (kW)", "load_input_kw"],
        ["Load shed (%)", "shed_load_percent"], ["Fully disconnected", "fully_disconnected"],
        ["Requested load (kvar)", "requested_load_kvar"], ["Served load (kvar)", "load_input_kvar"],
        ["Delivered PV (kW)", "pv_input_kw"], ["Battery injection (kW)", "bess_input_kw"], ["Shedding (kW)", "shedding_kw"],
        ["Pre-control voltage (pu)", "pre_control_voltage_pu"], ["Available PV (kW)", "available_pv_kw"],
        ["Shedding (kvar)", "shedding_kvar"], ["Curtailment (kW)", "curtailment_kw"]] : [
        ["Current (A)", "current_a"], ["Active flow (kW)", "sending_p_kw", "p_kw"],
        ["Reactive flow (kvar)", "sending_q_kvar", "q_kvar"], ["Loss (kW)", "loss_p_kw", "loss_kw"]];
      const rows = entries.map(([caption, key, fallback]) => [caption, data[key] ?? data[fallback], peer[key] ?? peer[fallback]]);
      const pane = section(detail, kind + " " + id + (equipment?.name ? " · " + equipment.name : ""));
      const show = (target, items) => alternative ? table(target, ["Measure", scenario.label, alternative.label, "Difference"],
        items.map(([caption, actual, comparison]) => [caption, actual, comparison, number(actual) && number(comparison) ? actual - comparison : null])) :
        kv(target, items.map(([caption, actual]) => [caption, actual]));
      const limit = kind === "Bus" ? 8 : 3;
      show(pane, rows.slice(0, limit));
      if (kind === "Line") note(pane, "Bus " + equipment?.from_bus + " to " + equipment?.to_bus + " · Ampacity " +
        fmt(equipment?.ampacity_a) + " A");
      advanced(pane, "More electrical details", body => {
        show(body, rows.slice(limit));
        details(body, "Saved values and attributes", {equipment, data, comparison: alternative ? peer : undefined});
      });
      if (data.diagnostic_only || scenario.hours[index]?.converged === false) note(pane, "Nonconverged. Values are diagnostic only.");
    } catch (error) { if (request === inspected) note(detail, error.message); }
  }

  function selectEquipment(kind, id) {
    state.equipment = [kind, id];
    picker.value = id ? state.equipment.join(":") : "";
    draw();
    inspect();
  }
  picker.addEventListener("change", () => {
    const separator = picker.value.indexOf(":");
    if (separator === -1) selectEquipment("Bus", "");
    else selectEquipment(picker.value.slice(0, separator), picker.value.slice(separator + 1));
  });
  other.addEventListener("change", () => { state.networkPeer = other.value; inspect(); });
  canvas.addEventListener("wheel", event => {
    event.preventDefault();
    state.zoom = Math.max(.15, Math.min(15, state.zoom * (event.deltaY < 0 ? 1.12 : .9)));
    draw();
  }, {passive: false});
  canvas.addEventListener("pointerdown", event => {
    drag = [event.offsetX, event.offsetY, state.offsetX, state.offsetY];
    canvas.setPointerCapture(event.pointerId);
  });
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
    if (target) return selectEquipment("Bus", target[0]);
    const line = segments.find(([, [x, y], [x2, y2]]) => {
      const f = Math.max(0, Math.min(1, ((px - x) * (x2 - x) + (py - y) * (y2 - y)) /
        ((x2 - x) ** 2 + (y2 - y) ** 2 || 1)));
      return Math.hypot(px - x - f * (x2 - x), py - y - f * (y2 - y)) < 7;
    });
    if (line) selectEquipment("Line", line[0]);
  });

  async function showHour() {
    const index = state.hour;
    const row = scenario.hours[index];
    const message = row?.converged === false ? "Power flow did not converge" : row?.feasible === false ?
      "Unresolved constraints at this hour" : row?.shedding_kw > 0 ? fmt(row.shedding_kw) + " kW of load shed" : "";
    status.textContent = message;
    status.classList.toggle("warning", Boolean(message));
    try {
      const data = await block(run, scenario.network_blocks?.[Math.floor(index / scenario.chunk_hours)]);
      if (!root.isConnected || index !== state.hour) return;
      snapshot = data;
      snapshotIndex = index;
      hint.textContent = (hourAt() || "") + " · Wheel to zoom, drag to pan, select equipment for exact values.";
      draw();
      inspect();
    } catch (error) { status.textContent = error.message; }
  }
  state.hourChanged = showHour;
  state.redraw = draw;
  showHour();
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

function plot(root, series, title, withCsv = false) {
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
  const filename = title.toLowerCase().replace(/[^a-z0-9]+/g, "-");
  advanced(root, "Export chart", body => {
    png(body, canvas, filename);
    if (withCsv) body.append(button("Save chart data CSV", () => {
      const quote = value => '"' + String(value ?? "").replaceAll('"', '""') + '"';
      const rows = [["Timestamp", "Period", "Series", title], ...series.flatMap(set =>
        set.points.map(point => [point.timestamp, point.label, set.label, point.value]))];
      const url = URL.createObjectURL(new Blob([rows.map(row => row.map(quote).join(",")).join("\r\n")], {type: "text/csv"}));
      const link = el("a");
      link.href = url;
      link.download = filename + ".csv";
      link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    }));
  });
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
  if (field === "requested_demand_kw") return number(row.load_input_kw) && number(row.shedding_kw) ?
    row.load_input_kw + row.shedding_kw : null;
  return row[field];
}

function simulation(root) {
  const scenario = active();
  if (!scenario.hours.length || staticCase(scenario)) return note(root, "Hourly charts unavailable for this run.");
  const metrics = [
    ["Demand & PV (kW)", null, "average"], ["Shedding & curtailment (kW)", null, "average"],
    ["Voltage range (pu)", null, "min"], ["BESS SOC (%)", "bess_accepted_soc", "last"],
    ["BESS power (kW)", "bess_trial_power_kw", "average"], ["Grid & losses (kW)", null, "average"],
    ...variables
  ];
  const groups = {
    0: [["Requested demand", "requested_demand_kw", "average"], ["Delivered PV", "pv_input_kw", "average"]],
    1: [["Load shedding", "shedding_kw", "average"], ["PV curtailment", "curtailment_kw", "average"]],
    2: [["Lowest voltage", "voltage_min_pu", "min"], ["Highest voltage", "voltage_max_pu", "max"]],
    5: [["Grid import", "grid_import_kw", "average"], ["Grid export", "grid_export_kw", "average"],
        ["Active loss", "loss_p_kw", "average"]]
  };
  const peers = comparableScenarios();
  const quick = el("div", undefined, "chart-controls");
  const choose = select(metrics.map(([title], i) => [i, title]), state.variable ?? 0);
  const cadence = select(["Hourly", "Daily", "Weekly", "Monthly"].map(value => [value, value]), state.cadence);
  const windows = select([["all", "Full saved period"], ["7", "Week around selected hour"],
    ["30", "Month around selected hour"], ["custom", "Custom dates"]], state.chartWindow);
  const entityBox = el("span", undefined, "chart-entities");
  const firstDay = scenario.hours[0].timestamp.slice(0, 10), lastDay = scenario.hours.at(-1).timestamp.slice(0, 10);
  const start = el("input"), end = el("input");
  start.type = end.type = "date";
  start.min = end.min = firstDay;
  start.max = end.max = lastDay;
  start.value = state.chartStart || firstDay;
  end.value = state.chartEnd || lastDay;
  const activeId = peers.find(peer => peer.scenario === scenario)?.id;
  const overlay = select([["", "Current alternative only"], ...peers.filter(peer => peer.id !== activeId)
    .map(peer => [peer.id, peer.label])], state.chartPeer);
  quick.append(label("Metric", choose), entityBox, label("Resolution", cadence), label("Time range", windows),
    label("Compare with", overlay));
  root.append(quick);
  const selected = new Set(state.visibleSeries || (activeId ? [activeId] : []));
  if (overlay.value) selected.add(overlay.value);
  const legend = el("div", undefined, "chart-controls");
  const dates = el("div", undefined, "chart-controls");
  const multiple = el("div", undefined, "chart-controls");
  dates.append(label("Start date", start), label("End date", end));
  const options = advanced(root, "Advanced chart options", body => {
    body.append(dates, legend, multiple);
    peers.forEach(peer => {
      const toggle = el("input");
      toggle.type = "checkbox";
      toggle.value = peer.id;
      toggle.checked = selected.has(peer.id);
      toggle.addEventListener("change", () => {
        if (toggle.checked) selected.add(peer.id); else selected.delete(peer.id);
        redraw();
      });
      legend.append(label(peer.label, toggle, "toggle"));
    });
  });
  let chart = el("div");
  root.append(chart);
  let pending = 0;
  let entitySelect = null;

  function range() {
    if (windows.value === "custom") return [start.value, end.value];
    if (windows.value === "all") return [firstDay, lastDay];
    const day = new Date((hourAt()?.slice(0, 10) || firstDay) + "T00:00:00Z");
    const count = Number(windows.value);
    const from = new Date(day);
    from.setUTCDate(day.getUTCDate() - Math.floor(count / 2));
    const through = new Date(from);
    through.setUTCDate(from.getUTCDate() + count - 1);
    return [from.toISOString().slice(0, 10), through.toISOString().slice(0, 10)];
  }

  async function redraw() {
    const request = ++pending;
    state.variable = Number(choose.value);
    state.cadence = cadence.value;
    state.chartWindow = windows.value;
    state.chartStart = start.value;
    state.chartEnd = end.value;
    state.visibleSeries = selected;
    const [title, field, method, type] = metrics[state.variable];
    const fields = groups[state.variable] || [[title, field, method]];
    const [from, through] = range();
    const ids = type ? (state.chartEntities?.length ? state.chartEntities : [entitySelect.value]) : [""];
    const series = [];
    chart.setAttribute("aria-busy", "true");
    if (!chart.childElementCount) note(chart, "Loading saved series…");
    try {
      await Promise.all(peers.filter(peer => selected.has(peer.id)).map(async peer => {
        await loadHours(peer.scenario);
        const columns = await Promise.all(ids.map(id => type ? entityColumns(peer.scenario, type, id) : null));
        return {peer, columns};
      })).then(results => {
        for (const {peer, columns} of results) for (const [entityIndex, id] of ids.entries()) {
          const entity = columns[entityIndex];
          for (const [legendLabel, key, aggregate] of fields) {
            const records = [];
            for (const row of scenario.hours) {
              const date = row.timestamp.slice(0, 10);
              if ((from && date < from) || (through && date > through)) continue;
              const i = peer.scenario.timeIndex.get(row.timestamp);
              const sample = peer.scenario.hours[i];
              let value = type ? (sample?.converged === false || entity?.diagnostic_only?.[i] ? null : entity?.[key]?.[i]) :
                sample ? physicalValue(sample, key) : null;
              if (key === "bess_accepted_soc" && number(value)) value *= 100;
              records.push([row.timestamp, value, sample?.dt_hours]);
            }
            series.push({label: peer.label + (type ? " · " + type + " " + id : "") +
              (fields.length > 1 ? " · " + legendLabel : ""), points: bucketed(records, cadence.value, aggregate)});
          }
        }
      });
      if (request !== pending || !chart.isConnected) return;
      const next = el("div");
      chart.replaceWith(next);
      chart = next;
      if (!series.length) note(chart, "Select a saved series to plot.");
      else plot(chart, series, title, true);
      const meaning = [...new Set(fields.map(([, , aggregate]) => cadence.value === "Hourly" && aggregate !== "energy" ?
        "saved hourly values" : aggregationLabel[aggregate]))].join(" / ");
      note(chart, cadence.value + " · " + meaning + " · " + fmt(manifest().clock));
    } catch (error) { if (request === pending) note(chart, error.message); }
    finally { if (request === pending) chart.removeAttribute("aria-busy"); }
  }

  function changeEntities() {
    entityBox.replaceChildren();
    multiple.replaceChildren();
    const type = metrics[Number(choose.value)][3];
    if (type) {
      const entities = Object.keys(type === "Bus" ? scenario.bus_blocks || scenario.buses :
        scenario.branch_blocks || scenario.branches);
      entitySelect = select(entities.map(id => [id, type + " " + id]));
      const picks = (state.chartEntities || []).filter(id => entities.includes(id));
      if (picks.length) entitySelect.value = picks[0];
      state.chartEntities = picks.length ? picks : entities.slice(0, 1);
      const multi = select(entities.map(id => [id, type + " " + id]));
      multi.multiple = true;
      multi.size = Math.min(4, entities.length || 1);
      const sync = () => [...multi.options].forEach(option => { option.selected = state.chartEntities.includes(option.value); });
      sync();
      entitySelect.addEventListener("change", () => { state.chartEntities = [entitySelect.value]; sync(); redraw(); });
      multi.addEventListener("change", () => {
        state.chartEntities = [...multi.selectedOptions].map(option => option.value).slice(0, 6);
        if (!state.chartEntities.length && entitySelect.value) state.chartEntities = [entitySelect.value];
        if (state.chartEntities.length) entitySelect.value = state.chartEntities[0];
        sync();
        redraw();
      });
      entityBox.append(label(type, entitySelect));
      multiple.append(label("Additional " + type.toLowerCase() + " series (up to six)", multi));
    }
    redraw();
  }

  choose.addEventListener("change", changeEntities);
  overlay.addEventListener("change", () => {
    selected.clear();
    if (activeId) selected.add(activeId);
    if (overlay.value) selected.add(overlay.value);
    state.chartPeer = overlay.value;
    legend.querySelectorAll("input").forEach(input => { input.checked = selected.has(input.value); });
    redraw();
  });
  [cadence, windows, start, end].forEach(control => control.addEventListener("change", () => {
    if (windows.value === "custom") { options.open = true; }
    redraw();
  }));
  state.hourChanged = () => windows.value === "7" || windows.value === "30" ? redraw() : state.redraw?.();
  changeEntities();
}

async function bess(root) {
  const scenario = active();
  const run = current();
  const metrics = metricsOf(scenario.metrics);
  const candidate = state.scenario === "best_bess" ? run.metadata.optimizer?.best_bess_candidate :
    run.metadata.context?.["Manual BESS"];
  const values = scenario.hours.filter(row => number(row.bess_accepted_soc));
  if (!values.length) return note(root, "Saved hourly battery records are unavailable for this alternative.");
  const min = Math.min(...values.map(row => row.bess_accepted_soc));
  const max = Math.max(...values.map(row => row.bess_accepted_soc));
  const configuredFloor = candidate?.soc_min ?? (number(run.metadata.context?.["Settings controls"]?.spin_soc_min_percent) ?
    run.metadata.context["Settings controls"].spin_soc_min_percent / 100 : null);
  const limits = values.filter(row => row.bess_limited === true).length;
  const summary = section(root, "Battery operation");
  cards(summary, [["Battery configuration", batteryName(candidate)],
    ["Charged / discharged", number(metrics.bess_charge_energy_kwh) && number(metrics.bess_discharge_energy_kwh) ?
      energy(metrics.bess_charge_energy_kwh) + " / " + energy(metrics.bess_discharge_energy_kwh) : null],
    ["SOC range", fmt(min * 100, 2) + "–" + fmt(max * 100, 2) + "%"]]);
  if (number(configuredFloor)) {
    const floorHours = values.filter(row => row.bess_accepted_soc <= configuredFloor + 1e-8).length;
    note(summary, fmt(floorHours) + " recorded hours at minimum SOC. " + fmt(limits) + " hours recorded a battery limit.");
  } else if (limits) note(summary, fmt(limits) + " hours recorded a battery limit.");
  if (metrics.load_shedding_energy_kwh > 0) summary.append(el("p",
    energy(metrics.load_shedding_energy_kwh) + " of requested energy remained unserved with this battery.", "warning"));
  const choose = select([["soc", "State of charge (%)"], ["power", "Battery injection (kW)"],
    ["energy", "Stored energy (kWh)"], ["headroom", "Physical power headroom (kW)"]], state.bessVariable || "soc");
  root.append(label("Battery series", choose));
  const chart = el("div");
  root.append(chart);
  const records = new Map((await eventSummaries(scenario)).map(event => [event.timestamp, event]));
  if (!root.isConnected) return;
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
  function plotBattery() {
    state.bessVariable = choose.value;
    chart.replaceChildren();
    plot(chart, definitions[choose.value].map(([label, get]) => ({label,
      points: scenario.hours.map(row => ({label: row.timestamp, timestamp: row.timestamp,
        value: get(row, records.get(row.timestamp))}))})), choose.selectedOptions[0].textContent, true);
  }
  const hourly = el("div");
  let hourPanel;
  let request = 0;
  async function showHour() {
    state.redraw?.();
    if (!hourPanel.open) return;
    const sequence = ++request;
    const index = state.hour;
    const row = scenario.hours[index];
    try {
      const event = await hourEvent(scenario, index);
      if (!hourly.isConnected || sequence !== request) return;
      hourly.replaceChildren();
      const box = section(hourly, row.timestamp);
      kv(box, [["Requested (kW)", row.bess_request_kw], ["Accepted (kW)", event?.accepted_kw ?? row.bess_trial_power_kw],
        ["Injection before residual controls (kW)", event?.after_bess_kw], ["Energy before (kWh)", event?.energy_before_kwh],
        ["Energy after (kWh)", event?.energy_after_kwh], ["Remaining closure hours", event?.terminal_remaining_hours],
        ["Terminal target (kWh)", event?.terminal_target_kwh], ["Remaining charge headroom (kWh)", event?.terminal_charge_headroom_kwh],
        ["Remaining discharge headroom (kWh)", event?.terminal_discharge_headroom_kwh],
        ["Reason codes", event?.reason_codes?.join(", ") || row.bess_limit_reason]]);
      if (event?.risks?.length) table(box, ["Look-ahead hour", "Uncontrolled constraints", "Tested injection (kW)"],
        event.risks.map(risk => [risk.timestamp, risk.converged ? risk.constraints.join(", ") : "FBS failed",
          risk.tested_action_kw.join(", ") || null]));
      if (event?.projected_stress_actions?.length)
        table(box, ["Stressed hour", "Projected injection (kW)", "Projected energy (kWh)", "Realized injection (kW)"],
          event.projected_stress_actions.map(action => [action.timestamp, action.forecast_kw, action.forecast_energy_kwh,
            records.get(action.timestamp)?.accepted_kw]));
      if (event) details(box, "Complete saved dispatch event", event);
    } catch (error) { if (sequence === request) note(hourly, error.message); }
  }
  hourPanel = advanced(root, "Hourly battery limits and 24-hour schedule", body => body.append(hourly));
  hourPanel.addEventListener("toggle", showHour);
  choose.addEventListener("change", plotBattery);
  state.hourChanged = showHour;
  plotBattery();
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
  const {base, selected, savings} = savedAlternatives(run);
  const choice = run.metadata.optimizer ? selected : m;
  cards(report, [["No BESS annual cost", currency(base.annual_total_cost)], ["Selected annual cost", currency(choice.annual_total_cost)],
    ["Modeled annual savings", currency(savings)], ["Annualized ownership", currency(choice.annualized_bess_cost)]]
    .filter(([, value]) => value !== null));
  if (run.metadata.optimizer?.decision_message) note(report, run.metadata.optimizer.decision_message);
  note(report, "The objective includes modeled costs for unserved energy and curtailed PV. Avoided penalties are modeled savings.");
  const rate = prices?.discount_rate, lifetime = prices?.lifetime_years;
  const crf = number(rate) && number(lifetime) && lifetime > 0 ? (rate ? rate / (1 - (1 + rate) ** -lifetime) : 1 / lifetime) : null;
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
    advanced(chart, "Export chart", body => png(body, canvas, "annual-cost-contributions"));
  }
  const breakdown = body => {
    table(body, ["Component", ...scenarios.map(item => item.label)],
      components.map(([text, field]) => [text, ...values.map(item => number(item[field]) ? String(item[field]) : null)]));
    kv(body, [["Annualization basis", m.annualization_basis], ["Grid import tariff (USD/kWh)", prices?.grid_import_tariff_per_kwh],
      ["Grid export tariff (USD/kWh)", prices?.grid_export_tariff_per_kwh], ["Value of lost load (USD/kWh)", prices?.shedding_penalty_per_kwh],
      ["Curtailment penalty (USD/kWh)", prices?.curtailment_penalty_per_kwh], ["Discount rate (%)", number(rate) ? rate * 100 : null],
      ["Lifetime (years)", lifetime], ["Capital recovery factor", crf], ["Terminal energy policy", prices?.terminal_policy]]);
    if (run.economic_comparison?.length) economicAlternatives(body);
    if (state.runs.length > 1) {
      const cross = section(body, "Saved prices by run");
      const fields = ["grid_import_tariff_per_kwh", "grid_export_tariff_per_kwh", "shedding_penalty_per_kwh",
        "curtailment_penalty_per_kwh", "annualization_basis"];
      table(cross, ["Run", "Import tariff", "Export tariff", "Shedding penalty", "Curtailment penalty", "Annualization", "Basis matched"],
        state.runs.map(other => [other.manifest.folder, ...fields.map(field => other.manifest.economics?.[field]),
          compare(run.manifest, other.manifest).economics]));
    }
  };
  if (printable) breakdown(report);
  else advanced(root, "Detailed economics", breakdown);
}

function optimization(root) {
  const run = current();
  const meta = run.metadata.optimizer;
  const count = run.candidate_count ?? run.evaluations?.length ?? null;
  const feasible = run.feasible_count ?? run.evaluations?.filter(candidate => candidate.feasible === true).length ?? null;
  const infeasible = run.infeasible_count ?? run.evaluations?.filter(candidate => candidate.feasible === false).length ?? null;
  if (!count && !meta) return note(root, "Optimizer evaluations unavailable for this run.");
  const summary = section(root, "Candidate selection");
  const {savings} = savedAlternatives(run);
  cards(summary, [["Selected", selectedOutcome(run)], ["Feasible BESS candidates", feasible],
    ["Infeasible BESS candidates", infeasible], ["Modeled annual savings", currency(savings)]]);
  if (meta?.decision_message) note(summary, meta.decision_message);
  if (meta?.best_bess_replay_mismatch) summary.append(el("p", meta.best_bess_replay_mismatch, "warning"));
  if (meta?.annual_verification_hours) {
    note(summary, fmt(meta.annual_verification_hours, 0) + " chronological hours verified per finalist.");
    const reliable = meta.verified_minimum_shedding_candidate;
    if (reliable) note(summary, "Lowest shedding among verified batteries: " + batteryName(reliable.candidate) +
      ", " + energy(reliable.annual_shedding_kwh) + " unserved.");
    advanced(summary, "Screening estimates and verification times", body => {
      kv(body, [["Screened battery candidates", meta.screening_candidate_count],
        ["Verified finalist hours", meta.annual_verification_hours]]);
      details(body, "Representative weeks, bus probes and timings", {periods: meta.screening_periods,
        locations: meta.screened_locations, wall_seconds: meta.stage_wall_seconds});
    });
  }
  if (run.convergence.length) {
    const convergence = section(root, "Convergence");
    plot(convergence, [{label: "Best annual cost", points: run.convergence.map(row => ({
      label: nameOf(row.axis || "Iteration") + " " + row.index, timestamp: "", value: row.best_annual_cost
    }))}], "Best annual cost (USD/year)");
  }
  const best = run.ranked || run.evaluations?.filter(candidate => candidate.feasible === true && number(candidate.annual_cost))
    .sort((a, b) => a.annual_cost - b.annual_cost).slice(0, 8) || [];
  if (best.length) table(section(root, "Top feasible batteries"), ["Bus", "Power (kW)", "Energy (kWh)", "Annual cost (USD/year)"],
    best.map(item => [item.bus_id, item.power_rating_kw, item.energy_capacity_kwh, item.annual_cost]));
  if (count) advanced(root, "Explore all candidates", async body => {
    const evaluations = run.evaluations || await block(run, run.evaluation_block);
    if (body.isConnected) candidateExplorer(body, run, evaluations);
  });
}

function candidateExplorer(list, run, evaluations) {
  const meta = run.metadata.optimizer;
  const controls = el("div", undefined, "chart-controls");
  const buses = [...new Set(evaluations.map(row => row.bus_id))].sort((a, b) => a - b);
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
  const pageSize = 16;

  const isBest = row => meta?.best_bess_candidate && ["bus_id", "energy_capacity_kwh", "power_rating_kw"].every(
    key => row[key] === meta.best_bess_candidate[key]);
  function inspect(row) {
    inspection.replaceChildren();
    const info = section(inspection, batteryName(row));
    kv(info, [["Feasible", row.feasible], ["Annual cost (USD/year)", row.annual_cost], ["Result", row.message],
      ["Available records", isBest(row) && hourCount(run.scenarios.best_bess) ?
        "Saved replay · Best evaluated feasible BESS" : "Summary only"],
      ["Unserved energy (kWh)", row.load_shedding_energy_kwh],
      ["Curtailment (kWh)", row.curtailment_energy_kwh], ["Reserve violation hours", row.reserve_violation_hours]]);
    details(info, "Complete candidate record", row);
    if (isBest(row) && hourCount(run.scenarios.best_bess)) info.append(button("Inspect saved battery replay", () => {
      state.tab = "Analysis"; state.analysis = "BESS"; pickScenario("best_bess");
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
    const rows = evaluations.filter(row => (!bus.value || String(row.bus_id) === bus.value) &&
      (!status.value || row.feasible === (status.value === "yes")) &&
      (!minimum.value || row[size.value] >= Number(minimum.value)) &&
      (!maximum.value || row[size.value] <= Number(maximum.value)));
    rows.sort((a, b) => order.value === "feasible" ? Number(b.feasible) - Number(a.feasible) :
      (a[order.value] ?? Infinity) - (b[order.value] ?? Infinity));
    page = Math.min(page, Math.max(0, Math.ceil(rows.length / pageSize) - 1));
    table(pane, ["Candidate", "Bus", "Power (kW)", "Energy (kWh)", "Feasible", "Annual cost", "Records", "Result"],
      rows.slice(page * pageSize, (page + 1) * pageSize).map(row => [button("Inspect " + row.evaluation_index, () => inspect(row)),
        row.bus_id, row.power_rating_kw, row.energy_capacity_kwh, row.feasible, row.annual_cost,
        isBest(row) && hourCount(run.scenarios.best_bess) ? "Saved replay" : "Summary only", row.message]));
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

function severity(event, row) {
  return event?.severity ?? (row?.converged === false || event?.final?.converged === false ? 4 :
    row?.feasible === false || Object.keys(event?.final?.violations || {}).length ? 3 :
    (event?.shedding_kw ?? row?.shedding_kw) > 1e-9 ? 2 :
    (event?.curtailment_kw ?? row?.curtailment_kw) > 1e-9 || row?.bess_limited === true ? 1 : 0);
}

async function diagnostics(root) {
  const scenario = active();
  const run = current();
  if (!scenario.hours.length) return note(root, "Saved hourly diagnostics are unavailable.");
  const digest = scenario.diagnostic || {};
  const hourly = scenario.hours;
  const infeasible = digest.infeasible ?? hourly.filter(row => row.feasible === false || row.converged === false).length;
  const statusKnown = digest.known_status ?? hourly.some(row => row.feasible !== undefined || row.converged === false);
  const summary = section(root, "Validation status");
  const savedHours = key => hourly.some(row => number(row[key])) ? hourly.filter(row => row[key] > 1e-9).length : null;
  cards(summary, [["Unresolved or failed hours", statusKnown ? infeasible : null],
    ["Worst voltage after controls", number(digest.worst_voltage_pu ?? textMetric("voltage_min_pu")) ?
      fmt(digest.worst_voltage_pu ?? textMetric("voltage_min_pu"), 5) + " pu" +
      (digest.worst_bus ? " at bus " + digest.worst_bus : "") : null],
    ["Hours with load shedding", digest.shedding_hours ?? savedHours("shedding_kw")],
    ["Hours with PV curtailment", digest.curtailment_hours ?? savedHours("curtailment_kw")],
    ["Battery limiter hours", digest.battery_limiter_hours ??
      (hourly.some(row => typeof row.bess_limited === "boolean") ? hourly.filter(row => row.bess_limited === true).length : null)]]);
  if (infeasible) summary.append(el("p", "Saved results contain unresolved constraints, nonconvergence, or a failed feasibility check.", "warning"));

  advanced(root, "Load service and solver timings", body => {
    const quality = metricsOf(scenario.metrics);
    kv(body, [["Fully disconnected bus-hours", quality.fully_disconnected_bus_hours ?? "Unavailable"],
      ["Hours with any disconnected load bus", quality.hours_with_full_disconnection ?? "Unavailable"],
      ["Hours without verified service values", quality.service_unverified_hours ?? "Unavailable"],
      ["Bus-hours above 50% shed", quality.buses_shed_over_50_percent_hours ?? "Unavailable"],
      ["Bus-hours above 80% shed", quality.buses_shed_over_80_percent_hours ?? "Unavailable"],
      ["Weighted controller score", quality.controller_policy_score ?? "Unavailable"]]);
    const ranking = [...(scenario.service_by_bus || [])].sort((a, b) =>
      b.fully_disconnected_hours - a.fully_disconnected_hours || b.shed_energy_kwh - a.shed_energy_kwh);
    if (ranking.length) table(body, ["Bus", "Disconnected hours", "Longest outage (h)", "Energy served (%)", "Shed energy (kWh)"],
      ranking.map(bus => [bus.bus_id, bus.fully_disconnected_hours, bus.longest_disconnection_hours,
        bus.served_energy_percent, bus.shed_energy_kwh]));
    else note(body, "Per-bus service history unavailable.");
    details(body, "Saved timing breakdown", run.metadata.context?.["Dispatch timing"] ||
      run.metadata.optimizer?.stage_wall_seconds || {});
  });

  const tableSection = section(root, "Event log");
  const controls = el("div", undefined, "chart-controls");
  const scope = select([["exceptional", "Exceptional events"], ["all", "All saved hours"]], state.eventScope);
  controls.append(label("Show", scope));
  tableSection.append(controls);
  const filter = el("div", undefined, "chart-controls");
  advanced(tableSection, "Filter by reason, date or bus", body => body.append(filter));
  const list = el("div");
  tableSection.append(list);
  const selected = el("div", undefined, "selected-event");
  const selectedHeading = section(root, "Selected event");
  selectedHeading.append(selected);
  note(selected, "Select an event to inspect the recorded stages.");
  const eventRows = await eventSummaries(scenario);
  if (!root.isConnected) return;
  const byTime = new Map(eventRows.map(event => [event.timestamp, event]));
  const reasons = [...new Set(eventRows.flatMap(item => item.reason_codes || []))].sort();
  const reason = select([["", "All saved causes"], ...reasons.map(code => [code, code])], state.filterCause);
  const date = el("input"), bus = el("input");
  date.type = "date"; date.value = state.filterDate || "";
  bus.type = "number"; bus.min = 1; bus.value = state.filterBus || "";
  filter.append(label("Cause", reason), label("Study date", date), label("Bus ID", bus));

  let opened = false, view = 0, page = 0;
  async function showHour() {
    if (!opened) return;
    const sequence = ++view;
    const index = state.hour;
    const row = hourly[index];
    selected.replaceChildren();
    note(selected, "Reading saved stages for " + row.timestamp + "…");
    try {
      const event = await hourEvent(scenario, index);
      if (sequence !== view || !selected.isConnected) return;
      selected.replaceChildren();
      selected.append(el("h3", row.timestamp));
      if (severity(event, row) >= 3) selected.append(el("p", "This operating point failed a recorded check.", "warning"));
      const stages = event ? [["Uncontrolled", event.pre], ["After BESS", event.after_bess], ["Final controls", event.final]] : [];
      if (stages.length) {
        table(selected, ["Stage", "Converged", "Min voltage (pu)", "Bus", "Max voltage (pu)", "Bus",
          "PCC import (kW)", "PCC export (kW)", "Residual limits"], stages.map(([title, flow]) => [
          title, flow?.converged, flow?.minimum_pu, flow?.minimum_bus, flow?.maximum_pu, flow?.maximum_bus,
          flow?.import_kw, flow?.export_kw, flow?.converged ? Object.keys(flow.violations || {}).length ? flow.violations :
            flow.binding?.join(", ") || "None recorded" : null]));
      } else kv(selected, [["FBS converged", row.converged], ["Minimum voltage (pu)", row.voltage_min_pu],
        ["Maximum voltage (pu)", row.voltage_max_pu], ["PCC real power (kW)", row.slack_p_kw]]);
      kv(selected, [["Load shed (kW)", event?.shedding_kw ?? row.shedding_kw],
        ["Curtailed PV (kW)", event?.curtailment_kw ?? row.curtailment_kw], ["BESS injection (kW)", event?.accepted_kw],
        ["Reasons", event?.reason_codes?.join(", ") || row.bess_limit_reason]]);
      advanced(selected, "Advanced details for this event", async body => {
        kv(body, [["Corrector status", event?.correction?.status], ["Linear solver status", event?.correction?.linear_status],
          ["Corrector iterations", event?.correction?.iterations], ["Corrector FBS calls", event?.correction?.fbs_trials],
          ["Corrective cost (USD)", event?.correction?.objective_usd], ["Power balance residual (kW)", row.power_balance_residual_kw],
          ["Reactive balance residual (kvar)", row.reactive_balance_residual_kvar], ["Look-ahead hours", event?.horizon_hours],
          ["Matched No BESS shedding (kW)", event?.no_bess_shedding_kw], ["Matched No BESS curtailment (kW)", event?.no_bess_curtailment_kw],
          ["Avoided shedding (kW)", event?.avoided_shedding_kw], ["Avoided curtailment (kW)", event?.avoided_curtailment_kw],
          ["Engineering messages", event?.messages?.join(" · ") || row.messages || row.fbs_message]]);
        details(body, "Complete saved event and hourly record", {event, row});
        const ids = Object.keys(scenario.bus_blocks || scenario.buses);
        const controls = (await Promise.all(ids.map(async id => [id, entityValues(await entityColumns(scenario, "Bus", id), index)])))
          .filter(([, bus]) => bus.shedding_kw > 0 || bus.curtailment_kw > 0)
          .sort(([, a], [, b]) => b.shedding_kw - a.shedding_kw);
        if (controls.length) table(body, ["Bus", "Shed (kW)", "Shed (kvar)", "Curtailed (kW)", "Pre-control (pu)", "Final (pu)"],
          controls.map(([id, bus]) => [id, bus.shedding_kw, bus.shedding_kvar, bus.curtailment_kw, bus.pre_control_voltage_pu, bus.voltage_pu]));
      });
    } catch (error) { if (sequence === view) note(selected, error.message); }
  }

  function refresh() {
    state.eventScope = scope.value;
    state.filterCause = reason.value;
    state.filterDate = date.value;
    state.filterBus = bus.value;
    list.replaceChildren();
    const matching = hourly.map(row => ({row, event: byTime.get(row.timestamp)})).filter(({row, event}) => {
      const pre = event?.pre || {};
      const matchingBus = [event?.bus_id, pre.minimum_bus, pre.maximum_bus].some(value => String(value) === bus.value) ||
        (pre.violation_keys || Object.keys(pre.violations || {})).some(key => /voltage:/.test(key) && key.split(":")[1] === bus.value);
      return (scope.value === "all" || severity(event, row) > 0) &&
        (!reason.value || event?.reason_codes?.includes(reason.value)) && (!date.value || row.timestamp.startsWith(date.value)) &&
        (!bus.value || matchingBus);
    });
    if (!matching.length) return note(list, "No saved hours match these filters.");
    if (scope.value !== "all") matching.sort((a, b) => severity(b.event, b.row) - severity(a.event, a.row) ||
      a.row.timestamp.localeCompare(b.row.timestamp));
    const size = 10;
    const last = Math.ceil(matching.length / size) - 1;
    page = Math.min(page, last);
    const status = ["Routine", "PV curtailment or BESS limit", "Load shedding", "Unresolved check", "Nonconverged"];
    table(list, ["Saved hour", "Status", "Final min (pu)", "Load shed (kW)", "Reasons"], matching.slice(page * size, (page + 1) * size)
      .map(({row, event}) => [button(row.timestamp, () => {
        opened = true;
        setHour(row.timestamp);
        selectedHeading.scrollIntoView({block: "nearest"});
      }), status[severity(event, row)], row.voltage_min_pu, event?.shedding_kw ?? row.shedding_kw, event?.reason_codes?.join(", ")]));
    const pager = el("div", undefined, "chart-controls");
    const previous = button("Previous", () => { page--; refresh(); });
    const next = button("Next", () => { page++; refresh(); });
    previous.disabled = page === 0;
    next.disabled = page >= last;
    pager.append(previous, el("span", fmt(matching.length) + " hours · Page " + (page + 1) + " of " + (last + 1)), next);
    list.append(pager);
  }
  [scope, reason, date, bus].forEach(control => control.addEventListener("change", () => { page = 0; refresh(); }));
  state.hourChanged = () => { opened = true; showHour(); };
  refresh();

  advanced(root, "Feeder shedding and control comparisons", body => {
    const requested = textMetric("requested_load_energy_kwh"), shed = textMetric("load_shedding_energy_kwh");
    const fractions = hourly.filter(row => number(row.load_input_kw) && number(row.shedding_kw) && row.load_input_kw + row.shedding_kw > 0)
      .map(row => row.shedding_kw / (row.load_input_kw + row.shedding_kw));
    kv(body, [["Unserved energy (kWh)", shed], ["Energy unserved (%)", requested > 0 ? shed / requested * 100 : null],
      ["Peak hourly shedding (%)", fractions.length ? Math.max(...fractions) * 100 : null],
      ["Curtailed energy (kWh)", textMetric("curtailment_energy_kwh")], ["Feeder losses (kWh)", textMetric("loss_energy_kwh")]]);
    const ranking = scenario.shedding_ranking || Object.entries(scenario.buses).map(([id, bus]) => [id,
      (bus.shedding_kw || []).reduce((sum, power) => sum + (power || 0), 0) * manifest().dt_hours]);
    if (ranking.some(([, kwh]) => kwh > 0)) table(body, ["Bus", "Unserved energy (kWh)"], ranking.sort((a, b) => b[1] - a[1]));
    const peers = state.runs.filter(other => {
      const match = compare(run.manifest, other.manifest);
      return other !== run && match.align && match.inputMatch && other.manifest.network_control && run.manifest.network_control &&
        other.manifest.network_control !== run.manifest.network_control && other.scenarios[state.scenario] &&
        stable(run.metadata.optimizer?.best_bess_candidate) === stable(other.metadata.optimizer?.best_bess_candidate) &&
        stable(run.metadata.context?.["Manual BESS"]) === stable(other.metadata.context?.["Manual BESS"]);
    });
    if (peers.length) table(body, ["Policy", "Feasible", "Unserved energy (kWh)", "Curtailed (kWh)", "Annual cost (USD/year)"],
      [[run.manifest.network_control, scenario], ...peers.map(other => [other.manifest.network_control, other.scenarios[state.scenario]])]
        .map(([policy, item]) => {
          const m = metricsOf(item.metrics);
          return [nameOf(policy), m.feasible, m.load_shedding_energy_kwh, m.curtailment_energy_kwh,
            m.feasible ? m.annual_total_cost : null];
        }));
  });
  if (scenario.unmatched_event_block !== null && scenario.unmatched_event_block !== undefined)
    advanced(root, "Saved events without a matching hourly row", async body =>
      details(body, "Complete saved records", await block(run, scenario.unmatched_event_block)));
}

function preparePrint() {
  const summary = $("print-summary");
  summary.replaceChildren(el("h1", $("title").textContent));
  overview(summary);
  if (availableAnalysis(current(), active()).includes("Economics")) economics(summary, true);
}

async function start() {
  const available = document.readyState === "loading" ? new Promise(resolve =>
    document.addEventListener("DOMContentLoaded", resolve, {once: true})) : Promise.resolve();
  const run = await unpack($("report-data").textContent, async id => {
    if (!$("report-block-" + id)) await available;
    const element = $("report-block-" + id);
    if (!element) throw Error("The saved report is missing data block " + id);
    return element.textContent;
  });
  state.runs.push(run);
  $("run").add(new Option(run.manifest.folder, 0));
  for (const name of tabs) {
    const control = tabControl(name, "tab-" + name.toLowerCase(), () => navigate(name), state.tab === name);
    $("tabs").append(control);
  }
  $("tabs").setAttribute("role", "tablist");
  $("analysis-tabs").setAttribute("role", "tablist");
  $("tabs").addEventListener("keydown", tabKey);
  $("analysis-tabs").addEventListener("keydown", tabKey);
  const link = location.hash.slice(1).toLowerCase();
  const linkedAnalysis = analysisTabs.find(name => name.toLowerCase() === link);
  if (linkedAnalysis) { state.tab = "Analysis"; state.analysis = linkedAnalysis; }
  else state.tab = link === "simulation" ? "Charts" : tabs.find(name => name.toLowerCase() === link) || "Overview";
  $("workspace").hidden = false;
  $("report-actions").hidden = false;
  pickRun(0);
  $("run").addEventListener("change", () => pickRun(Number($("run").value)));
  $("scenario").addEventListener("change", () => pickScenario($("scenario").value));
  let slideFrame;
  $("hour").addEventListener("input", () => {
    const index = Number($("hour").value);
    cancelAnimationFrame(slideFrame);
    slideFrame = requestAnimationFrame(() => setHour(active().hours[index]?.timestamp));
  });
  $("previous-hour").addEventListener("click", () => setHour(active().hours[state.hour - 1]?.timestamp));
  $("next-hour").addEventListener("click", () => setHour(active().hours[state.hour + 1]?.timestamp));
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
        } else if (state.runs[existing].scenarios.summary && !run.scenarios.summary) {
          state.runs[existing] = run;
          if (existing === state.run) pickRun(existing);
        }
      } catch (error) { failures.push(file.name + " · " + error.message); }
    }
    event.target.value = "";
    checkNotice();
    if (failures.length) $("notice").textContent += " " + failures.join(" ");
    render();
  });
  document.documentElement.dataset.ready = "true";
  performance.mark("dashboard-bootstrap-ready");
}

start().catch(error => { $("notice").textContent = "Unable to open saved dashboard: " + error.message; });
