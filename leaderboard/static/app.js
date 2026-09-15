const ALIASES = { overview: "results", scoring: "results" };
const VIEWS = ["eras", "activity", "runs", "architecture", "results", "forecasts", "questions", "corpus", "lab"];
const ARCHITECTURE_NODES = [
  {
    id: "sources",
    label: "Historical inputs",
    short: "registries + dated files",
    stage: "build",
    runtime: "Build time · network permitted",
    summary: "Defines what can enter an epoch and records exact dates, provenance, access rules, and source types.",
    input: "Wayback captures, FRED/GDELT material, public reports, and maintained fixtures",
    output: "Cutoff-checked source documents and question ingredients",
    files: ["config/sources.yaml", "config/survey_sources.yaml", "data/sources/"],
  },
  {
    id: "builders",
    label: "Corpus + questions",
    short: "normalize, filter, index",
    stage: "build",
    runtime: "Build time · host process",
    summary: "Normalizes evidence, rejects anything after the epoch cutoff, builds hybrid indexes, and creates the benchmark question set.",
    input: "Dated source documents plus an epoch cutoff",
    output: "data/corpus/<epoch> and data/questions/<epoch>.jsonl",
    files: ["src/psbx/corpus/", "src/psbx/questions/", "src/psbx/epochs.py"],
  },
  {
    id: "sandbox",
    label: "Frozen search cell",
    short: "Docker · read-only · no egress",
    stage: "sealed",
    runtime: "Docker container · port 8766",
    summary: "Mounts exactly one epoch/source cell, freezes its clock, blocks outbound internet, and exposes only search, fetch, health, and clock endpoints.",
    input: "One read-only corpus index and its epoch configuration",
    output: "Cutoff-safe document hits and full-text fetches",
    files: ["src/psbx/sandbox/Dockerfile", "src/psbx/sandbox/search_service.py", "src/psbx/sandbox/docker_sidecar.py"],
  },
  {
    id: "agents",
    label: "Agents + society",
    short: "single, swarm, personas",
    stage: "runtime",
    runtime: "Host process · model APIs permitted",
    summary: "Runs one model or a configurable swarm, assigns explicit simulation personas, shares frozen retrieval, validates citations, and computes the swarm median.",
    input: "Questions, model/roster config, personas, and sealed search results",
    output: "Individual votes, rationales, citations, and aggregate predictions",
    files: ["src/psbx/agents/", "src/psbx/society/", "src/psbx/openrouter.py", "custom/"],
  },
  {
    id: "runs",
    label: "Run archive",
    short: "manifest, log, votes",
    stage: "runtime",
    runtime: "Host filesystem · append-only run folders",
    summary: "Gives every launch a unique folder so configuration, progress, output, and failures remain inspectable and comparable.",
    input: "Prepared run config plus agent output",
    output: "run.yaml, swarm.yaml, manifest.json, run.log, predictions and votes",
    files: ["data/runs/<run-id>/", "leaderboard/jobs.py", "src/psbx/io.py"],
  },
  {
    id: "scoring",
    label: "Evaluation",
    short: "Brier, ranking, leakage",
    stage: "runtime",
    runtime: "Host process · later truth visible only here",
    summary: "Joins saved forecasts to later outcomes and produces probability error, ranking, calibration, contamination checks, target progress, and chart metadata.",
    input: "Predictions, votes, ground truth, public-prior baselines",
    output: "results.json, calibration data, progress measures, and PNG plots",
    files: ["src/psbx/scoring/", "src/psbx/eval/", "leaderboard/explain.py"],
  },
  {
    id: "viewer",
    label: "Dashboard",
    short: "control + inspect + compare",
    stage: "runtime",
    runtime: "FastAPI on 127.0.0.1:8765",
    summary: "Loads repository-backed state, starts jobs, monitors agents, switches epoch/source cells, compares runs, and explains scores in the browser.",
    input: "Epoch state, sandbox health, run files, scores and plots",
    output: "The Eras, Agents live, Runs, Architecture, Results, Questions, Corpus and Setup views",
    files: ["leaderboard/app.py", "leaderboard/store.py", "leaderboard/activity.py", "leaderboard/static/"],
  },
];
const state = {
  eras: [],
  selectedEra: null,
  switchingEra: false,
  activity: null,
  activityTimer: null,
  resealing: false,
  overview: null,
  questions: null,
  reveal: false,
  category: "",
  jobTimer: null,
  lastJobStatus: "idle",
  lastJobRunId: null,
  ready: null,
  swarmOptions: null,
  selectedRun: null,
  runs: [],
  runListKey: "",
  architectureNode: "sandbox",
};

const RUN_ORDER = [
  "phase2-e2012-swarm-probe-container",
  "phase2-e2012-swarm-probe",
  "phase2-e2012-openrouter",
  "phase2-e2012-real",
  "phase1-e2012-smoke",
];

function $(sel) {
  return document.querySelector(sel);
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function setText(sel, value) {
  const el = $(sel);
  if (el) el.textContent = value;
}

function withEra(path) {
  if (!state.selectedEra) return path;
  const url = new URL(path, window.location.origin);
  url.searchParams.set("epoch", state.selectedEra);
  return `${url.pathname}${url.search}`;
}

function selectedEra() {
  return state.eras.find((era) => era.id === state.selectedEra) || null;
}

async function getJSON(url) {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${res.status} ${url}`);
  return res.json();
}

function fmt(n, digits = 3) {
  if (n == null || Number.isNaN(n)) return "—";
  return Number(n).toFixed(digits);
}

function pct(n) {
  if (n == null || Number.isNaN(n)) return "—";
  return `${Math.round(Number(n) * 100)}%`;
}

function setView(name) {
  name = ALIASES[name] || name;
  if (!VIEWS.includes(name)) name = "results";
  for (const view of VIEWS) {
    const el = $(`#view-${view}`);
    if (el) el.hidden = view !== name;
  }
  const labels = {
    eras: "Eras",
    activity: "Agents live",
    runs: "Runs",
    architecture: "Architecture",
    results: "Results",
    forecasts: "Each answer",
    questions: "The questions",
    corpus: "The frozen library",
    lab: "Setup",
  };
  document.querySelectorAll("nav.tabs [role='tab']").forEach((btn) => {
    const on = btn.dataset.view === name;
    btn.setAttribute("aria-selected", on ? "true" : "false");
    btn.setAttribute("tabindex", on ? "0" : "-1");
    if (on) btn.setAttribute("aria-current", "page");
    else btn.removeAttribute("aria-current");
  });
  const announce = $("#view-announce");
  if (announce) announce.textContent = labels[name] || name;
  if (location.hash !== `#${name}`) history.replaceState(null, "", `#${name}`);
  if (name === "eras") renderEras();
  if (name === "activity") loadActivity();
  if (name === "runs") renderRunHistory(state.runs);
  if (name === "architecture") renderArchitecture(state.architectureNode);
  syncActivityPolling(name === "activity");
  if (name === "results") loadScores();
  if (name === "forecasts") loadForecasts();
  if (name === "questions") loadQuestions();
  if (name === "corpus") loadCorpus();
  if (name === "lab") renderLab();
}

function syncActivityPolling(active) {
  if (state.activityTimer) {
    clearInterval(state.activityTimer);
    state.activityTimer = null;
  }
  if (active) {
    state.activityTimer = setInterval(() => loadActivity(true), 2000);
  }
}

function applyEraCopy(era) {
  if (!era) return;
  const year = era.year;
  setText("#mast-lede", `We freeze the world on ${era.cutoff_date}, let a model search only evidence available by then, then grade it on what happened next.`);
  setText("#tab-corpus", `4. The ${year} library`);
  setText("#corpus-heading", `The ${year} library`);
  setText("#questions-caption", `The frozen ${year} question set`);
  setText("#corpus-caption", `Documents in the cutoff-locked ${year} index`);
  document.querySelectorAll(".era-prior-label").forEach((el) => {
    el.textContent = `${year} prior`;
  });
  const command = $("#era-build-command");
  if (command) {
    command.innerHTML = `Grow the ${year} library with <code>psbx corpus build --epoch ${escapeHtml(era.id)} --live --max-docs 400</code>. Its cutoff remains ${escapeHtml(era.cutoff_date)}.`;
  }
}

function renderEras() {
  const grid = $("#era-grid");
  if (!grid) return;
  const active = selectedEra();
  setText("#era-current-id", active ? active.id : "—");
  setText("#era-current-cutoff", active ? active.cutoff_date : "—");
  setText(
    "#era-current-evidence",
    active ? `${active.n_documents} documents · ${active.n_questions} questions` : "—"
  );
  grid.innerHTML = state.eras.length
    ? state.eras
        .map((era) => {
          const on = era.id === state.selectedEra;
          const sources = (era.source_types || []).length
            ? era.source_types.join(" · ")
            : "No indexed source silos yet";
          const missing = [
            !era.has_corpus ? "corpus" : "",
            !era.has_questions ? "questions" : "",
          ].filter(Boolean);
          const status = era.ready ? (on ? "Selected" : "Ready to select") : `Needs ${missing.join(" + ")}`;
          return `<button type="button" class="era-card" data-era="${escapeHtml(era.id)}" aria-pressed="${on}" ${era.ready ? "" : "disabled"}>
            <span class="era-card-top"><strong>${escapeHtml(String(era.year))}</strong><span class="era-status" data-ready="${era.ready}">${escapeHtml(status)}</span></span>
            <span class="era-dates">Freeze ${escapeHtml(era.cutoff_date)} → resolve by ${escapeHtml(era.resolution_window_end)}</span>
            <span class="era-counts"><b>${era.n_documents}</b> documents <b>${era.n_questions}</b> questions</span>
            <span class="era-sources">${escapeHtml(sources)}</span>
          </button>`;
        })
        .join("")
    : `<p class="empty">No epochs are configured.</p>`;
  const readyCount = state.eras.filter((era) => era.ready).length;
  const configured = state.eras.length;
  const suffix = configured === 1
    ? "Only one era is populated today; new configured datasets will appear here automatically."
    : "Each ready era stays isolated from every other era.";
  setText("#era-note", `${readyCount} of ${configured} configured eras ready. ${suffix}`);
}

async function loadEras() {
  const data = await getJSON("/api/eras");
  state.eras = data.eras || [];
  const requested = new URL(window.location.href).searchParams.get("epoch");
  const requestedEra = state.eras.find((era) => era.id === requested && era.ready);
  const defaultEra = state.eras.find((era) => era.id === data.default_epoch_id && era.ready);
  const firstReady = state.eras.find((era) => era.ready);
  state.selectedEra = (requestedEra || defaultEra || firstReady || {}).id || null;
  renderEras();
  applyEraCopy(selectedEra());
}

async function selectEra(epochId) {
  const era = state.eras.find((row) => row.id === epochId);
  if (!era || !era.ready || era.id === state.selectedEra || state.switchingEra) return;
  state.switchingEra = true;
  state.selectedEra = era.id;
  state.overview = null;
  state.questions = null;
  state.activity = null;
  state.selectedRun = null;
  state.runs = [];
  state.runListKey = "";
  const url = new URL(window.location.href);
  url.searchParams.set("epoch", era.id);
  history.replaceState(null, "", `${url.pathname}${url.search}${url.hash}`);
  const category = $("#q-category");
  category.innerHTML = `<option value="">All topics</option>`;
  $("#search-table tbody").innerHTML = "";
  $("#fetch-panel").hidden = true;
  renderEras();
  applyEraCopy(era);
  setText("#run-state-label", `Loading ${era.id}…`);
  try {
    await loadOverview();
    applyReady(state.ready);
    setView(location.hash.replace("#", "") || "results");
  } catch (err) {
    setText("#era-note", `Could not load ${era.id}: ${String(err)}`);
  } finally {
    state.switchingEra = false;
    renderEras();
  }
}

function bindTablist() {
  const tabs = [...document.querySelectorAll("nav.tabs [role='tab']")];
  tabs.forEach((btn, i) => {
    btn.addEventListener("click", () => setView(btn.dataset.view));
    btn.addEventListener("keydown", (ev) => {
      let next = null;
      if (ev.key === "ArrowRight" || ev.key === "ArrowDown") next = tabs[(i + 1) % tabs.length];
      if (ev.key === "ArrowLeft" || ev.key === "ArrowUp") next = tabs[(i - 1 + tabs.length) % tabs.length];
      if (ev.key === "Home") next = tabs[0];
      if (ev.key === "End") next = tabs[tabs.length - 1];
      if (!next) return;
      ev.preventDefault();
      next.focus();
      setView(next.dataset.view);
    });
  });
}

function runOptionKey(runs) {
  return (runs || [])
    .map((r) => `${r.run_id}|${r.label || r.run_id}|${r.n_predictions || 0}`)
    .join("\n");
}

function sortRuns(runs) {
  return (runs || []).slice().sort((a, b) => {
    const byDate = String(b.created_at || "").localeCompare(String(a.created_at || ""));
    if (byDate) return byDate;
    const ia = RUN_ORDER.indexOf(a.run_id);
    const ib = RUN_ORDER.indexOf(b.run_id);
    const ka = ia === -1 ? 100 : ia;
    const kb = ib === -1 ? 100 : ib;
    if (ka !== kb) return ka - kb;
    return (a.run_id || "").localeCompare(b.run_id || "");
  });
}

function pickPreferredRun(runs) {
  if (state.selectedRun && (runs || []).some((r) => r.run_id === state.selectedRun)) {
    return state.selectedRun;
  }
  const ready = state.ready || {};
  const ids = [ready.swarm_run_id, ready.live_run_id, ready.mock_run_id];
  for (const id of ids) {
    if (id && (runs || []).some((r) => r.run_id === id && r.n_predictions > 0)) return id;
  }
  return (runs && runs[0] && runs[0].run_id) || "";
}

function fillRunSelect(runs, preferred) {
  const select = $("#run-select");
  if (!select) return;
  const list = sortRuns(runs);
  const current = preferred || pickPreferredRun(list) || "";
  const key = runOptionKey(list);
  if (key !== state.runListKey) {
    select.innerHTML = list.length
      ? list
          .map((r) => {
            const label = r.label || r.run_id;
            const n = r.n_predictions ? ` · ${r.n_predictions}` : "";
            return `<option value="${r.run_id}">${label}${n}</option>`;
          })
          .join("")
      : `<option value="">No runs yet</option>`;
    state.runListKey = key;
  }
  if (current && [...select.options].some((o) => o.value === current)) {
    if (select.value !== current) select.value = current;
  }
  state.selectedRun = select.value || null;
  state.runs = list;
}

async function loadOverview() {
  const data = await getJSON(withEra("/api/overview"));
  state.overview = data;
  setText("#mast-epoch", data.epoch.id);
  setText("#mast-cutoff", data.epoch.cutoff_date);
  setText("#mast-resolve", data.epoch.resolution_window_end);
  const runs = (data.runs || []).map((r) => ({
    ...r,
    label: r.label || (data.run_labels && data.run_labels[r.run_id]) || r.run_id,
  }));
  const liveId = (state.ready && state.ready.live_run_id) || data.live_run_id;
  const swarmId = (state.ready && state.ready.swarm_run_id) || data.swarm_run_id;
  const mockId = (state.ready && state.ready.mock_run_id) || data.mock_run_id;
  if (state.ready) {
    state.ready.live_run_id = liveId;
    state.ready.swarm_run_id = swarmId;
    state.ready.mock_run_id = mockId;
  }
  fillRunSelect(runs, pickPreferredRun(runs));
  renderGoalProgress(data.goal_progress || {});
  renderRunHistory(state.runs);
  applyEraCopy(selectedEra());
}

function goalProgressSVG(points) {
  const visible = (points || []).slice(-14);
  if (!visible.length) {
    return `<p class="empty">No scored runs yet. Finish a run to start this history.</p>`;
  }
  const width = 760;
  const height = 250;
  const left = 46;
  const right = 18;
  const top = 20;
  const bottom = 42;
  const plotW = width - left - right;
  const plotH = height - top - bottom;
  const x = (index) => left + (visible.length === 1 ? plotW / 2 : index * plotW / (visible.length - 1));
  const y = (value) => top + (1 - Math.max(0, Math.min(100, Number(value))) / 100) * plotH;
  const actual = visible.map((point, index) => `${x(index)},${y(point.progress_percent)}`).join(" ");
  const best = visible.map((point, index) => `${x(index)},${y(point.best_so_far_percent)}`).join(" ");
  const guides = [0, 50, 100].map((value) => `<g>
    <line x1="${left}" y1="${y(value)}" x2="${width - right}" y2="${y(value)}" class="goal-guide${value === 100 ? " target" : ""}"></line>
    <text x="${left - 9}" y="${y(value) + 4}" text-anchor="end">${value}%</text>
  </g>`).join("");
  const marks = visible.map((point, index) => {
    const runNumber = points.length - visible.length + index + 1;
    return `<g class="goal-mark" data-met="${Boolean(point.goal_met)}">
      <circle cx="${x(index)}" cy="${y(point.progress_percent)}" r="5"><title>${escapeHtml(point.label)}: ${fmt(point.progress_percent, 1)}% progress; Brier ${fmt(point.brier)}; ${point.n_questions} questions</title></circle>
      <text x="${x(index)}" y="${height - 15}" text-anchor="middle">${runNumber}</text>
    </g>`;
  }).join("");
  return `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Goal progress across ${visible.length} scored runs">
    ${guides}
    <polyline points="${actual}" class="goal-run-line"></polyline>
    <polyline points="${best}" class="goal-best-line"></polyline>
    ${marks}
    <text x="${width - right}" y="${top - 7}" text-anchor="end" class="goal-target-label">TARGET</text>
    <text x="${left}" y="${height - 15}" class="goal-axis-label">RUN</text>
  </svg>`;
}

function renderGoalProgress(goal) {
  const best = goal.best || null;
  const latest = goal.latest || null;
  const human = goal.human_emulation || {};
  const progress = best ? Number(best.progress_percent || 0) : 0;
  setText("#goal-percent", best ? `${fmt(progress, 1)}%` : "—");
  setText("#goal-state", best && best.goal_met ? "Forecast target met" : best ? `${fmt(100 - progress, 1)}% remaining` : "Awaiting a scored run");
  setText(
    "#goal-gap",
    best
      ? best.goal_met
        ? `The forecast benchmark target has been met by ${best.label}. Keep running larger replications to test whether it holds.`
        : `${fmt(100 - progress, 1)}% remains before one run both beats the public prior and covers all ${goal.benchmark_questions || 50} questions.`
      : "A scored run is needed before progress can be measured."
  );
  const meter = $("#goal-meter");
  if (meter) {
    meter.value = progress;
    meter.textContent = `${fmt(progress, 1)}%`;
  }
  setText("#goal-quality", best ? `${fmt(best.quality_percent, 1)}% · Brier ${fmt(best.brier)}` : "—");
  setText("#goal-coverage", best ? `${fmt(best.coverage_percent, 1)}% · ${best.n_questions}/${goal.benchmark_questions || 50} questions` : "—");
  setText("#goal-latest", latest ? `${latest.label} · ${fmt(latest.progress_percent, 1)}%` : "—");
  setText("#goal-target", goal.target_brier == null ? "—" : `Brier ≤ ${fmt(goal.target_brier)} on ${goal.benchmark_questions || 50} questions`);
  setText("#goal-description", goal.target || "Beat the frozen public prior across the full benchmark");
  const chart = $("#goal-chart");
  if (chart) chart.innerHTML = goalProgressSVG(goal.points || []);
  const humanGoal = $("#human-goal");
  if (humanGoal) {
    humanGoal.dataset.status = human.status || "not_measured";
    humanGoal.innerHTML = `<strong>${escapeHtml(human.label || "Human-decision emulation is not scored yet")}</strong><span>${escapeHtml(human.requirement || "Held-out respondent-level survey outcomes are required before assigning this percentage.")}</span>`;
  }
}

function durationWords(seconds) {
  const value = Math.max(0, Number(seconds || 0));
  if (value < 60) return `${Math.ceil(value)} seconds`;
  if (value < 3600) return `${Math.ceil(value / 60)} minutes`;
  return `${(value / 3600).toFixed(value < 7200 ? 1 : 0)} hours`;
}

function renderArchitecture(selectedId = state.architectureNode) {
  const flow = $("#arch-flow");
  if (!flow) return;
  if (!flow.dataset.rendered) {
    flow.innerHTML = ARCHITECTURE_NODES.map((node, index) => {
      const edge = index < ARCHITECTURE_NODES.length - 1
        ? `<span class="arch-edge" aria-hidden="true"></span>`
        : "";
      return `<button type="button" class="arch-node" data-arch-node="${escapeHtml(node.id)}" data-stage="${escapeHtml(node.stage)}" aria-pressed="false"><strong>${escapeHtml(node.label)}</strong><span>${escapeHtml(node.short)}</span></button>${edge}`;
    }).join("");
    flow.dataset.rendered = "true";
  }
  const selected = ARCHITECTURE_NODES.find((node) => node.id === selectedId)
    || ARCHITECTURE_NODES[0];
  state.architectureNode = selected.id;
  flow.querySelectorAll("[data-arch-node]").forEach((button) => {
    button.setAttribute("aria-pressed", button.dataset.archNode === selected.id ? "true" : "false");
  });
  setText("#arch-detail-title", selected.label);
  setText("#arch-detail-summary", selected.summary);
  setText("#arch-detail-runtime", selected.runtime);
  setText("#arch-detail-input", selected.input);
  setText("#arch-detail-output", selected.output);
  $("#arch-detail-files").innerHTML = selected.files
    .map((path) => `<li><code>${escapeHtml(path)}</code></li>`)
    .join("");
}

function swarmComposition() {
  return [...document.querySelectorAll("[data-swarm-model]")].map((input) => ({
    model_id: input.dataset.swarmModel,
    count: Math.max(0, Number.parseInt(input.value || "0", 10) || 0),
  }));
}

function updateSwarmEstimate() {
  const options = state.swarmOptions || {};
  const bodies = swarmComposition();
  const agents = bodies.reduce((sum, row) => sum + row.count, 0);
  const questions = Math.max(1, Number.parseInt($("#swarm-questions").value || "1", 10) || 1);
  const calls = agents * questions;
  const ceiling = Number(options.ceiling || 100);
  const invalid = agents < 1 || agents > ceiling;
  setText("#swarm-total", `${agents} agent${agents === 1 ? "" : "s"}`);
  setText("#swarm-calls", `${calls} model call${calls === 1 ? "" : "s"}`);
  setText(
    "#swarm-estimate",
    `At least ${durationWords(calls * Number(options.minimum_seconds_per_call || 2))}, plus provider latency.`
  );
  setText(
    "#swarm-builder-error",
    invalid ? `Choose between 1 and ${ceiling} total agents.` : ""
  );
  const launch = $("#swarm-launch");
  if (launch) launch.disabled = invalid || state.lastJobStatus === "running";
  return { agents, questions, calls, bodies, invalid };
}

function applySwarmPreset(presetId) {
  const options = state.swarmOptions || {};
  const preset = (options.presets || []).find((row) => row.id === presetId);
  if (!preset) return updateSwarmEstimate();
  document.querySelectorAll("[data-swarm-model]").forEach((input) => {
    input.value = preset.counts[input.dataset.swarmModel] || 0;
  });
  setText("#swarm-builder-error", "");
  const label = $("#swarm-label");
  if (label) label.value = `${preset.label} comparison`;
  return updateSwarmEstimate();
}

function renderSwarmBuilder(options) {
  if (!options || !$("#swarm-composition")) return;
  state.swarmOptions = options;
  const presets = options.presets || [];
  $("#swarm-preset").innerHTML = presets
    .map((preset) => `<option value="${escapeHtml(preset.id)}">${escapeHtml(preset.label)}</option>`)
    .join("") + `<option value="custom">Custom mix</option>`;
  $("#swarm-preset").value = options.default_preset || "balanced-12";
  $("#swarm-composition").innerHTML = (options.species || [])
    .map((model) => `<tr>
      <td><strong>${escapeHtml(model.label)}</strong><small>${escapeHtml(model.notes || model.model_id)}</small></td>
      <td><code>${escapeHtml(model.model_slug)}</code></td>
      <td><label class="sr-only" for="count-${escapeHtml(model.model_id)}">Bodies using ${escapeHtml(model.label)}</label><input id="count-${escapeHtml(model.model_id)}" class="agent-count" type="number" min="0" max="${Number(options.ceiling || 100)}" value="${Number(model.default_count || 0)}" data-swarm-model="${escapeHtml(model.model_id)}"></td>
    </tr>`)
    .join("");
  applySwarmPreset(options.default_preset || "balanced-12");
}

function rosterSummary(composition) {
  const rows = (composition || []).filter((row) => Number(row.count));
  if (!rows.length) return "No saved roster";
  return rows
    .map((row) => `${row.count}× ${(row.label || row.model_id || "agent").replace(/^swarm (worker|species) · /, "")}`)
    .join(" · ");
}

function renderRunHistory(runs) {
  const body = $("#run-history");
  if (!body) return;
  const rows = sortRuns(runs || []);
  setText("#run-archive-count", `${rows.length} saved run${rows.length === 1 ? "" : "s"}`);
  body.innerHTML = rows.length
    ? rows.map((run) => {
        const when = run.created_at ? new Date(run.created_at).toLocaleString() : "date unavailable";
        const selected = run.run_id === state.selectedRun;
        const score = run.primary_brier == null ? "—" : fmt(run.primary_brier);
        const rank = run.primary_c_index == null ? "—" : fmt(run.primary_c_index);
        return `<tr data-selected="${selected}">
          <td><strong>${escapeHtml(run.label || run.run_id)}</strong><small>${escapeHtml(when)} · ${escapeHtml(run.source_type || "all")} sources</small><code>${escapeHtml(run.run_id)}</code></td>
          <td class="run-swarm-cell"><b>${Number(run.n_agents || 0)}</b><small>${escapeHtml(rosterSummary(run.composition))}</small></td>
          <td class="num">${Number(run.n_questions || 0)}</td>
          <td class="num">${score}</td>
          <td class="num">${rank}</td>
          <td><span class="run-status" data-status="${escapeHtml(run.status || "recorded")}">${escapeHtml(run.status || "recorded")}</span></td>
          <td><div class="row-actions"><button type="button" class="linkish" data-run-results="${escapeHtml(run.run_id)}" ${run.has_predictions ? "" : "disabled"}>Results</button><button type="button" class="linkish" data-run-log="${escapeHtml(run.run_id)}" ${run.has_log ? "" : "disabled"}>Log</button></div></td>
        </tr>`;
      }).join("")
    : `<tr><td colspan="7">No runs are saved for this epoch yet. Configure a swarm above to create the first one.</td></tr>`;
}

async function openSavedRun(runId, view = "results") {
  state.selectedRun = runId;
  fillRunSelect(state.runs, runId);
  await loadScores();
  await loadForecasts();
  if (view === "activity") await loadActivity();
  setView(view);
}

async function loadSavedLog(runId) {
  const data = await getJSON(withEra(`/api/runs/${encodeURIComponent(runId)}/log`));
  const run = data.run || {};
  $("#saved-log").hidden = false;
  setText("#saved-log-heading", run.label || runId);
  setText(
    "#saved-log-meta",
    `${run.n_agents || 0} agents · ${run.n_questions || 0} questions · ${run.status || "recorded"}`
  );
  setText("#saved-log-output", (data.lines || []).join("\n") || "No persistent log was recorded for this legacy run.");
  $("#saved-log").scrollIntoView({ behavior: "smooth", block: "start" });
}

function isolationFact(label, value, ok) {
  return `<div><dt>${escapeHtml(label)}</dt><dd class="${ok ? "ok" : "warn"}">${escapeHtml(value)}</dd></div>`;
}

function renderActivity(data) {
  state.activity = data;
  const experiment = data.experiment || {};
  const run = data.run || {};
  const access = data.access || {};
  const agents = data.agents || [];
  const evidence = data.evidence || {};
  setText("#activity-objective", experiment.objective || "No experiment selected.");
  setText("#activity-score-target", `Current target: ${experiment.score_target || "unknown"}.`);
  setText("#activity-human-gap", experiment.human_emulation_status || experiment.next_validation || "Not evaluated yet.");
  setText("#flow-epoch", `${data.epoch.id} · ${data.epoch.cutoff_date}`);
  setText("#flow-container", `${access.mode || "unknown"} · ${access.selection || "unknown"}`);
  setText("#flow-pack", run.shared_retrieval ? "one cutoff-locked pack" : "per-model retrieval");
  setText("#flow-agents", `${run.n_agents || 0} ${run.shared_retrieval ? "sequential" : "configured"}`);

  const sealed = Boolean(access.verified);
  const sealBadge = $("#seal-badge");
  sealBadge.dataset.status = sealed ? "verified" : "failed";
  sealBadge.textContent = sealed
    ? `${data.epoch.id}/${access.selection} seal verified`
    : "Seal not verified";
  $("#isolation-facts").innerHTML = [
    isolationFact("Live web", access.live_web || "unknown", access.live_web === "blocked"),
    isolationFact("Container clock", access.clock && access.clock.today ? access.clock.today : "unavailable", Boolean(access.cutoff_match)),
    isolationFact("Root filesystem", access.read_only_rootfs ? "read only" : "not verified", Boolean(access.read_only_rootfs)),
    isolationFact("Corpus mounts", access.mounts_read_only ? "read only" : "not verified", Boolean(access.mounts_read_only)),
    isolationFact("Published endpoint", access.loopback_only ? "127.0.0.1 only" : "not verified", Boolean(access.loopback_only)),
    isolationFact("Outbound egress", access.egress === "iptables-drop" ? "blocked by firewall" : access.egress || "unknown", access.egress === "iptables-drop" && Boolean(access.egress_lock_requested)),
  ].join("");

  const scopeSelect = $("#scope-select");
  const scopeKey = JSON.stringify(access.available_sources || {});
  if (scopeSelect.dataset.key !== scopeKey) {
    scopeSelect.innerHTML = Object.entries(access.available_sources || {})
      .map(([source, count]) => `<option value="${escapeHtml(source)}">${source === "all" ? "All epoch sources" : source} · ${count} documents</option>`)
      .join("");
    scopeSelect.dataset.key = scopeKey;
  }
  if ([...scopeSelect.options].some((option) => option.value === access.selection)) {
    scopeSelect.value = access.selection;
  }
  const runActive = run.status === "running";
  scopeSelect.disabled = runActive || state.resealing;
  const scopeApply = $("#scope-apply");
  scopeApply.disabled = runActive || state.resealing;
  scopeApply.textContent = state.resealing ? "Resealing…" : "Seal container to this scope";
  setText(
    "#scope-help",
    runActive
      ? "The access scope is locked until this run finishes."
      : `Current cell: ${data.epoch.id}/${access.selection}. Changing it restarts only the frozen search sidecar.`
  );

  const complete = Number(run.n_complete || 0);
  const total = Number(run.n_agents || agents.length || 0);
  const progress = Math.max(0, Math.min(1, Number(run.progress || 0)));
  $("#agent-progress").value = progress;
  $("#agent-progress").textContent = `${Math.round(progress * 100)}%`;
  setText("#agent-progress-label", `${complete} / ${total} complete · ${run.status || "idle"}`);
  $("#agent-grid").setAttribute("aria-busy", runActive ? "true" : "false");
  $("#agent-grid").innerHTML = agents.length
    ? agents
        .map((agent) => {
          const probability = agent.probability == null ? "—" : pct(agent.probability);
          const detail = agent.rationale || (agent.status === "working" ? "Waiting for this agent’s calibrated JSON vote." : "No saved vote for this run yet.");
          return `<details class="agent-row" data-status="${escapeHtml(agent.status)}">
            <summary>
              <span class="agent-index">${String(agent.index).padStart(2, "0")}</span>
              <span class="agent-identity"><strong>${escapeHtml(agent.model_label)}</strong><small>${escapeHtml(agent.persona_label)}</small></span>
              <span class="agent-state"><i aria-hidden="true"></i>${escapeHtml(agent.status)}</span>
              <span class="agent-vote">${probability}</span>
            </summary>
            <div class="agent-detail"><p>${escapeHtml(detail)}</p><code>${escapeHtml(agent.model_slug || agent.agent_id)}</code></div>
          </details>`;
        })
        .join("")
    : `<p class="empty">No agent roster is attached to this run.</p>`;

  const queries = evidence.queries || [];
  $("#activity-queries").innerHTML = queries.length
    ? queries.map((query) => `<li>${escapeHtml(query)}</li>`).join("")
    : `<li class="empty-line">No saved searches yet.</li>`;
  const timeline = data.timeline || [];
  $("#activity-timeline").innerHTML = timeline.length
    ? timeline.map((event) => `<li data-kind="${escapeHtml(event.kind)}"><strong>${escapeHtml(event.label)}</strong><span>${escapeHtml(event.detail)}</span></li>`).join("")
    : `<li class="empty-line">Saved run loaded. Live events appear here during the next run.</li>`;
  const docs = evidence.documents || [];
  $("#activity-docs tbody").innerHTML = docs.length
    ? docs.map((doc) => `<tr>
        <td><strong>${escapeHtml(doc.title)}</strong><small class="doc-id">${escapeHtml(doc.document_id.slice(0, 12))}</small></td>
        <td>${escapeHtml(doc.source_type)} · ${escapeHtml(doc.outlet)}</td>
        <td class="num">${escapeHtml(String(doc.published_at || "").slice(0, 10))}</td>
        <td class="${doc.within_cutoff ? "ok" : "warn"}">${doc.within_cutoff ? "inside epoch" : "blocked"}</td>
      </tr>`).join("")
    : `<tr><td colspan="4">No cited documents are saved for this run yet.</td></tr>`;
  setText("#evidence-count", `${queries.length} searches · ${docs.length} cited documents · ${evidence.n_tool_calls || 0} tool calls`);
}

async function loadActivity(quiet = false) {
  if (!state.selectedEra || !state.selectedRun) return;
  try {
    const q = new URLSearchParams({ epoch: state.selectedEra, run_id: state.selectedRun });
    const data = await getJSON(`/api/activity?${q}`);
    renderActivity(data);
  } catch (err) {
    if (!quiet) {
      setText("#activity-objective", `Could not load agent activity: ${String(err)}`);
      $("#seal-badge").dataset.status = "failed";
      setText("#seal-badge", "Status unavailable");
    }
  }
}

async function sealContainer(ev) {
  ev.preventDefault();
  if (state.resealing || !state.selectedEra) return;
  state.resealing = true;
  const source = $("#scope-select").value || "all";
  $("#scope-apply").disabled = true;
  $("#scope-apply").textContent = "Resealing…";
  setText("#scope-help", `Restarting the search sidecar on ${state.selectedEra}/${source}…`);
  try {
    const res = await fetch("/api/sandbox/select", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        epoch_id: state.selectedEra,
        source_type: source === "all" ? null : source,
      }),
    });
    if (!res.ok) {
      const payload = await res.json().catch(() => ({}));
      throw new Error(payload.detail || `HTTP ${res.status}`);
    }
    await loadActivity();
  } catch (err) {
    setText("#scope-help", `Container was not changed: ${String(err)}`);
  } finally {
    state.resealing = false;
    $("#scope-apply").textContent = "Seal container to this scope";
    await loadActivity(true);
  }
}

function renderLab() {
  const data = state.overview;
  if (!data) return;
  const tb = $("#overview-models tbody");
  tb.innerHTML = data.models
    .map(
      (m) => `<tr>
        <td class="num">${m.id}</td>
        <td>${m.label || m.id}</td>
        <td>${m.provider}</td>
        <td class="num">${m.declared_pretraining_cutoff}</td>
        <td>${m.is_instruction_tuned ? "yes" : "no"}</td>
      </tr>`
    )
    .join("");
  const labels = {
    questions: "Question set",
    corpus: "Corpus index",
    search: "Search + fetch API",
    predictions: "Predictions on disk",
    scores: "Score report",
  };
  $("#overview-connected").innerHTML = Object.entries(labels)
    .map(([key, label]) => {
      const on = data.connected[key];
      return `<li><span>${label}</span><span class="${on ? "ok" : "warn"}">${on ? "ready" : "empty"}</span></li>`;
    })
    .join("");
  const extra = [
    data.questions_source,
    data.index_source,
    data.cutoff_filter,
    ...(data.errors || []),
  ];
  $("#overview-errors").textContent = extra.filter(Boolean).join(" · ");
  const swarm = $("#overview-swarm");
  if (swarm && state.ready && state.ready.swarm_note) {
    swarm.textContent = state.ready.swarm_note;
  }
}

async function loadQuestions() {
  const cat = $("#q-category").value;
  const reveal = $("#reveal-truth").checked;
  state.reveal = reveal;
  const q = new URLSearchParams({ epoch: state.selectedEra });
  if (reveal) q.set("reveal_truth", "true");
  if (cat) q.set("category", cat);
  const data = await getJSON(`/api/questions?${q}`);
  state.questions = data;
  const select = $("#q-category");
  if (select.options.length <= 1) {
    for (const name of Object.keys(data.categories || {})) {
      const opt = document.createElement("option");
      opt.value = name;
      opt.textContent = `${name} (${data.categories[name]})`;
      select.appendChild(opt);
    }
    select.value = cat;
  }
  $("#q-count").textContent = `${data.n} questions`;
  document.querySelectorAll("#q-table .truth-col").forEach((el) => {
    el.hidden = !reveal;
  });
  $("#q-table tbody").innerHTML = data.questions
    .map((row) => {
      const prior = row.prior_signal ? fmt(row.prior_signal.probability, 2) : "—";
      const truth = reveal
        ? row.ground_truth === true
          ? "Yes"
          : row.ground_truth === false
            ? "No"
            : "—"
        : "withheld";
      return `<tr>
        <td class="num">${row.id}</td>
        <td>${row.category}</td>
        <td class="q-text">${row.text}</td>
        <td class="num">${prior}</td>
        <td>${row.generator}</td>
        <td class="truth-col">${truth}</td>
      </tr>`;
    })
    .join("");
}

async function loadCorpus() {
  const data = await getJSON(withEra("/api/corpus"));
  $("#corpus-assertion").textContent = `Only documents published on or before ${data.cutoff_date}. Leaked rows: ${data.n_leaked}.`;
  $("#search-status").textContent = `${data.n_documents} documents in the index`;
  if (!$("#search-table tbody").children.length) {
    $("#search-table tbody").innerHTML = data.documents
      .slice(0, 12)
      .map(
        (d) => `<tr>
          <td><button class="linkish" data-fetch="${d.document_id}">${d.document_id.slice(0, 12)}</button></td>
          <td>${d.title}</td>
          <td>${d.outlet}</td>
          <td class="num">${d.published_at.slice(0, 10)}</td>
          <td class="num">${fmt(d.prominence, 2)}</td>
          <td class="q-text">Open to read</td>
        </tr>`
      )
      .join("");
  }
}

async function runSearch(ev) {
  ev.preventDefault();
  const body = {
    query: $("#search-q").value,
    k: Number($("#search-k").value) || 8,
    min_prominence: Number($("#search-prom").value) || 0,
  };
  $("#search-status").textContent = "Searching…";
  if (window.Enchant) Enchant.setPose("search");
  const res = await fetch(`/api/eras/${encodeURIComponent(state.selectedEra)}/search`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    $("#search-status").textContent = `Search failed ${res.status}`;
    if (window.Enchant) Enchant.setPose("error");
    return;
  }
  const hits = await res.json();
  $("#search-status").textContent = `${hits.length} hits · all on or before cutoff`;
  if (window.Enchant) {
    Enchant.setPose("done");
    setTimeout(() => Enchant.setPose("idle"), 1800);
  }
  $("#search-table tbody").innerHTML = hits
    .map(
      (h) => `<tr>
        <td><button class="linkish" data-fetch="${h.document_id}">${h.document_id.slice(0, 12)}</button></td>
        <td>${h.title}</td>
        <td>${h.outlet}</td>
        <td class="num">${String(h.published_at).slice(0, 10)}</td>
        <td class="num">${fmt(h.prominence, 2)}</td>
        <td class="q-text">${h.snippet || ""}</td>
      </tr>`
    )
    .join("");
}

async function fetchDoc(id) {
  const res = await fetch(`/api/eras/${encodeURIComponent(state.selectedEra)}/fetch`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ document_id: id }),
  });
  if (!res.ok) return;
  const doc = await res.json();
  $("#fetch-panel").hidden = false;
  $("#fetch-title").textContent = doc.title;
  $("#fetch-meta").innerHTML = [
    ["ID", doc.id],
    ["Outlet", doc.outlet],
    ["Published", doc.published_at],
    ["Source", doc.source_type],
    ["Prominence", fmt(doc.prominence, 3)],
    ["URL", doc.url],
  ]
    .map(([k, v]) => `<div><dt>${k}</dt><dd>${v}</dd></div>`)
    .join("");
  $("#fetch-text").textContent = doc.text;
}

async function loadForecasts() {
  const runs = state.runs.length ? state.runs : (await getJSON(withEra("/api/runs"))).runs || [];
  fillRunSelect(runs, state.selectedRun);
  if (!state.selectedRun) {
    $("#forecasts-empty").hidden = false;
    $("#pred-table").hidden = true;
    return;
  }
  const reveal = $("#f-reveal").checked;
  const data = await getJSON(
    withEra(`/api/runs/${encodeURIComponent(state.selectedRun)}?reveal_truth=${reveal}`)
  );
  const modelSel = $("#f-model");
  const prev = modelSel.value;
  const models = data.models || [];
  modelSel.innerHTML = `<option value="">All models</option>` + models.map((m) => `<option value="${m}">${m}</option>`).join("");
  if (models.includes(prev)) modelSel.value = prev;
  const want = modelSel.value;
  let rows = data.predictions || [];
  if (want) rows = rows.filter((p) => p.model_id === want);
  $("#f-count").textContent = `${rows.length} of ${data.n_predictions} forecasts`;
  document.querySelectorAll("#pred-table .truth-col").forEach((el) => {
    el.hidden = !reveal;
  });
  if (!rows.length) {
    $("#forecasts-empty").hidden = false;
    $("#pred-table tbody").innerHTML = "";
    return;
  }
  $("#forecasts-empty").hidden = true;
  $("#pred-table").hidden = false;
  $("#pred-table tbody").innerHTML = rows
    .map((p) => {
      const truth = reveal
        ? p.ground_truth === true
          ? "Yes"
          : p.ground_truth === false
            ? "No"
            : "—"
        : "withheld";
      return `<tr>
        <td class="num">${p.model_id}</td>
        <td class="q-text">${p.question_text || p.question_id}</td>
        <td class="num">${pct(p.probability)}</td>
        <td class="num">${p.prior == null ? "—" : pct(p.prior)}</td>
        <td class="truth-col">${truth}</td>
        <td class="truth-col num">${p.item_brier == null ? "—" : fmt(p.item_brier)}</td>
        <td>${(p.search_queries || []).slice(0, 3).join(" · ")}</td>
      </tr>`;
    })
    .join("");
}

function tagFor(row) {
  if (row.reference) return "line to beat";
  if (row.kind === "baseline") return "simple rule";
  if (row.beats_prior) return "beats prior";
  if (row.delta_vs_prior != null && row.delta_vs_prior > 0) {
    return `${fmt(row.delta_vs_prior)} worse than prior`;
  }
  return "model";
}

function boardCell(kind, width, value, extraClass) {
  const w = width == null ? 0 : width;
  const mark = kind === "c" ? `<span class="chance-mark" title="0.50 = guessing"></span>` : "";
  return `<div class="metric-cell">
    <div class="pair">
      <div class="board-track">${mark}<span class="board-fill ${extraClass}" style="--w:${w}"></span></div>
      <div class="board-val">${value}</div>
    </div>
  </div>`;
}

async function loadScores() {
  const requested = state.selectedRun;
  const q = new URLSearchParams({ epoch: state.selectedEra });
  if (requested) q.set("run_id", requested);
  const data = await getJSON(`/api/scores?${q}`);
  const ex = data.explain || {};
  const verdict = ex.verdict || { tone: "empty", headline: "No scores yet.", detail: "" };
  $("#verdict").dataset.tone = verdict.tone || "empty";
  setText("#verdict-h", verdict.headline);
  setText("#verdict-d", verdict.detail || "");
  setText("#ranking-line", verdict.ranking || "");
  if (requested) {
    state.selectedRun = requested;
    const select = $("#run-select");
    if (select && [...select.options].some((o) => o.value === requested) && select.value !== requested) {
      select.value = requested;
    }
  } else if (ex.run_id) {
    state.selectedRun = ex.run_id;
    const select = $("#run-select");
    if (select && [...select.options].some((o) => o.value === ex.run_id)) select.value = ex.run_id;
  }

  const story = ex.story || [];
  $("#story").innerHTML = story
    .map(
      (s) => `<li>
        <span class="n">${s.step}</span>
        <div><h3>${s.title}</h3><p>${s.body}</p></div>
      </li>`
    )
    .join("");

  const metrics = ex.metrics || [];
  $("#metrics").innerHTML = metrics
    .map(
      (m) => `<article class="metric">
        <p class="short">${m.short}</p>
        <h3>${m.name}</h3>
        <p>${m.plain}</p>
        <span class="dir">${m.direction}</span>
      </article>`
    )
    .join("");

  const board = ex.scoreboard || [];
  $("#scoreboard").innerHTML = board.length
    ? board
        .map((row) => {
          const win = row.kind === "model" && row.beats_prior;
          const lose = row.kind === "model" && !row.beats_prior && row.delta_vs_prior != null;
          return `<div class="board-row" data-kind="${row.kind}" data-reference="${row.reference}" data-win="${win}" data-lose="${lose}">
            <div class="board-name">${row.label}<small>${row.note || row.id}</small><span class="board-tag">${tagFor(row)}</span></div>
            ${boardCell("brier", row.bar, fmt(row.brier), "brier-fill")}
            ${boardCell("c", row.c_bar, row.c_index == null ? "—" : fmt(row.c_index), "c-fill")}
          </div>`;
        })
        .join("")
    : `<p class="note">Scores appear once a run has been graded.</p>`;

  const facts = [
    ["This run", ex.run_label || data.run_id || "—"],
    ["Answers scored", ex.n_predictions || 0],
    ["Citations flagged", ex.n_flagged || 0],
    ["Score source", data.source || "—"],
  ];
  $("#result-facts").innerHTML = facts
    .map(([k, v]) => `<div><dt>${k}</dt><dd>${v}</dd></div>`)
    .join("");

  const cats = ex.brier_by_category || {};
  const catRows = [];
  Object.entries(cats).forEach(([mid, byCat]) => {
    Object.entries(byCat || {}).forEach(([cat, score]) => {
      catRows.push(`<tr><td class="num">${mid}</td><td>${cat}</td><td class="num">${fmt(score)}</td></tr>`);
    });
  });
  $("#cat-table tbody").innerHTML = catRows.length
    ? catRows.join("")
    : `<tr><td colspan="3">Topic split appears after a scored run.</td></tr>`;

  const report = data.report || {};
  const cal = report.calibration || {};
  if (!Object.keys(cal).length && data.prior_signal && data.prior_signal.calibration) {
    cal.prior_signal = data.prior_signal.calibration;
  }
  $("#cal-chart").innerHTML = reliabilitySVG(cal);
  const eces = Object.entries(cal)
    .map(([id, c]) => `${id} honesty gap ${fmt(c.ece)}`)
    .join(" · ");
  $("#cal-note").textContent = eces || "This chart needs forecasts with known outcomes.";
  $("#contam-note").textContent = ex.contamination_note || "";
  $("#contam-chart").innerHTML = contaminationSVG(report.contamination || []);
  await loadPlots(state.selectedRun || data.run_id);
}

async function loadPlots(runId) {
  const grid = $("#perf-plots");
  const empty = $("#perf-plots-empty");
  if (!grid) return;
  if (!runId) {
    grid.innerHTML = "";
    if (empty) empty.hidden = false;
    return;
  }
  try {
    const data = await getJSON(withEra(`/api/runs/${encodeURIComponent(runId)}/plots`));
    const plots = data.plots || [];
    if (!plots.length) {
      grid.innerHTML = "";
      if (empty) empty.hidden = false;
      return;
    }
    if (empty) empty.hidden = true;
    grid.innerHTML = plots
      .map((plot, i) => {
        const hero = plot.id === "vote_swarm" || (i === 0 && plots.length === 1);
        const plotUrl = new URL(withEra(plot.url), window.location.origin);
        plotUrl.searchParams.set("t", Date.now());
        const src = `${plotUrl.pathname}${plotUrl.search}`;
        return `<figure class="perf-plot${hero ? " hero" : ""}">
          <img src="${escapeHtml(src)}" alt="${escapeHtml(plot.title || "Performance chart")}" loading="lazy">
          <figcaption>
            <strong>${escapeHtml(plot.title || plot.id)}</strong>
            <span class="plot-question">Question: ${escapeHtml(plot.question || "What does this chart reveal?")}</span>
            <span>${escapeHtml(plot.caption || "")}</span>
            <span class="plot-good"><b>What good looks like:</b> ${escapeHtml(plot.good_result || "Closer to later truth with less error.")}</span>
          </figcaption>
        </figure>`;
      })
      .join("");
  } catch (err) {
    grid.innerHTML = "";
    if (empty) {
      empty.hidden = false;
      empty.textContent = "Charts could not be drawn for this run.";
    }
  }
}

function reliabilitySVG(curves) {
  const w = 360;
  const h = 220;
  const p = 36;
  const ids = Object.keys(curves);
  if (!ids.length) return `<p class="note">No calibration bins.</p>`;
  let paths = `<line x1="${p}" y1="${h - p}" x2="${w - p}" y2="${p}" stroke="#80ff20" stroke-dasharray="3 3"/>`;
  ids.forEach((id, i) => {
    const bins = (curves[id].bins || []).filter((b) => b.n);
    const color = i === 0 ? "#80ff20" : i === 1 ? "#ffffa0" : "#d4c4ff";
    const pts = bins
      .map((b) => {
        const x = p + b.mean_forecast * (w - 2 * p);
        const y = h - p - b.mean_outcome * (h - 2 * p);
        return `${x},${y}`;
      })
      .join(" ");
    paths += `<polyline fill="none" stroke="${color}" points="${pts}"/>`;
    bins.forEach((b) => {
      const x = p + b.mean_forecast * (w - 2 * p);
      const y = h - p - b.mean_outcome * (h - 2 * p);
      paths += `<circle cx="${x}" cy="${y}" r="3" fill="${color}"/>`;
    });
  });
  return `<svg viewBox="0 0 ${w} ${h}" role="img" aria-label="Calibration: forecast probability versus observed rate">
    ${paths}
    <text x="${p}" y="${h - 10}">Forecast 0</text>
    <text x="${w - 70}" y="${h - 10}">Forecast 1</text>
    <text x="8" y="${p}">Outcome 1</text>
  </svg>`;
}

function contaminationSVG(curves) {
  const w = 360;
  const h = 220;
  const p = 36;
  const ptsAll = [];
  curves.forEach((c) => {
    (c.buckets || []).forEach((b) => {
      if (!b.n || Number.isNaN(b.mean_accuracy)) return;
      ptsAll.push({ x: (b.gap_lo_days + b.gap_hi_days) / 2, y: b.mean_accuracy });
    });
  });
  if (!ptsAll.length) return `<p class="note">No usable leakage buckets for this epoch.</p>`;
  const xs = ptsAll.map((p0) => p0.x);
  const minX = Math.min(...xs, -10);
  const maxX = Math.max(...xs, 10);
  const xmap = (x) => p + ((x - minX) / (maxX - minX || 1)) * (w - 2 * p);
  const ymap = (y) => h - p - y * (h - 2 * p);
  const zero = xmap(0);
  let paths = `<line x1="${zero}" y1="${p}" x2="${zero}" y2="${h - p}" stroke="#ff6b6b"/>`;
  curves.forEach((c, i) => {
    const color = i === 0 ? "#80ff20" : i === 1 ? "#ffffa0" : "#d4c4ff";
    const pts = (c.buckets || [])
      .filter((b) => b.n && !Number.isNaN(b.mean_accuracy))
      .map((b) => `${xmap((b.gap_lo_days + b.gap_hi_days) / 2)},${ymap(b.mean_accuracy)}`)
      .join(" ");
    paths += `<polyline fill="none" stroke="${color}" points="${pts}"/>`;
  });
  return `<svg viewBox="0 0 ${w} ${h}" role="img" aria-label="Contamination: accuracy by days from training cutoff">
    ${paths}
    <text x="${p}" y="${h - 10}">Gap (days)</text>
    <text x="8" y="${p}">Accuracy</text>
  </svg>`;
}

function poseFromJob(job) {
  if (!window.Enchant) return;
  const status = job.status || "idle";
  const phase = job.phase || "";
  if (status === "running" && phase === "score") Enchant.setPose("maths");
  else if (status === "running") Enchant.setPose("search");
  else if (status === "error" && state.lastJobStatus === "running") Enchant.setPose("error");
  else if (status === "done" && state.lastJobStatus === "running") Enchant.setPose("done");
}

function jobKind(job) {
  if (job && job.kind) return job.kind;
  if (job && job.mock) return "mock";
  return "live";
}

function renderJob(job) {
  const status = job.status || "idle";
  const label = job.phase && status === "running" ? `${status} · ${job.phase}` : status;
  $("#run-state").dataset.status = status;
  $("#run-state").setAttribute("aria-busy", status === "running" ? "true" : "false");
  const spoken = {
    idle: "Idle",
    running: label === "running" ? "Running" : label.replace("running · ", "Running, "),
    done: "Done",
    error: job.error ? `Error: ${String(job.error).slice(0, 80)}` : "Error",
  };
  $("#run-state-label").textContent =
    job.error && status === "error" ? spoken.error : spoken[status] || label;
  const mockBtn = $("#run-btn");
  const liveBtn = $("#run-live-btn");
  const swarmBtn = $("#run-swarm-btn");
  const launchBtn = $("#swarm-launch");
  const busy = status === "running";
  const kind = jobKind(job);
  const liveOk = state.ready && state.ready.live_ready;
  const eraRunnable = state.ready && state.ready.run_epoch === state.selectedEra;
  mockBtn.disabled = busy || !eraRunnable;
  mockBtn.textContent = busy && kind === "mock" ? "Running…" : "Run practice";
  liveBtn.disabled = busy || !liveOk || !eraRunnable;
  liveBtn.textContent = busy && kind === "live" ? "Running…" : "Run live mix";
  mockBtn.title = eraRunnable
    ? "Run the configured practice experiment for this era"
    : `No practice run config targets ${state.selectedEra || "this era"} yet`;
  liveBtn.title = !eraRunnable
    ? `No live run config targets ${state.selectedEra || "this era"} yet`
    : liveOk
    ? "Score each of the six OpenRouter species once on 1 question (not the 12-agent swarm)"
    : "Add OPENROUTER_API_KEY, or both ANTHROPIC_API_KEY and OPENAI_API_KEY, to .env";
  if (swarmBtn) {
    swarmBtn.disabled = busy || !liveOk || !eraRunnable;
    swarmBtn.textContent = busy && kind === "swarm" ? "Running…" : "Run configured swarm";
    swarmBtn.title = !eraRunnable
      ? `No swarm run config targets ${state.selectedEra || "this era"} yet`
      : liveOk
      ? "Launch the roster and question count configured in the Runs tab"
      : "Add OPENROUTER_API_KEY to .env for a configured swarm";
  }
  if (launchBtn) {
    const estimate = updateSwarmEstimate();
    launchBtn.disabled = busy || !liveOk || !eraRunnable || estimate.invalid;
    launchBtn.textContent = busy && kind === "swarm" ? "Swarm running…" : "Run this swarm";
  }
  const log = (job.log || []).join("\n");
  const band = $("#run-log-band");
  if (status === "idle" && !log) {
    band.hidden = true;
  } else {
    band.hidden = false;
    $("#run-log").textContent = log || "(no output yet)";
    $("#run-log").scrollTop = $("#run-log").scrollHeight;
  }
  poseFromJob(job);
}

async function pollJob() {
  try {
    const job = await getJSON("/api/jobs/run");
    const prev = state.lastJobStatus;
    renderJob(job);
    if (job.status === "running") {
      if (!state.jobTimer) state.jobTimer = setInterval(pollJob, 1000);
    } else if (state.jobTimer) {
      clearInterval(state.jobTimer);
      state.jobTimer = null;
    }
    if (prev === "running" && (job.status === "done" || job.status === "error")) {
      await refreshAfterJob(job.run_id);
      if (job.status === "done") setView("results");
    }
    state.lastJobStatus = job.status;
    state.lastJobRunId = job.run_id;
  } catch (err) {
    $("#run-state-label").textContent = "error";
    $("#run-state").dataset.status = "error";
  }
}

async function refreshAfterJob(runId) {
  if (runId) state.selectedRun = runId;
  await loadOverview();
  await loadScores();
  await loadForecasts();
}

async function startSimulation(kind) {
  const mockBtn = $("#run-btn");
  const liveBtn = $("#run-live-btn");
  const swarmBtn = $("#run-swarm-btn");
  mockBtn.disabled = true;
  liveBtn.disabled = true;
  if (swarmBtn) swarmBtn.disabled = true;
  const custom = kind === "swarm" ? updateSwarmEstimate() : null;
  if (custom && custom.invalid) {
    setView("runs");
    return;
  }
  const starting = {
    mock: "Starting practice (keyword lookup)…",
    live: "Starting live mix (6 species × 1 question)…",
    swarm: `Starting swarm (${custom ? custom.agents : 12} sequential votes × ${custom ? custom.questions : 1} questions)…`,
  };
  if (kind === "mock") mockBtn.textContent = "Running…";
  else if (kind === "swarm" && swarmBtn) swarmBtn.textContent = "Running…";
  else liveBtn.textContent = "Running…";
  $("#run-log-band").hidden = false;
  $("#run-log").textContent = starting[kind] || "Starting…";
  if (window.Enchant) Enchant.setPose("search");
  const res = await fetch("/api/jobs/run", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      kind,
      mock: kind === "mock",
      epoch_id: state.selectedEra,
      isolated_retrieval: true,
      source_type:
        state.activity && state.activity.access && state.activity.access.selection !== "all"
          ? state.activity.access.selection
          : null,
      label: kind === "swarm" ? ($("#swarm-label").value || null) : null,
      n_questions: kind === "swarm" ? custom.questions : null,
      swarm_bodies: kind === "swarm" ? custom.bodies : null,
    }),
  });
  if (res.status === 409) {
    await pollJob();
    return;
  }
  if (res.status === 412 || !res.ok) {
    let detail = await res.text();
    try {
      detail = JSON.parse(detail).detail || detail;
    } catch (_err) {
      // Keep a plain-text server response as-is.
    }
    $("#run-state").dataset.status = "error";
    $("#run-state-label").textContent = "error";
    $("#run-log").textContent = `Start failed ${res.status}: ${detail}`;
    mockBtn.disabled = false;
    mockBtn.textContent = "Run practice";
    liveBtn.textContent = "Run live mix";
    if (swarmBtn) swarmBtn.textContent = "Run configured swarm";
    applyReady(state.ready);
    if (window.Enchant) Enchant.setPose("error");
    return;
  }
  const started = await res.json();
  state.selectedRun = started.run_id || state.selectedRun;
  renderJob(started);
  state.lastJobStatus = "running";
  setView("activity");
  await pollJob();
}

function applyReady(ready) {
  state.ready = ready || state.ready;
  const mockBtn = $("#run-btn");
  const liveBtn = $("#run-live-btn");
  const swarmBtn = $("#run-swarm-btn");
  const ok = state.ready && state.ready.live_ready;
  const eraRunnable = state.ready && state.ready.run_epoch === state.selectedEra;
  if (state.ready && state.ready.swarm_options) {
    renderSwarmBuilder(state.ready.swarm_options);
  }
  if (state.lastJobStatus !== "running") {
    if (mockBtn) mockBtn.disabled = !eraRunnable;
    if (liveBtn) liveBtn.disabled = !ok || !eraRunnable;
    if (swarmBtn) swarmBtn.disabled = !ok || !eraRunnable;
  }
  updateSwarmEstimate();
}

function bind() {
  bindTablist();
  $("#reveal-truth").addEventListener("change", loadQuestions);
  $("#q-category").addEventListener("change", loadQuestions);
  $("#search-form").addEventListener("submit", runSearch);
  $("#scope-form").addEventListener("submit", sealContainer);
  $("#run-btn").addEventListener("click", () => startSimulation("mock"));
  $("#run-live-btn").addEventListener("click", () => startSimulation("live"));
  const swarmBtn = $("#run-swarm-btn");
  if (swarmBtn) swarmBtn.addEventListener("click", () => startSimulation("swarm"));
  $("#swarm-builder").addEventListener("submit", (ev) => {
    ev.preventDefault();
    startSimulation("swarm");
  });
  $("#swarm-preset").addEventListener("change", () => {
    const preset = $("#swarm-preset").value;
    if (preset !== "custom") applySwarmPreset(preset);
  });
  $("#swarm-composition").addEventListener("input", (ev) => {
    if (!ev.target.matches("[data-swarm-model]")) return;
    $("#swarm-preset").value = "custom";
    updateSwarmEstimate();
  });
  $("#swarm-questions").addEventListener("input", updateSwarmEstimate);
  $("#saved-log-close").addEventListener("click", () => {
    $("#saved-log").hidden = true;
  });
  $("#run-select").addEventListener("change", async () => {
    state.selectedRun = $("#run-select").value || null;
    try {
      await loadScores();
      await loadForecasts();
      if (location.hash === "#activity") await loadActivity();
      renderRunHistory(state.runs);
    } catch (err) {
      console.error("Failed to load run", state.selectedRun, err);
    }
  });
  $("#f-model").addEventListener("change", loadForecasts);
  $("#f-reveal").addEventListener("change", loadForecasts);
  document.body.addEventListener("click", (ev) => {
    const eraBtn = ev.target.closest("[data-era]");
    if (eraBtn) selectEra(eraBtn.dataset.era);
    const fetchBtn = ev.target.closest("[data-fetch]");
    if (fetchBtn) fetchDoc(fetchBtn.dataset.fetch);
    const resultBtn = ev.target.closest("[data-run-results]");
    if (resultBtn) openSavedRun(resultBtn.dataset.runResults);
    const logBtn = ev.target.closest("[data-run-log]");
    if (logBtn) loadSavedLog(logBtn.dataset.runLog);
    const architectureNode = ev.target.closest("[data-arch-node]");
    if (architectureNode) renderArchitecture(architectureNode.dataset.archNode);
  });
  window.addEventListener("hashchange", () => setView(location.hash.replace("#", "")));
}

async function boot() {
  bind();
  try {
    await loadEras();
  } catch (err) {
    setText("#era-note", `Could not load the epoch registry: ${String(err)}`);
  }
  try {
    state.ready = await getJSON("/api/jobs/ready");
    applyReady(state.ready);
  } catch (err) {
    applyReady({ live_ready: false });
  }
  try {
    await loadOverview();
    await loadActivity(true);
  } catch (err) {
    $("#overview-errors").textContent = String(err);
  }
  const hash = location.hash.replace("#", "");
  const preferred = pickPreferredRun(state.runs || []);
  const preferredHas = (state.runs || []).some(
    (r) => r.run_id === preferred && r.n_predictions > 0
  );
  if (preferredHas && !hash) setView("eras");
  else setView(hash || "eras");
  pollJob();
}

boot();
