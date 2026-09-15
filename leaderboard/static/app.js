const ALIASES = { overview: "results", scoring: "results" };
const VIEWS = ["eras", "activity", "leaderboard", "runs", "architecture", "population", "results", "forecasts", "questions", "corpus", "lab"];
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
  activityQuestion: null,
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
  population: null,
  agentView: "graph",
  geographyView: "map",
  geographyCatalog: null,
  geographyLayer: "states",
  geographyPayload: null,
  geographyRequestToken: 0,
  geographySelection: { level: "nation", id: "us:1" },
  datasetKind: "population",
  datasetLayerId: null,
  datasetCompareLayerId: null,
  mapShadeMode: "density",
  populationSelection: null,
  leaderboard: null,
  leaderboardMode: "agents",
  leaderboardMetric: "score",
  leaderboardCorporation: "",
};

const GEOGRAPHY_CACHE = new Map();

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
    leaderboard: "Leaderboard",
    runs: "Runs",
    architecture: "Architecture",
    population: "Population",
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
  if (name === "leaderboard") loadLeaderboard();
  if (name === "runs") renderRunHistory(state.runs);
  if (name === "architecture") renderArchitecture(state.architectureNode);
  if (name === "population") loadPopulation();
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
    active
      ? active.has_corpus
        ? `${active.n_documents} generated documents · ${active.n_questions} questions`
        : `tracked practice fixtures in memory · ${active.n_questions} questions`
      : "—"
  );
  grid.innerHTML = state.eras.length
    ? state.eras
        .map((era) => {
          const on = era.id === state.selectedEra;
          const sources = (era.source_types || []).length
            ? era.source_types.join(" · ")
            : era.practice_ready
              ? "Tracked practice fixtures · generated index absent"
              : "No indexed source silos yet";
          const missing = [
            !era.has_corpus ? "corpus" : "",
            !era.has_questions ? "questions" : "",
          ].filter(Boolean);
          const status = era.isolated_run_ready
            ? on ? "Selected · run assets built" : "Ready to select"
            : era.practice_ready
              ? on ? "Selected · inspect only" : "Practice inspection available"
              : `Needs ${missing.join(" + ")}`;
          return `<button type="button" class="era-card" data-era="${escapeHtml(era.id)}" aria-pressed="${on}" ${era.ready ? "" : "disabled"}>
            <span class="era-card-top"><strong>${escapeHtml(String(era.year))}</strong><span class="era-status" data-ready="${era.ready}">${escapeHtml(status)}</span></span>
            <span class="era-dates">Freeze ${escapeHtml(era.cutoff_date)} → resolve by ${escapeHtml(era.resolution_window_end)}</span>
            <span class="era-counts"><b>${era.n_documents}</b> generated documents <b>${era.n_questions}</b> questions</span>
            <span class="era-sources">${escapeHtml(sources)}</span>
          </button>`;
        })
        .join("")
    : `<p class="empty">No epochs are configured.</p>`;
  const readyCount = state.eras.filter((era) => era.ready).length;
  const configured = state.eras.length;
  const runnableCount = state.eras.filter((era) => era.isolated_run_ready).length;
  const suffix = configured === 1
    ? "Tracked fixtures remain inspectable without creating files; an isolated run needs prepared assets and a verified sidecar."
    : "Each prepared era stays isolated from every other era.";
  setText("#era-note", `${readyCount} of ${configured} eras inspectable; ${runnableCount} have generated run assets. ${suffix}`);
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
  state.population = null;
  state.leaderboard = null;
  state.geographySelection = { level: "nation", id: "us:1" };
  state.populationSelection = null;
  state.selectedRun = null;
  state.activityQuestion = null;
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
    await loadReady();
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
  const maximumRequests = calls * 2;
  const ceiling = Number(options.ceiling || 100);
  const guard = options.cost_controls || {};
  const requestCeiling = Number(guard.max_paid_requests || 0);
  const maxRunUsd = Number(guard.max_run_usd || 0);
  const prices = new Map(
    (options.species || []).map((model) => [model.model_id, Number(model.estimated_usd_per_request || 0)])
  );
  const estimatedMaxUsd = bodies.reduce(
    (sum, row) => sum + row.count * questions * 2 * (prices.get(row.model_id) || 0),
    0
  );
  const countInvalid = agents < 1 || agents > ceiling;
  const requestInvalid = requestCeiling > 0 && maximumRequests > requestCeiling;
  const costInvalid = maxRunUsd > 0 && estimatedMaxUsd > maxRunUsd;
  const invalid = countInvalid || requestInvalid || costInvalid;
  setText("#swarm-total", `${agents} agent${agents === 1 ? "" : "s"}`);
  setText(
    "#swarm-calls",
    `${calls} planned call${calls === 1 ? "" : "s"} · up to ${maximumRequests} with JSON retries`
  );
  setText(
    "#swarm-estimate",
    `At least ${durationWords(calls * Number(options.minimum_seconds_per_call || 2))}, plus provider latency. Conservative local ceiling estimate: $${estimatedMaxUsd.toFixed(3)}.`
  );
  let error = "";
  if (countInvalid) error = `Choose between 1 and ${ceiling} total agents.`;
  else if (requestInvalid) error = `This run can attempt ${maximumRequests} paid requests; the local limit is ${requestCeiling}.`;
  else if (costInvalid) error = `The $${estimatedMaxUsd.toFixed(3)} estimate exceeds the local $${maxRunUsd.toFixed(2)} run limit.`;
  setText(
    "#swarm-builder-error",
    error
  );
  const launch = $("#swarm-launch");
  const liveOk = Boolean(state.ready && state.ready.live_ready);
  const eraRunnable = Boolean(state.ready && state.ready.run_epoch === state.selectedEra);
  const practiceOk = Boolean(state.ready && state.ready.practice_ready && eraRunnable);
  if (launch) {
    launch.disabled = invalid || state.lastJobStatus === "running" || !liveOk || !practiceOk;
    launch.title = !eraRunnable
      ? `No swarm run config targets ${state.selectedEra || "this era"} yet`
      : !practiceOk
        ? state.ready.practice_blocking_reason || "Prepare and seal the frozen corpus first"
      : !liveOk
        ? state.ready.live_blocking_reason || "Live research prerequisites are incomplete"
        : error || "Run this bounded, preflighted swarm";
  }
  if (state.populationSelection) {
    state.populationSelection.n_agents = agents;
    renderPopulationLens();
  }
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
        const population = run.population_selection || null;
        return `<tr data-selected="${selected}">
          <td><strong>${escapeHtml(run.label || run.run_id)}</strong><small>${escapeHtml(when)} · ${escapeHtml(run.source_type || "all")} sources</small><code>${escapeHtml(run.run_id)}</code></td>
          <td class="run-swarm-cell"><b>${Number(run.n_agents || 0)}</b><small>${escapeHtml(rosterSummary(run.composition))}</small>${population ? `<small class="run-population">Weighted to ${escapeHtml(population.label || population.population_id)}</small>` : ""}</td>
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
  state.activityQuestion = null;
  fillRunSelect(state.runs, runId);
  await loadScores();
  await loadForecasts();
  if (view === "activity") await loadActivity();
  setView(view);
}

async function loadSavedLog(runId) {
  const data = await getJSON(withEra(`/api/runs/${encodeURIComponent(runId)}/log`));
  const run = data.run || {};
  if (location.hash !== "#runs") setView("runs");
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

function median(values) {
  const rows = values.filter((value) => Number.isFinite(value)).sort((a, b) => a - b);
  if (!rows.length) return null;
  const middle = Math.floor(rows.length / 2);
  return rows.length % 2 ? rows[middle] : (rows[middle - 1] + rows[middle]) / 2;
}

function agentChainMarkup(data, compact = false) {
  const run = data && data.run ? data.run : {};
  const evidence = data && data.evidence ? data.evidence : {};
  const agents = data && data.agents ? data.agents : [];
  const probabilities = agents
    .filter((agent) => agent.probability != null)
    .map((agent) => Number(agent.probability))
    .filter((value) => Number.isFinite(value));
  if (!run.chain_available) {
    return `<div class="chain-unavailable">
      <strong>Question-scoped swarm chain unavailable</strong>
      <span>${escapeHtml(run.chain_reason || "Choose a shared-retrieval swarm run with saved votes.")}</span>
    </div>`;
  }
  const aggregate = median(probabilities);
  const selection = run.population_selection || null;
  const populationLine = selection
    ? `<span class="chain-population">Weighted to ${escapeHtml(selection.label || selection.population_id)}</span>`
    : `<span class="chain-population muted">Default explicit persona panel</span>`;
  const agentButtons = agents.length
    ? agents
        .map((agent) => {
          const status = agent.status || "queued";
          const probability = agent.probability == null ? "—" : pct(agent.probability);
          const label = `${agent.model_label || agent.agent_id}, ${agent.persona_label || "unassigned"}, ${status}${agent.probability == null ? "" : `, vote ${probability}`}`;
          return `<button type="button" class="chain-agent" data-status="${escapeHtml(status)}" data-agent-open="${Number(agent.index || 1) - 1}" aria-label="${escapeHtml(label)}">
            <span class="chain-agent-index">${String(agent.index || 0).padStart(2, "0")}</span>
            <span class="chain-agent-body"><strong>${escapeHtml(agent.model_label || agent.agent_id)}</strong><small>${escapeHtml(agent.persona_label || "Unassigned simulation role")}</small></span>
            <span class="chain-agent-vote">${probability}</span>
          </button>`;
        })
        .join("")
    : `<p class="chain-empty">No agent roster is attached to this run.</p>`;
  const complete = Number(run.n_complete || 0);
  const total = Number(run.n_agents || agents.length || 0);
  return `<div class="chain-canvas${compact ? " is-compact" : ""}">
    <section class="chain-stage chain-origin" aria-label="Frozen experiment source">
      <span class="chain-stage-label">01 · SOURCE</span>
      <strong>${escapeHtml((data.epoch && data.epoch.id) || state.selectedEra || "Epoch")}</strong>
      <small>world sealed ${escapeHtml((data.epoch && data.epoch.cutoff_date) || "at cutoff")}</small>
    </section>
    <span class="chain-link" aria-hidden="true"><i></i></span>
    <section class="chain-stage chain-pack" aria-label="Shared evidence pack">
      <span class="chain-stage-label">02 · SHARED PACK</span>
      <strong>${Number((evidence.documents || []).length)} cited docs</strong>
      <small>${Number((evidence.queries || []).length)} searches · ${(evidence.n_tool_calls || 0)} calls</small>
    </section>
    <span class="chain-link branch" aria-hidden="true"><i></i></span>
    <section class="chain-agent-field" aria-label="Independent sequential agent votes">
      <header><span>03 · INDEPENDENT VOTES</span>${populationLine}</header>
      <div class="chain-agent-grid">${agentButtons}</div>
      <p class="execution-rail"><span>${complete}/${total} returned</span><i aria-hidden="true"></i><span>execution order only</span></p>
    </section>
    <span class="chain-link merge" aria-hidden="true"><i></i></span>
    <section class="chain-stage chain-aggregate" aria-label="Swarm aggregate">
      <span class="chain-stage-label">04 · MEDIAN</span>
      <strong>${aggregate == null ? "—" : pct(aggregate)}</strong>
      <small>${probabilities.length} saved vote${probabilities.length === 1 ? "" : "s"}</small>
    </section>
  </div>`;
}

function setAgentView(mode) {
  state.agentView = mode === "list" ? "list" : "graph";
  const graph = $("#agent-chain-live");
  const list = $("#agent-grid");
  if (graph) graph.hidden = state.agentView !== "graph";
  if (list) list.hidden = state.agentView !== "list";
  document.querySelectorAll("[data-agent-view]").forEach((button) => {
    button.setAttribute("aria-pressed", String(button.dataset.agentView === state.agentView));
  });
}

function renderAgentChains(data) {
  const live = $("#agent-chain-live");
  if (live) {
    live.innerHTML = agentChainMarkup(data);
    live.setAttribute("aria-busy", data.run && data.run.status === "running" ? "true" : "false");
  }
  const results = $("#agent-chain-results");
  if (results) results.innerHTML = agentChainMarkup(data, true);
  setAgentView(state.agentView);
}

function renderChainQuestionPickers(run) {
  const questions = run.chain_questions || [];
  document.querySelectorAll("[data-chain-question]").forEach((select) => {
    const field = select.closest(".chain-question-picker");
    if (field) field.hidden = !run.chain_available || questions.length <= 1;
    select.innerHTML = questions
      .map(
        (question, index) => `<option value="${escapeHtml(question.id)}">${index + 1}. ${escapeHtml(question.label)}</option>`
      )
      .join("");
    select.value = run.chain_question_id || "";
  });
}

function renderActivity(data) {
  state.activity = data;
  const experiment = data.experiment || {};
  const run = data.run || {};
  const access = data.access || {};
  const agents = data.agents || [];
  const evidence = data.evidence || {};
  renderChainQuestionPickers(run);
  setText("#agents-heading", run.chain_available ? "Agent chain map" : "Agent run detail");
  setText(
    "#shared-retrieval-note",
    run.chain_available
      ? `Question-scoped view — ${run.chain_question_label || run.chain_question_id} Agents share this question’s sealed pack, vote independently, and do not influence one another.`
      : run.chain_reason || "This run does not expose a truthful shared-retrieval chain."
  );
  setText(
    "#result-chain-heading",
    run.chain_available ? "How this swarm reached the result" : "Agent chain not available"
  );
  setText(
    "#result-chain-note",
    run.chain_available
      ? `Question-scoped view — ${run.chain_question_label || run.chain_question_id} One frozen pack, independent votes, one median.`
      : run.chain_reason || "This saved run does not contain a question-scoped swarm chain."
  );
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
  renderAgentChains(data);

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
        <td>${escapeHtml(doc.source_type)} · ${escapeHtml(doc.outlet)}<small>${escapeHtml(doc.authenticity || "unverified")}</small></td>
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
    if (state.activityQuestion) q.set("question_id", state.activityQuestion);
    const data = await getJSON(`/api/activity?${q}`);
    state.activityQuestion = data.run && data.run.chain_question_id
      ? data.run.chain_question_id
      : null;
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
      headers: { "Content-Type": "application/json", "X-PSBX-CSRF": "1" },
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
    await loadReady();
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

function formatBytes(bytes) {
  const value = Number(bytes || 0);
  if (!value) return "—";
  return `${(value / 1_000_000_000).toFixed(2)} GB`;
}

function populationProfiles() {
  return (((state.population || {}).explorer || {}).profiles || []);
}

function profileById(populationId) {
  return populationProfiles().find((profile) => profile.population_id === populationId) || null;
}

function stateByFips(fips) {
  return (((state.population || {}).census || {}).states || []).find(
    (area) => String(area.fips) === String(fips)
  ) || null;
}

function profileForState(area, type = "state") {
  if (!area) return null;
  return populationProfiles().find(
    (profile) => profile.geography?.state_fips === area.fips && profile.geography?.type === type
  ) || null;
}

function canonicalGeographyId(value) {
  return String(value || "").replace(/^district:/, "congressional_district:");
}

function profileForGeographyId(geographyId) {
  const canonical = canonicalGeographyId(geographyId);
  return populationProfiles().find(
    (profile) => canonicalGeographyId(profile.geography?.id) === canonical
  ) || null;
}

function selectedGeographyProfile() {
  const selection = state.geographySelection || {};
  if (selection.populationId) return profileById(selection.populationId);
  const exact = profileForGeographyId(selection.id);
  if (exact) return exact;
  if (selection.level === "state") return profileForState(stateByFips(selection.stateFips));
  if (selection.level === "nation") {
    return populationProfiles().find(
      (profile) => profile.population_id === "national-us-e2012" || profile.geography?.id === "us:1"
    ) || null;
  }
  return null;
}

function geographyButton(area, mode) {
  const profile = profileForState(area);
  const status = profile && profile.runnable ? "profile" : area.ready ? "sources" : "planned";
  const selected = state.geographySelection && state.geographySelection.stateFips === area.fips;
  return `<button type="button" class="geography-tile ${mode === "map" ? "map-tile" : "box-tile"}" data-geo-state="${escapeHtml(area.fips)}" data-status="${status}" aria-pressed="${selected}">
    <strong>${escapeHtml(area.abbreviation)}</strong>
    <span>${escapeHtml(area.name)}</span>
    <small>${Number(area.district_count || 1)} House district${Number(area.district_count || 1) === 1 ? "" : "s"} · ${profile?.runnable ? "profile ready" : "profile missing"}</small>
  </button>`;
}

function geographySelectionForProfile(profile) {
  const isNation = profile.population_id === "national-us-e2012" || profile.geography.id === "us:1";
  return {
    level: isNation ? "nation" : profile.geography.type || "area",
    id: profile.geography.id,
    label: profile.label,
    stateFips: profile.geography.state_fips,
    populationId: profile.population_id,
  };
}

function chooseGeography(selection) {
  if (selection?.level === "state" && selection.stateFips && state.geographyLayer === "states") {
    state.geographyLayer = "congressional";
  }
  state.geographySelection = selection;
  renderGeographyExplorer(state.population);
}

function dataCatalog() {
  return (state.population || {}).data_catalog || { kinds: [], layers: [] };
}

function selectedDataLayer() {
  const catalog = dataCatalog();
  return (catalog.layers || []).find((layer) => layer.id === state.datasetLayerId) || null;
}

function selectedCompareLayer() {
  const catalog = dataCatalog();
  return (catalog.layers || []).find((layer) => layer.id === state.datasetCompareLayerId) || null;
}

function displayDataLayers() {
  const catalog = dataCatalog();
  return (catalog.layers || []).filter(
    (layer) => layer.kind !== "population" || layer.id === catalog.default_layer_id
  );
}

function coverageRowForArea(layer, area) {
  if (!layer || !area) return null;
  const rows = layer.coverage_by_state || {};
  return rows[area.fips] || rows[area.abbreviation] || null;
}

function coverageLevelIds(row, level) {
  if (!row) return [];
  const ids = (row.geography_ids || {})[level] || [];
  return Array.isArray(ids) ? ids.map(canonicalGeographyId) : [];
}

function layerCoversFeature(layer, area, level, geographyId) {
  const row = coverageRowForArea(layer, area);
  if (!row) return false;
  const levels = row.geography_levels || row.levels || layer.geography_levels || [];
  if (!levels.includes(level)) return false;
  const ids = coverageLevelIds(row, level);
  return !ids.length || ids.includes(canonicalGeographyId(geographyId));
}

function currentDatasetSelection() {
  const layer = selectedDataLayer();
  if (!layer) return null;
  const supportedLevels = new Set([
    "nation",
    "state",
    "congressional_district",
    "state_legislative_upper",
    "state_legislative_lower",
    "county",
    "municipality",
    "precinct",
  ]);
  const activeLevel = state.geographySelection?.level || "all";
  const selection = {
    kind: layer.kind,
    layer_id: layer.id,
    year: "all",
    geography_level: supportedLevels.has(activeLevel) ? activeLevel : "all",
  };
  if (state.datasetCompareLayerId) selection.compare_layer_id = state.datasetCompareLayerId;
  return selection;
}

function renderDataControls() {
  const catalog = dataCatalog();
  const kinds = catalog.kinds || [];
  const layers = displayDataLayers();
  if (!state.datasetLayerId) state.datasetLayerId = catalog.default_layer_id || layers[0]?.id || null;
  const currentLayer = layers.find((layer) => layer.id === state.datasetLayerId) || layers[0] || null;
  if (currentLayer) {
    state.datasetLayerId = currentLayer.id;
    state.datasetKind = currentLayer.kind;
  }

  const kindSelect = $("#dataset-kind");
  if (kindSelect) {
    kindSelect.innerHTML = kinds.map(
      (kind) => `<option value="${escapeHtml(kind.id)}">${escapeHtml(kind.label)}</option>`
    ).join("");
    kindSelect.value = state.datasetKind;
  }
  const primary = $("#dataset-layer");
  const familyLayers = layers.filter((layer) => layer.kind === state.datasetKind);
  if (primary) {
    primary.innerHTML = familyLayers.length
      ? familyLayers.map((layer) => `<option value="${escapeHtml(layer.id)}">${escapeHtml(layer.label)} · ${escapeHtml(layer.status || "registered")}</option>`).join("")
      : `<option value="">No imported ${escapeHtml(state.datasetKind)} layers</option>`;
    if (!familyLayers.some((layer) => layer.id === state.datasetLayerId)) {
      state.datasetLayerId = familyLayers[0]?.id || null;
    }
    primary.value = state.datasetLayerId || "";
  }
  const compare = $("#dataset-compare-layer");
  if (compare) {
    const choices = layers.filter((layer) => layer.id !== state.datasetLayerId);
    compare.innerHTML = `<option value="">No comparison</option>` + choices.map(
      (layer) => `<option value="${escapeHtml(layer.id)}">${escapeHtml(layer.label)}</option>`
    ).join("");
    if (!choices.some((layer) => layer.id === state.datasetCompareLayerId)) {
      state.datasetCompareLayerId = null;
    }
    compare.value = state.datasetCompareLayerId || "";
  }
  const geoLayer = $("#geography-layer");
  if (geoLayer) geoLayer.value = state.geographyLayer;
  const shade = $("#map-shade-mode");
  if (shade) shade.value = state.mapShadeMode;
}

function demographicBars(profile) {
  if (!profile || !profile.demographics || !profile.demographics.length) return "";
  return profile.demographics
    .map((group, index) => {
      const categories = (group.categories || []).slice(0, 5);
      const visibleShare = categories.reduce((sum, category) => sum + Number(category.share || 0), 0);
      if (visibleShare < 0.995) {
        categories.push({ label: "All other groups", share: Math.max(0, 1 - visibleShare) });
      }
      const bars = categories
        .map((category) => `<li>
          <span>${escapeHtml(category.label)}</span>
          <div><i style="--share:${Math.max(0, Math.min(1, Number(category.share || 0)))}"></i></div>
          <b>${pct(category.share)}</b>
        </li>`)
        .join("");
      return `<details class="demographic-group"${index < 2 ? " open" : ""}>
        <summary>${escapeHtml(group.label)}</summary>
        <ul>${bars}</ul>
      </details>`;
    })
    .join("");
}

function projectionForAgentCount(nAgents) {
  return ((state.swarmOptions || {}).representative_swarm_projections || []).find(
    (row) => Number(row.representative_agents || row.agents) === Number(nAgents)
  ) || null;
}

function renderRepresentativeAgentOptions() {
  const select = $("#population-agent-count");
  if (!select) return;
  const previous = Number(select.value || 12);
  const options = state.swarmOptions || {};
  const counts = options.representative_agent_counts || [12, 25, 50, 100];
  const labels = { 12: "quick panel", 25: "broader panel", 50: "default paid limit", 100: "maximum" };
  select.innerHTML = counts.map((count) => {
    const projection = projectionForAgentCount(count);
    const suffix = projection?.status === "blocked" ? " · blocked by current caps" : "";
    return `<option value="${Number(count)}">${Number(count)} · ${labels[count] || "representatives"}${suffix}</option>`;
  }).join("");
  select.value = counts.includes(previous) ? String(previous) : String(counts[0] || 12);
}

function renderPopulationCostEnvelope(profile) {
  renderRepresentativeAgentOptions();
  const options = state.swarmOptions || {};
  const guard = options.cost_controls || {};
  const nAgents = Number($("#population-agent-count")?.value || 12);
  const projection = projectionForAgentCount(nAgents);
  setText("#cost-mode-state", guard.enabled ? "ENABLED" : "OFF");
  setText(
    "#cost-agent-cap",
    `${Number(options.paid_agent_ceiling_per_question || 0)} per question`
  );
  setText(
    "#cost-run-cap",
    guard.max_run_usd == null ? "not configured" : `$${Number(guard.max_run_usd).toFixed(2)}`
  );
  setText(
    "#cost-estimate",
    projection
      ? `${Number(projection.maximum_requests || 0)} reserved requests · ≤$${Number(projection.estimated_max_usd || 0).toFixed(3)} · ${String(projection.status || "unknown").replaceAll("_", " ")}`
      : "projection unavailable"
  );
  const use = $("#population-swarm-use");
  if (use) {
    const capBlocked = projection?.status === "blocked";
    use.disabled = !(profile && profile.runnable) || capBlocked;
    use.title = capBlocked
      ? (projection.blocking_reasons || ["Current local spending caps block this size."]).join(" ")
      : "Configure this representative population in the Runs workspace";
  }
}

function selectedMapFeature() {
  const features = state.geographyPayload?.feature_collection?.features || [];
  const selectedId = canonicalGeographyId(state.geographySelection?.id);
  return features.find(
    (feature) => canonicalGeographyId(feature.id || feature.properties?.id) === selectedId
  ) || null;
}

function renderDatasetReadout(area) {
  const layer = selectedDataLayer();
  const compare = selectedCompareLayer();
  const selection = state.geographySelection || {};
  let coverage = false;
  if (selection.level === "nation") {
    coverage = Boolean(layer && (layer.states || []).length);
  } else if (area) {
    coverage = layerCoversFeature(layer, area, selection.level, selection.id);
  }
  const stateLabel = !layer
    ? "No dataset imported for this family"
    : coverage
      ? `${layer.label} · coverage found`
      : `${layer.label} · no matching coverage at this level`;
  setText("#geography-data-state", stateLabel);
  const comparison = compare ? ` Compared against ${compare.label}.` : "";
  setText(
    "#geography-data-detail",
    `${layer?.note || "Select a registered data layer to inspect its coverage."}${comparison} These layers are display/evaluation metadata only (runtime access off) and never enter agent prompts or retrieval.`
  );
  const registry = $("#dataset-source-registry");
  if (registry) {
    const sources = (dataCatalog().registered_sources || []).filter(
      (source) => source.kind === state.datasetKind && (!source.normalized || source.status !== "ready")
    );
    registry.innerHTML = sources.slice(0, 4).map((source) => {
      const years = source.year_start
        ? `${source.year_start}${source.year_end && source.year_end !== source.year_start ? `–${source.year_end}` : ""}`
        : "undated";
      const status = source.normalized
        ? source.status
        : source.status === "partial"
          ? "partial · not normalized"
          : source.status === "adapter_required"
            ? "adapter required"
            : "registered · not normalized";
      return `<li><span>${escapeHtml(years)} · ${escapeHtml(source.label)}</span><strong data-status="${escapeHtml(source.status || "registered")}">${escapeHtml(status)}</strong></li>`;
    }).join("");
  }
}

function renderGeographyInspector() {
  const data = state.population || {};
  const census = data.census || {};
  const selection = state.geographySelection || { level: "nation", id: "us:1" };
  const area = selection.stateFips ? stateByFips(selection.stateFips) : null;
  const profile = selectedGeographyProfile();
  const levelLabels = {
    nation: "Nation",
    state: "State aggregate",
    district: "Congressional district",
    congressional_district: "U.S. House district",
    state_legislative_upper: "State senate district",
    state_legislative_lower: "State house / assembly district",
    county: "County",
    county_subdivision: "County subdivision",
    tract: "Census tract",
    voting_district: "Voting district",
    custom: "Built test area",
  };
  const label = selection.label || (area && area.name) || "United States";
  setText("#geography-level", levelLabels[selection.level] || "Built area");
  setText("#geography-name", label);
  const profileState = $("#geography-profile-state");
  const substate = !["nation", "state"].includes(selection.level);
  const stateSourcesReady = selection.level === "state" && area && area.ready;
  profileState.dataset.status = profile && profile.runnable ? "runnable" : stateSourcesReady ? "sources" : "waiting";
  profileState.textContent = profile && profile.runnable
    ? "Validated · runnable"
    : stateSourcesReady
      ? "Sources ready · build needed"
      : ["district", "congressional_district"].includes(selection.level)
        ? "District profile not built"
        : "Profile not built";
  const summary = profile
    ? profile.disclosure
    : substate
      ? "This boundary is selectable, but a validated synthetic population profile has not been built for it. Comparison-layer coverage does not make the area swarm-ready."
      : selection.level === "state"
        ? "The state source pack and the runnable synthetic population are tracked separately. Open a built profile when one becomes available."
        : "Select a state or D.C. to open its district layer, or choose any validated build below to inspect its demographic distribution.";
  setText("#geography-summary", summary);

  const facts = selection.level === "nation" && profile
    ? [
        ["Represents", `${Number(profile.target_population || 0).toLocaleString()} synthetic people`],
        ["Compressed cells", Number(profile.representative_cells || 0).toLocaleString()],
        ["State builds", `${Number((data.builds || {}).state_populations || 0)} validated`],
        ["Reasoning budget", `${Number(profile.reasoning_calls || 0)} calls`],
      ]
    : selection.level === "nation"
    ? [
        ["Coverage", `${census.states_plus_dc || 51} states + D.C.`],
        ["District layer", "2012 apportionment"],
        ["Source archives", `${census.artifact_count || 0}/${census.expected_artifact_count || 625}`],
        ["Runnable builds", populationProfiles().filter((item) => item.runnable).length],
      ]
    : profile
      ? [
          ["Represents", `${Number(profile.target_population || 0).toLocaleString()} synthetic people`],
          ["Compressed cells", Number(profile.representative_cells || 0).toLocaleString()],
          ["Reasoning budget", `${Number(profile.reasoning_calls || 0)} calls`],
          ["Vintage", profile.geography.vintage || "not recorded"],
        ]
      : (() => {
          const feature = selectedMapFeature();
          const layer = selectedDataLayer();
          const covered = area && layerCoversFeature(layer, area, selection.level, selection.id);
          const landSqMi = Number(feature?.properties?.land_m2 || 0) / 2_589_988.11;
          return [
            ["Boundary", feature ? "materialized" : "not materialized"],
            ["Land area", landSqMi ? `${Math.round(landSqMi).toLocaleString()} sq mi` : "—"],
            ["Comparison layer", covered ? "coverage found" : "no matching row"],
            ["Runnable profile", "not built"],
          ];
        })();
  $("#geography-facts").innerHTML = facts
    .map(([term, value]) => `<div><dt>${escapeHtml(term)}</dt><dd>${escapeHtml(value)}</dd></div>`)
    .join("");
  $("#demographic-empty").hidden = Boolean(profile && profile.runnable);
  $("#demographic-groups").innerHTML = demographicBars(profile);

  const profileSelect = $("#population-profile-select");
  const runnable = populationProfiles().filter((item) => item.runnable);
  profileSelect.innerHTML = runnable.length
    ? `<option value="">Choose a validated build…</option>` + runnable
        .map((item) => `<option value="${escapeHtml(item.population_id)}">${escapeHtml(item.label)} · ${Number(item.target_population || 0).toLocaleString()} represented</option>`)
        .join("")
    : `<option value="">No validated builds available</option>`;
  if (profile && profile.runnable) profileSelect.value = profile.population_id;
  renderDatasetReadout(area);
  renderPopulationCostEnvelope(profile);
  setText(
    "#population-swarm-note",
    profile && profile.runnable
      ? `Ready to sample ${profile.label} by population weight. Unspecified politics, urbanicity, and media habits remain unspecified.`
      : "Choose a validated build. Demographics shape explicit simulation roles; unspecified politics or media habits are never inferred."
  );
}

function renderSubareas(area, payload = state.geographyPayload) {
  const container = $("#population-subareas");
  if (!area || !payload) {
    container.hidden = true;
    container.innerHTML = "";
    return;
  }
  const stateProfile = profileForState(area);
  const features = payload.feature_collection?.features || [];
  const featureButtons = features.map((feature) => {
    const properties = feature.properties || {};
    const featureId = feature.id || properties.id;
    const profile = profileForGeographyId(featureId);
    const selected = canonicalGeographyId(state.geographySelection?.id) === canonicalGeographyId(featureId);
    return `<button type="button" class="district-tile" data-geo-feature="${escapeHtml(featureId)}" aria-pressed="${selected}">
      <span>${escapeHtml(payload.layer?.short_label || "Area")}</span><strong>${escapeHtml(properties.abbreviation || properties.code || "—")}</strong><small>${profile?.runnable ? "validated profile" : "profile not built"}</small>
    </button>`;
  }).join("");
  const unavailable = payload.available
    ? ""
    : `<div class="subarea-empty"><strong>Layer unavailable</strong><span>No ${escapeHtml(payload.layer?.label || "selected")} geometry is materialized for ${escapeHtml(area.name)}.</span></div>`;
  container.innerHTML = `<button type="button" class="state-aggregate" data-geo-state-aggregate="${escapeHtml(area.fips)}" data-status="${stateProfile && stateProfile.runnable ? "profile" : "planned"}">
      <span>State aggregate</span><strong>${escapeHtml(area.name)}</strong><small>${stateProfile && stateProfile.runnable ? "validated profile" : "population build needed"}</small>
    </button>
    ${unavailable}<div class="district-field">${featureButtons}</div>`;
  container.hidden = state.geographyView !== "boxes";
}

function normalizedDensityValues(features) {
  const values = features.map((feature) => {
    const area = stateByFips(feature.properties?.state_fips);
    const profile = profileForState(area);
    const landSqMi = Number(feature.properties?.land_m2 || 0) / 2_589_988.11;
    const density = profile?.runnable && landSqMi > 0
      ? Number(profile.target_population || 0) / landSqMi
      : 0;
    return density;
  });
  const logged = values.filter(Boolean).map((value) => Math.log1p(value));
  const min = logged.length ? Math.min(...logged) : 0;
  const max = logged.length ? Math.max(...logged) : 1;
  return values.map((value) => value ? 0.16 + ((Math.log1p(value) - min) / Math.max(0.001, max - min)) * 0.84 : 0);
}

function mapFeatureStyles(payload) {
  const features = payload.feature_collection?.features || [];
  const primary = selectedDataLayer();
  const densities = payload.layer?.id === "states" ? normalizedDensityValues(features) : [];
  return Object.fromEntries(features.map((feature, index) => {
    const properties = feature.properties || {};
    const featureId = feature.id || properties.id;
    const area = stateByFips(properties.state_fips);
    const profile = payload.layer?.id === "states"
      ? profileForState(area)
      : profileForGeographyId(featureId);
    const covered = layerCoversFeature(primary, area, payload.layer?.geography_level, featureId);
    const sourceReady = payload.layer?.id === "states" && area?.ready;
    const status = profile?.runnable ? "active" : covered ? "coverage" : sourceReady ? "source" : "missing";
    const density = densities[index] || 0;
    const value = state.mapShadeMode === "coverage"
      ? (covered ? 0.68 : profile?.runnable ? 0.48 : 0.04)
      : density || (profile?.runnable ? 0.34 : covered ? 0.18 : 0.03);
    const landSqMi = Number(properties.land_m2 || 0) / 2_589_988.11;
    const detail = profile?.runnable && density
      ? `${Number(profile.target_population || 0).toLocaleString()} represented · ${Math.round(Number(profile.target_population || 0) / Math.max(1, landSqMi)).toLocaleString()} per sq mi`
      : profile?.runnable
        ? "validated population profile"
        : covered
          ? "comparison coverage; population profile not built"
          : sourceReady
            ? "source pack ready; population profile not built"
            : "boundary only; population profile not built";
    return [featureId, { status, value, detail }];
  }));
}

function handleMapFeatureSelect(feature) {
  const payload = state.geographyPayload;
  if (!payload) return;
  const properties = feature.properties || {};
  const featureId = feature.id || properties.id;
  if (payload.layer?.id === "states") {
    const area = stateByFips(properties.state_fips);
    if (!area) return;
    const profile = profileForState(area);
    chooseGeography({
      level: "state",
      id: `state:${area.fips}`,
      label: area.name,
      stateFips: area.fips,
      populationId: profile?.population_id || null,
    });
    return;
  }
  const area = stateByFips(properties.state_fips);
  const profile = profileForGeographyId(featureId);
  chooseGeography({
    level: payload.layer?.geography_level || "area",
    id: featureId,
    label: `${area?.name || "Area"} · ${properties.label || properties.abbreviation || properties.code || "selection"}`,
    stateFips: properties.state_fips,
    populationId: profile?.population_id || null,
  });
}

function renderMapGeometry(payload = state.geographyPayload) {
  const map = $("#population-map");
  if (!map || !payload) return;
  const loading = $("#map-loading");
  const empty = $("#map-empty");
  if (loading) loading.hidden = true;
  if (empty) empty.hidden = Boolean(payload.available);
  setText("#map-feature-count", payload.available ? `${Number(payload.feature_count || 0).toLocaleString()} SELECTABLE CELLS` : "NO CELLS MATERIALIZED");
  setText("#map-source-label", `${payload.source_agency || "Official boundary source"} · ${payload.boundary_vintage || "vintage not recorded"}`);
  map.hidden = state.geographyView !== "map";
  if (state.geographyView !== "map" || !window.PolisimGeoMap) return;
  window.PolisimGeoMap.mount(map, {
    onError: () => {
      if (empty) {
        empty.hidden = false;
        empty.querySelector("strong").textContent = "WEBGL MAP UNAVAILABLE";
        empty.querySelector("span").textContent = "Use the Index view to select the same official geography boundaries.";
      }
    },
  });
  window.PolisimGeoMap.render(payload.feature_collection, {
    scope: payload.layer?.scope || "state",
    featureStyles: mapFeatureStyles(payload),
    selectedId: state.geographySelection?.id,
    onSelect: handleMapFeatureSelect,
  });
}

async function loadGeographyWorld() {
  const selection = state.geographySelection || { level: "nation" };
  const area = selection.stateFips ? stateByFips(selection.stateFips) : null;
  const layerId = area ? (state.geographyLayer === "states" ? "congressional" : state.geographyLayer) : "states";
  const cacheKey = `${state.selectedEra || "e2012"}:${layerId}:${area?.fips || "us"}`;
  const token = ++state.geographyRequestToken;
  const loading = $("#map-loading");
  const empty = $("#map-empty");
  if (loading) loading.hidden = false;
  if (empty) empty.hidden = true;
  try {
    if (!state.geographyCatalog) {
      state.geographyCatalog = await getJSON(withEra("/api/geography/catalog"));
    }
    let payload = GEOGRAPHY_CACHE.get(cacheKey);
    if (!payload) {
      const params = new URLSearchParams({ layer: layerId });
      if (area) params.set("state", area.fips);
      payload = await getJSON(withEra(`/api/geography?${params}`));
      GEOGRAPHY_CACHE.set(cacheKey, payload);
    }
    if (token !== state.geographyRequestToken) return;
    state.geographyPayload = payload;
    renderSubareas(area, payload);
    renderMapGeometry(payload);
    renderGeographyInspector();
  } catch (error) {
    if (token !== state.geographyRequestToken) return;
    if (loading) loading.hidden = true;
    if (empty) {
      empty.hidden = false;
      empty.querySelector("strong").textContent = "GEOGRAPHY LOAD FAILED";
      empty.querySelector("span").textContent = String(error);
    }
    setText("#map-feature-count", "GEOMETRY ERROR");
  }
}

function renderGeographyExplorer(data) {
  if (!data) return;
  const states = (data.census && data.census.states) || [];
  const selection = state.geographySelection || { level: "nation", id: "us:1" };
  const area = selection.stateFips ? stateByFips(selection.stateFips) : null;
  renderDataControls();
  $("#population-boxes").innerHTML = `<button type="button" class="box-tile nation-box" data-geo-home><strong>US</strong><span>United States</span><small>${states.length} states + D.C.</small></button>`
    + states.map((row) => geographyButton(row, "boxes")).join("");
  $("#population-map").hidden = state.geographyView !== "map";
  $("#population-boxes").hidden = Boolean(area) || state.geographyView !== "boxes";
  renderSubareas(area);
  setText(
    "#geography-path-current",
    !["nation", "state"].includes(selection.level)
      ? selection.label
      : area
        ? area.name
        : selection.populationId
          ? selection.label
          : "All states + D.C."
  );
  setText(
    "#map-zoom-label",
    area
      ? `L02 · ${state.geographyLayer.replaceAll("_", " ").toUpperCase()}`
      : selection.populationId
        ? `PROFILE · ${selection.level.toUpperCase()}`
        : "L01 · STATE"
  );
  $("#geography-home").setAttribute(
    "aria-current",
    selection.level === "nation" ? "location" : "false"
  );
  document.querySelectorAll("[data-geography-view]").forEach((button) => {
    button.setAttribute("aria-pressed", String(button.dataset.geographyView === state.geographyView));
  });
  renderGeographyInspector();
  loadGeographyWorld();
}

function renderPopulationLens() {
  const lens = $("#swarm-population-lens");
  if (!lens) return;
  const selection = state.populationSelection;
  lens.hidden = !selection;
  if (!selection) return;
  setText("#swarm-population-title", selection.label);
  setText(
    "#swarm-population-detail",
    `${selection.n_agents} deterministic population-weighted personas · ${selectedDataLayer()?.label || "no comparison layer"} recorded for evaluation only · political behavior not inferred`
  );
}

function configurePopulationSwarm(ev) {
  ev.preventDefault();
  const profile = selectedGeographyProfile();
  if (!profile || !profile.runnable) return;
  const nAgents = Number($("#population-agent-count").value || 12);
  state.populationSelection = {
    population_id: profile.population_id,
    geography_id: profile.geography.id,
    label: profile.label,
    strategy: "population_weighted",
    n_agents: nAgents,
  };
  applySwarmPreset(`balanced-${nAgents}`);
  $("#swarm-preset").value = `balanced-${nAgents}`;
  $("#swarm-label").value = `${profile.label} · weighted ${nAgents}`;
  renderPopulationLens();
  setView("runs");
  $("#swarm-builder").scrollIntoView({ behavior: "smooth", block: "start" });
}

function renderPopulation(data) {
  state.population = data;
  const census = data.census || {};
  const builds = data.builds || {};
  const convergence = data.convergence || {};
  const behavior = data.behavior_validation || {};
  const fixture = builds.fixture || {};
  const profileContract = data.profile_contract || {};
  const inputsComplete = census.status === "verified";
  const populationsComplete =
    Number(builds.state_populations || 0) === Number(builds.expected_state_populations || 51)
    && Boolean(builds.national_population && builds.national_population.runnable);
  const complete = inputsComplete && populationsComplete;
  const verdict = $("#population-verdict");
  verdict.dataset.status = complete ? "verified" : census.status || "incomplete";
  verdict.setAttribute("aria-busy", "false");
  setText(
    "#population-intro",
    `Track B uses material released by ${data.cutoff_date}. This view distinguishes acquired inputs from populations and behavioral evidence.`
  );
  setText(
    "#population-headline",
    complete
      ? "All 51 state and D.C. populations plus the national aggregate are validated."
      : profileContract.status === "practice_fixture_ready"
        ? "One offline fixture profile is validated; nationwide profiles are not built."
        : profileContract.status === "no_validated_profiles"
          ? "No validated population profile is built in this workspace."
      : census.status === "not_downloaded"
        ? "The Census input pack has not been downloaded in this workspace."
        : "The Census input pack is incomplete and needs verification."
  );
  setText(
    "#population-detail",
    complete
      ? `${census.artifact_count} source archives and ${builds.validated_profiles} weighted builds are checksum-bound. ${convergence.passed ? `${convergence.conditions} convergence budgets were tested offline.` : "Convergence is pending."} ${behavior.passed ? "One mechanically sealed neutral-baseline behavior calibration is available; it is not analyst-blind validation." : "Held-out behavior validation is still pending."}`
      : profileContract.status === "practice_fixture_ready"
        ? "The runnable fixture is synthetic practice data for its declared fictional geography. Run the Census pipeline before making state or national coverage claims."
        : profileContract.status === "no_validated_profiles"
          ? `Build the provider-free fixture with ${profileContract.build_command || "psbx practice prepare --epoch e2012"}. State-scale profiles remain a separate Census workflow.`
          : "Run the population Census sync and verifier before building state-scale populations."
  );
  setText(
    "#population-stamp",
    complete
      ? "POPULATIONS VALIDATED"
      : profileContract.status === "practice_fixture_ready"
        ? "FIXTURE ONLY"
        : inputsComplete
          ? "BUILD INCOMPLETE"
          : "PROFILE NEEDED"
  );

  $("#population-pipeline").innerHTML = (data.pipeline || [])
    .map(
      (step) => `<li data-status="${escapeHtml(step.status)}">
        <span class="pipeline-marker" aria-hidden="true"></span>
        <strong>${escapeHtml(step.label)}</strong>
        <small>${escapeHtml(step.detail)}</small>
      </li>`
    )
    .join("");

  setText("#population-state-total", `${census.states_ready || 0} / ${census.states_plus_dc || 51} ready`);
  setText(
    "#population-national",
    builds.national_population && builds.national_population.runnable
      ? "Validated"
      : census.national_aggregate
        ? "Inputs only"
        : "Missing"
  );
  setText("#population-artifacts", `${census.artifact_count || 0} / ${census.expected_artifact_count || 625}`);
  setText("#population-size", formatBytes(census.total_bytes));
  setText("#population-coverage-count", `${census.states_ready || 0} of ${census.states_plus_dc || 51} complete`);

  $("#population-states").innerHTML = (census.states || [])
    .map(
      (area) => `<li data-ready="${Boolean(area.ready)}" title="${escapeHtml(area.name)}: ${area.artifacts}/${area.expected_artifacts} archives">
        <strong>${escapeHtml(area.abbreviation)}</strong>
        <span>${area.artifacts}/${area.expected_artifacts}</span>
      </li>`
    )
    .join("");
  const national = $("#population-national-row");
  national.dataset.ready = String(Boolean(census.national_aggregate));
  national.querySelector("span").textContent = census.national_aggregate
    ? "National demographic profile and selected ACS summary sequences are included; national PUMS is derived from the 51 state/D.C. archives."
    : "The national summary layer is not present in this workspace.";

  $("#population-families").innerHTML = (census.families || [])
    .map(
      (family) => `<tr><td>${escapeHtml(family.label)}</td><td class="num">${family.artifacts}</td></tr>`
    )
    .join("");
  $("#population-tables").innerHTML = (census.tables || [])
    .map(
      (table) => `<li><code>${escapeHtml(table.code)}</code><span>${escapeHtml(table.label)}</span></li>`
    )
    .join("");

  setText("#fixture-status", fixture.validated ? "Validation passed" : "Not validated");
  setText("#fixture-people", fixture.target_population == null ? "—" : `${fixture.target_population} exact`);
  setText("#fixture-cells", fixture.representative_cells == null ? "—" : fixture.representative_cells);
  setText("#fixture-calls", fixture.reasoning_calls == null ? "—" : `${fixture.reasoning_calls} calls`);
  setText("#fixture-tvd", fixture.max_total_variation == null ? "—" : fmt(fixture.max_total_variation, 3));
  $("#population-claims").innerHTML = (data.claims || [])
    .map((claim) => `<li>${escapeHtml(claim)}</li>`)
    .join("");
  renderGeographyExplorer(data);
}

async function loadPopulation() {
  const verdict = $("#population-verdict");
  if (verdict) verdict.setAttribute("aria-busy", "true");
  try {
    renderPopulation(await getJSON(withEra("/api/population")));
  } catch (err) {
    if (verdict) {
      verdict.dataset.status = "error";
      verdict.setAttribute("aria-busy", "false");
    }
    setText("#population-headline", "Population status could not be loaded.");
    setText("#population-detail", `Refresh the page or inspect the viewer API: ${String(err)}`);
    setText("#population-stamp", "LOAD ERROR");
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
  const classes = Object.entries(data.authenticity_counts || {})
    .map(([key, value]) => `${key} ${value}`)
    .join(" · ") || "none";
  $("#corpus-assertion").textContent = `Only documents dated on or before ${data.cutoff_date}. Evidence classes: ${classes}. Research eligible: ${data.research_eligible_documents || 0}. Leaked rows: ${data.n_leaked}.`;
  $("#search-status").textContent = `${data.n_documents} documents in the index`;
  if (!$("#search-table tbody").children.length) {
    $("#search-table tbody").innerHTML = data.documents
      .slice(0, 12)
      .map(
        (d) => `<tr>
          <td><button class="linkish" data-fetch="${escapeHtml(d.document_id)}">${escapeHtml(d.document_id.slice(0, 12))}</button></td>
          <td>${escapeHtml(d.title)}</td>
          <td>${escapeHtml(d.outlet)}</td>
          <td class="num">${escapeHtml(d.published_at.slice(0, 10))}</td>
          <td>${escapeHtml(d.authenticity || "unverified")}</td>
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
  const res = await fetch(`/api/eras/${encodeURIComponent(state.selectedEra)}/search`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    $("#search-status").textContent = `Search failed ${res.status}`;
    return;
  }
  const hits = await res.json();
  $("#search-status").textContent = `${hits.length} hits · all on or before cutoff`;
  $("#search-table tbody").innerHTML = hits
    .map(
      (h) => `<tr>
        <td><button class="linkish" data-fetch="${escapeHtml(h.document_id)}">${escapeHtml(h.document_id.slice(0, 12))}</button></td>
        <td>${escapeHtml(h.title)}</td>
        <td>${escapeHtml(h.outlet)}</td>
        <td class="num">${escapeHtml(String(h.published_at).slice(0, 10))}</td>
        <td>${escapeHtml(h.authenticity || "unverified")}</td>
        <td class="num">${fmt(h.prominence, 2)}</td>
        <td class="q-text">${escapeHtml(h.snippet || "")}</td>
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
    ["Evidence class", doc.authenticity || "unverified"],
    ["Research eligible", doc.authenticity && doc.authenticity.startsWith("authenticated_") ? "yes" : "no"],
    ["Content SHA-256", doc.content_sha256 || "not recorded"],
    ["Source reference", doc.source_reference || "not independently established"],
    ["Prominence", fmt(doc.prominence, 3)],
    ["URL", doc.url],
  ]
    .map(([k, v]) => `<div><dt>${escapeHtml(k)}</dt><dd>${escapeHtml(v)}</dd></div>`)
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

const ARENA_ASSETS = {
  openai: "/static/agents/openai.png",
  anthropic: "/static/agents/anthropic.png",
  google: "/static/agents/google.png",
  meta: "/static/agents/meta.png",
  qwen: "/static/agents/qwen.png",
  local: "/static/agents/local.png",
};

function arenaCorporationForModel(modelId = "") {
  const id = String(modelId).toLowerCase();
  if (id.includes("anthropic") || id.includes("claude") || id === "frontier-a") return "anthropic";
  if (id.includes("google") || id.includes("gemini")) return "google";
  if (id.includes("meta") || id.includes("llama")) return "meta";
  if (id.includes("qwen") || id.includes("alibaba")) return "qwen";
  if (id.includes("openai") || id === "frontier-b") return "openai";
  return "local";
}

function arenaAvatar(row, className = "arena-avatar") {
  if (row.asset === "swarm") {
    const assets = [...new Set((row.composition || []).map((item) => arenaCorporationForModel(item.model_id)))].slice(0, 3);
    const selected = assets.length ? assets : ["local"];
    return `<span class="${className} arena-avatar-stack" aria-label="Multi-model swarm">${selected
      .map((asset) => `<img src="${ARENA_ASSETS[asset]}" alt="" loading="lazy">`)
      .join("")}</span>`;
  }
  const asset = ARENA_ASSETS[row.asset] || ARENA_ASSETS.local;
  const alt = `${row.corporation || row.label || "Synthetic"} bot portrait`;
  return `<span class="${className}"><img src="${asset}" alt="${escapeHtml(alt)}" loading="lazy"></span>`;
}

function renderArenaPodium(data) {
  const stage = $("#arena-podium-stage");
  if (!stage) return;
  const top = (data.agents || []).slice(0, 3);
  if (!top.length) {
    stage.innerHTML = `<p class="arena-empty">No scored individual swarm ballots yet. Finish a swarm run to open the podium.</p>`;
    return;
  }
  const displayOrder = top.length === 3 ? [top[1], top[0], top[2]] : top;
  stage.innerHTML = displayOrder.map((row) => {
    const place = Number(row.rank || top.indexOf(row) + 1);
    return `<article class="podium-agent" data-place="${place}">
      ${arenaAvatar(row, "podium-portrait")}
      <div class="podium-plate">
        <span class="podium-place">#${place}</span>
        <div><strong>${escapeHtml(row.label)}</strong><small>${escapeHtml(row.model)} · ${row.n_forecasts} forecast${row.n_forecasts === 1 ? "" : "s"}</small></div>
        <b>${fmt(row.arena_score, 1)}</b>
      </div>
    </article>`;
  }).join("");
}

function arenaRows() {
  const data = state.leaderboard || {};
  let rows = [...(data[state.leaderboardMode] || [])];
  if (state.leaderboardCorporation && ["agents", "models"].includes(state.leaderboardMode)) {
    rows = rows.filter((row) => row.corporation_id === state.leaderboardCorporation);
  }
  const metric = state.leaderboardMetric;
  rows.sort((a, b) => {
    if (metric === "accuracy") {
      const av = state.leaderboardMode === "swarms" ? Number(a.c_index ?? -1) : Number(a.accuracy ?? -1);
      const bv = state.leaderboardMode === "swarms" ? Number(b.c_index ?? -1) : Number(b.accuracy ?? -1);
      return bv - av || Number(a.brier ?? 9) - Number(b.brier ?? 9);
    }
    if (metric === "volume") {
      const av = Number(state.leaderboardMode === "swarms" ? a.n_votes : a.n_forecasts);
      const bv = Number(state.leaderboardMode === "swarms" ? b.n_votes : b.n_forecasts);
      return bv - av || Number(a.brier ?? 9) - Number(b.brier ?? 9);
    }
    return Number(a.brier ?? 9) - Number(b.brier ?? 9) || Number(b.n_forecasts ?? b.n_votes ?? 0) - Number(a.n_forecasts ?? a.n_votes ?? 0);
  });
  return rows;
}

function arenaRecord(row, mode) {
  if (mode === "agents") return `${row.wins} run win${row.wins === 1 ? "" : "s"} · ${row.n_forecasts} forecasts`;
  if (mode === "models") return `${row.n_runs} run${row.n_runs === 1 ? "" : "s"} · ${row.n_agents ? `${row.n_agents} swarm agent${row.n_agents === 1 ? "" : "s"}` : "direct forecasts"}`;
  if (mode === "corporations") return `${row.n_models} models · ${row.n_forecasts} forecasts`;
  return `${row.n_agents} agents · ${row.n_questions} question${row.n_questions === 1 ? "" : "s"}`;
}

function arenaIdentity(row, mode) {
  if (mode === "agents") return `${escapeHtml(row.perspective)} · simulation role`;
  if (mode === "models") return `${escapeHtml(row.corporation)} · ${escapeHtml(row.model_type)}`;
  if (mode === "corporations") return `${row.n_models} ranked model${row.n_models === 1 ? "" : "s"} · ${row.n_agents} swarm agent${row.n_agents === 1 ? "" : "s"}`;
  const date = row.created_at ? new Date(row.created_at).toLocaleDateString() : "date unavailable";
  return `${escapeHtml(date)} · ${escapeHtml(row.source_type)} evidence`;
}

function renderArenaRankings() {
  const data = state.leaderboard;
  if (!data) return;
  const mode = state.leaderboardMode;
  const rows = arenaRows();
  const copy = {
    agents: "Individual synthetic agents, scored directly from their saved swarm ballots.",
    swarms: "Complete scored swarms, with direct access to each archived result and execution log.",
    models: "Model families aggregated across individual votes and ordinary saved forecasts.",
    corporations: "Corporations aggregated from the same underlying scored model forecasts.",
  };
  setText("#arena-board-copy", copy[mode]);
  const thirdHeader = $(".arena-table-head [role='columnheader']:nth-child(4)");
  if (thirdHeader) thirdHeader.textContent = mode === "swarms" ? "C-index" : "Hit rate";
  document.querySelectorAll("[data-arena-mode]").forEach((button) => {
    button.setAttribute("aria-pressed", button.dataset.arenaMode === mode ? "true" : "false");
  });
  const corporation = $("#arena-corporation");
  if (corporation) corporation.disabled = !["agents", "models"].includes(mode);
  const target = $("#arena-rankings");
  if (!rows.length) {
    target.innerHTML = `<p class="arena-empty">No scored competitors match this view yet.</p>`;
    return;
  }
  target.innerHTML = rows.map((row, index) => {
    const rank = index + 1;
    const brier = row.brier == null ? "—" : fmt(row.brier);
    const accuracy = mode === "swarms"
      ? (row.c_index == null ? "—" : fmt(row.c_index))
      : (row.accuracy == null ? "—" : pct(row.accuracy));
    const action = mode === "swarms"
      ? `<span class="arena-row-actions"><button type="button" class="linkish" data-run-results="${escapeHtml(row.id)}" ${row.has_predictions ? "" : "disabled"}>Result</button><button type="button" class="linkish" data-run-log="${escapeHtml(row.id)}" ${row.has_log ? "" : "disabled"}>Log</button></span>`
      : "";
    const tag = mode === "swarms" && row.beats_prior ? `<span class="arena-win-tag">Beat prior</span>` : "";
    return `<article class="arena-row" role="row" data-top="${rank <= 3}">
      <div class="arena-competitor" role="cell">
        <span class="arena-rank">${String(rank).padStart(2, "0")}</span>
        ${arenaAvatar(row)}
        <div><strong>${escapeHtml(row.label)}</strong><small>${arenaIdentity(row, mode)}</small>${tag}</div>
      </div>
      <div class="arena-score" role="cell"><strong>${fmt(row.arena_score, 1)}</strong><span class="arena-score-track"><i style="--arena-w:${Math.max(0, Math.min(100, Number(row.arena_score || 0)))}"></i></span></div>
      <div class="arena-stat" role="cell"><strong>${brier}</strong><small>lower better</small></div>
      <div class="arena-stat" role="cell"><strong>${accuracy}</strong><small>${mode === "swarms" ? "ranking" : "correct side"}</small></div>
      <div class="arena-record" role="cell"><span>${arenaRecord(row, mode)}</span>${action}</div>
    </article>`;
  }).join("");
}

function renderArenaMatchLog(data) {
  const rows = [...(data.swarms || [])].sort((a, b) => String(b.created_at || "").localeCompare(String(a.created_at || ""))).slice(0, 6);
  setText("#arena-log-count", `${rows.length} recent`);
  const list = $("#arena-match-list");
  list.innerHTML = rows.length ? rows.map((row) => {
    const date = row.created_at ? new Date(row.created_at).toLocaleDateString() : "Archived";
    return `<li>
      <div><span>${escapeHtml(date)}</span><b>${fmt(row.arena_score, 1)} score</b></div>
      <strong>${escapeHtml(row.label)}</strong>
      <small>${row.n_agents} agents · Brier ${fmt(row.brier)}${row.champion_agent ? ` · top ${escapeHtml(row.champion_agent)}` : ""}</small>
      <div class="arena-log-actions"><button type="button" class="linkish" data-run-results="${escapeHtml(row.id)}">Open result</button><button type="button" class="linkish" data-run-log="${escapeHtml(row.id)}" ${row.has_log ? "" : "disabled"}>Open log</button></div>
    </li>`;
  }).join("") : `<li class="arena-empty">No scored swarm results are archived yet.</li>`;
}

function renderLeaderboard(data = state.leaderboard) {
  if (!data) return;
  const summary = data.summary || {};
  const updated = data.updated_at ? new Date(data.updated_at).toLocaleString() : "No scored archive yet";
  setText("#arena-season-status", data.status === "measured" ? `${state.selectedEra} arena online` : "Arena awaiting results");
  setText("#arena-season-meta", `Archive updated ${updated}`);
  setText("#arena-ballots", summary.n_scored_ballots || 0);
  setText("#arena-agents", summary.n_agents || 0);
  setText("#arena-swarms", summary.n_swarms || 0);
  setText("#arena-models", summary.n_models || 0);
  renderArenaPodium(data);
  const corporations = data.corporations || [];
  const corporation = $("#arena-corporation");
  const previous = state.leaderboardCorporation;
  corporation.innerHTML = `<option value="">All corporations</option>` + corporations
    .map((row) => `<option value="${escapeHtml(row.id)}">${escapeHtml(row.label)}</option>`)
    .join("");
  if ([...corporation.options].some((option) => option.value === previous)) corporation.value = previous;
  renderArenaRankings();
  renderArenaMatchLog(data);
}

async function loadLeaderboard() {
  if (state.leaderboard) {
    renderLeaderboard();
    return;
  }
  const target = $("#arena-rankings");
  if (target) target.innerHTML = `<p class="arena-empty">Calculating saved standings…</p>`;
  try {
    state.leaderboard = await getJSON(withEra("/api/leaderboard"));
    renderLeaderboard();
  } catch (error) {
    if (target) target.innerHTML = `<p class="arena-empty">The saved standings could not be loaded. ${escapeHtml(String(error))}</p>`;
    setText("#arena-season-status", "Arena unavailable");
  }
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
  setText("#prior-rung-lead", ex.comparison_scope || "Scores disclose their question coverage and comparison scope.");
  $("#scoreboard").innerHTML = board.length
    ? board
        .map((row) => {
          const win = row.kind === "model" && row.beats_prior;
          const lose = row.kind === "model" && !row.beats_prior && row.delta_vs_prior != null;
          const coverage = row.coverage || {};
          const coverageNote = row.kind === "model"
            ? `Answered ${coverage.answered_questions || 0}/${coverage.expected_questions || 0} · ${row.display_scope}`
            : row.display_scope;
          return `<div class="board-row" data-kind="${row.kind}" data-reference="${row.reference}" data-win="${win}" data-lose="${lose}">
            <div class="board-name">${row.label}<small>${row.note || row.id}</small><small>${coverageNote}</small><span class="board-tag">${tagFor(row)}</span></div>
            ${boardCell("brier", row.bar, row.display_brier == null ? "—" : fmt(row.display_brier), "brier-fill")}
            ${boardCell("c", row.c_bar, row.display_c_index == null ? "—" : fmt(row.display_c_index), "c-fill")}
          </div>`;
        })
        .join("")
    : `<p class="note">Scores appear once a run has been graded.</p>`;

  const facts = [
    ["This run", ex.run_label || data.run_id || "—"],
    ["Answers scored", ex.n_predictions || 0],
    ["Benchmark questions", ex.question_count || 0],
    ["Matched questions", ex.matched_question_count || 0],
    ["Citation verification failures", ex.n_citation_verification_failed || 0],
    ["Contamination-review flags", ex.n_flagged || 0],
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
  const chainRunId = state.activity && state.activity.run ? state.activity.run.run_id : null;
  if (state.selectedRun && chainRunId !== state.selectedRun) await loadActivity(true);
  else if (state.activity) renderAgentChains(state.activity);
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
      if (!b.n || b.mean_accuracy == null || Number.isNaN(b.mean_accuracy)) return;
      ptsAll.push({ x: (b.gap_lo_days + b.gap_hi_days) / 2, y: b.mean_accuracy });
    });
  });
  if (!ptsAll.length) return `<p class="note">No usable declared-cutoff gap buckets for this epoch.</p>`;
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
      .filter((b) => b.n && b.mean_accuracy != null && !Number.isNaN(b.mean_accuracy))
      .map((b) => `${xmap((b.gap_lo_days + b.gap_hi_days) / 2)},${ymap(b.mean_accuracy)}`)
      .join(" ");
    paths += `<polyline fill="none" stroke="${color}" points="${pts}"/>`;
  });
  return `<svg viewBox="0 0 ${w} ${h}" role="img" aria-label="Descriptive accuracy by days from declared training cutoff metadata">
    ${paths}
    <text x="${p}" y="${h - 10}">Gap (days)</text>
    <text x="8" y="${p}">Accuracy</text>
  </svg>`;
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
  const practiceOk = Boolean(state.ready && state.ready.practice_ready && eraRunnable);
  mockBtn.disabled = busy || !practiceOk;
  mockBtn.textContent = busy && kind === "mock" ? "Running…" : "Run practice";
  liveBtn.disabled = busy || !liveOk || !practiceOk;
  liveBtn.textContent = busy && kind === "live" ? "Running…" : "Run live mix";
  mockBtn.title = !eraRunnable
    ? `No practice run config targets ${state.selectedEra || "this era"} yet`
    : practiceOk
      ? "Run the configured practice experiment for this era"
      : state.ready.practice_blocking_reason || "Practice prerequisites are incomplete";
  liveBtn.title = !eraRunnable
    ? `No live run config targets ${state.selectedEra || "this era"} yet`
    : liveOk
    ? "Score each of the six OpenRouter species once on 1 question (not the 12-agent swarm)"
    : state.ready.live_blocking_reason || "Live research prerequisites are incomplete";
  if (swarmBtn) {
    swarmBtn.disabled = busy || !liveOk || !practiceOk;
    swarmBtn.textContent = busy && kind === "swarm" ? "Running…" : "Run configured swarm";
    swarmBtn.title = !eraRunnable
      ? `No swarm run config targets ${state.selectedEra || "this era"} yet`
      : liveOk
      ? "Launch the roster and question count configured in the Runs tab"
      : state.ready.live_blocking_reason || "Live research prerequisites are incomplete";
  }
  if (launchBtn) {
    const estimate = updateSwarmEstimate();
    launchBtn.disabled = busy || !liveOk || !practiceOk || estimate.invalid;
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
  state.leaderboard = null;
  await loadOverview();
  await loadScores();
  await loadForecasts();
  if (location.hash === "#leaderboard") await loadLeaderboard();
}

async function startSimulation(kind) {
  const mockBtn = $("#run-btn");
  const liveBtn = $("#run-live-btn");
  const swarmBtn = $("#run-swarm-btn");
  if (!state.ready || !state.ready.practice_ready) {
    $("#run-log-band").hidden = false;
    $("#run-log").textContent = state.ready?.practice_blocking_reason
      || "Practice prerequisites are incomplete. Prepare the corpus and seal the sidecar first.";
    applyReady(state.ready);
    return;
  }
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
    swarm: state.populationSelection
      ? `Starting ${state.populationSelection.label} swarm (${custom ? custom.agents : 12} weighted personas × ${custom ? custom.questions : 1} questions)…`
      : `Starting swarm (${custom ? custom.agents : 12} sequential votes × ${custom ? custom.questions : 1} questions)…`,
  };
  if (kind === "mock") mockBtn.textContent = "Running…";
  else if (kind === "swarm" && swarmBtn) swarmBtn.textContent = "Running…";
  else liveBtn.textContent = "Running…";
  $("#run-log-band").hidden = false;
  $("#run-log").textContent = starting[kind] || "Starting…";
  const res = await fetch("/api/jobs/run", {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-PSBX-CSRF": "1" },
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
      population_selection: kind === "swarm" ? state.populationSelection : null,
      dataset_selection: kind === "swarm" ? currentDatasetSelection() : null,
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
    return;
  }
  const started = await res.json();
  state.selectedRun = started.run_id || state.selectedRun;
  state.activityQuestion = null;
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
  const practiceOk = Boolean(state.ready && state.ready.practice_ready && eraRunnable);
  if (state.ready && state.ready.swarm_options) {
    renderSwarmBuilder(state.ready.swarm_options);
  }
  if (state.lastJobStatus !== "running") {
    if (mockBtn) mockBtn.disabled = !practiceOk;
    if (liveBtn) liveBtn.disabled = !ok || !practiceOk;
    if (swarmBtn) swarmBtn.disabled = !ok || !practiceOk;
  }
  const prerequisite = $("#run-prerequisite");
  if (prerequisite) {
    prerequisite.dataset.status = practiceOk ? "ready" : "blocked";
    prerequisite.textContent = practiceOk
      ? `Ready: ${state.selectedEra}/${state.ready.requested_source_type || "all"} corpus and sealed sidecar verified.`
      : state.ready?.practice_blocking_reason
        || "Run prerequisites are unavailable; inspect Setup before launching.";
  }
  updateSwarmEstimate();
}

async function loadReady() {
  const params = new URLSearchParams();
  if (state.selectedEra) params.set("epoch", state.selectedEra);
  const scope = state.activity?.access?.selection;
  if (scope && scope !== "all" && scope !== "unknown") {
    params.set("source_type", scope);
  }
  state.ready = await getJSON(`/api/jobs/ready?${params}`);
  applyReady(state.ready);
  return state.ready;
}

function bind() {
  bindTablist();
  document.querySelectorAll("[data-chain-question]").forEach((select) => {
    select.addEventListener("change", () => {
      state.activityQuestion = select.value || null;
      loadActivity();
    });
  });
  $("#reveal-truth").addEventListener("change", loadQuestions);
  $("#q-category").addEventListener("change", loadQuestions);
  $("#search-form").addEventListener("submit", runSearch);
  $("#scope-form").addEventListener("submit", sealContainer);
  $("#population-swarm-form").addEventListener("submit", configurePopulationSwarm);
  $("#population-agent-count").addEventListener("change", () => {
    renderPopulationCostEnvelope(selectedGeographyProfile());
  });
  $("#population-profile-select").addEventListener("change", () => {
    const profile = profileById($("#population-profile-select").value);
    if (profile) chooseGeography(geographySelectionForProfile(profile));
  });
  $("#swarm-population-clear").addEventListener("click", () => {
    state.populationSelection = null;
    renderPopulationLens();
  });
  $("#result-chain-open-live").addEventListener("click", () => setView("activity"));
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
    state.activityQuestion = null;
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
  $("#arena-metric").addEventListener("change", () => {
    state.leaderboardMetric = $("#arena-metric").value;
    renderArenaRankings();
  });
  $("#arena-corporation").addEventListener("change", () => {
    state.leaderboardCorporation = $("#arena-corporation").value;
    renderArenaRankings();
  });
  $("#geography-layer").addEventListener("change", () => {
    state.geographyLayer = $("#geography-layer").value || "states";
    renderGeographyExplorer(state.population);
  });
  $("#dataset-kind").addEventListener("change", () => {
    state.datasetKind = $("#dataset-kind").value;
    state.datasetLayerId = (dataCatalog().layers || []).find(
      (layer) => layer.kind === state.datasetKind
    )?.id || null;
    state.datasetCompareLayerId = null;
    renderGeographyExplorer(state.population);
  });
  $("#dataset-layer").addEventListener("change", () => {
    state.datasetLayerId = $("#dataset-layer").value || null;
    renderGeographyExplorer(state.population);
  });
  $("#dataset-compare-layer").addEventListener("change", () => {
    state.datasetCompareLayerId = $("#dataset-compare-layer").value || null;
    renderGeographyExplorer(state.population);
  });
  $("#map-shade-mode").addEventListener("change", () => {
    state.mapShadeMode = $("#map-shade-mode").value === "coverage" ? "coverage" : "density";
    renderMapGeometry();
  });
  $("#map-zoom-in").addEventListener("click", () => window.PolisimGeoMap?.zoomIn());
  $("#map-zoom-out").addEventListener("click", () => window.PolisimGeoMap?.zoomOut());
  $("#map-reset-view").addEventListener("click", () => window.PolisimGeoMap?.resetCamera());
  document.body.addEventListener("click", async (ev) => {
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
    const arenaMode = ev.target.closest("[data-arena-mode]");
    if (arenaMode) {
      state.leaderboardMode = arenaMode.dataset.arenaMode;
      if (state.leaderboardMode === "corporations" || state.leaderboardMode === "swarms") {
        state.leaderboardCorporation = "";
        $("#arena-corporation").value = "";
      }
      renderArenaRankings();
    }
    const agentView = ev.target.closest("[data-agent-view]");
    if (agentView) setAgentView(agentView.dataset.agentView);
    const agentNode = ev.target.closest("[data-agent-open]");
    if (agentNode) {
      setView("activity");
      await loadActivity(true);
      setAgentView("list");
      const rows = document.querySelectorAll("#agent-grid .agent-row");
      const row = rows[Number(agentNode.dataset.agentOpen)];
      if (row) {
        row.open = true;
        row.scrollIntoView({ behavior: "smooth", block: "center" });
      }
    }
    const geographyView = ev.target.closest("[data-geography-view]");
    if (geographyView) {
      state.geographyView = geographyView.dataset.geographyView === "boxes" ? "boxes" : "map";
      renderGeographyExplorer(state.population);
    }
    const stateNode = ev.target.closest("[data-geo-state]");
    if (stateNode) {
      const area = stateByFips(stateNode.dataset.geoState);
      if (area) chooseGeography({ level: "state", id: `state:${area.fips}`, label: area.name, stateFips: area.fips });
    }
    const aggregateNode = ev.target.closest("[data-geo-state-aggregate]");
    if (aggregateNode) {
      const area = stateByFips(aggregateNode.dataset.geoStateAggregate);
      const profile = profileForState(area);
      if (area) chooseGeography({
        level: "state",
        id: `state:${area.fips}`,
        label: area.name,
        stateFips: area.fips,
        populationId: profile ? profile.population_id : null,
      });
    }
    const featureNode = ev.target.closest("[data-geo-feature]");
    if (featureNode) {
      const feature = (state.geographyPayload?.feature_collection?.features || []).find(
        (row) => String(row.id || row.properties?.id) === featureNode.dataset.geoFeature
      );
      if (feature) handleMapFeatureSelect(feature);
    }
    const profileNode = ev.target.closest("[data-geo-profile]");
    if (profileNode) {
      const profile = profileById(profileNode.dataset.geoProfile);
      if (profile) chooseGeography(geographySelectionForProfile(profile));
    }
    if (ev.target.closest("#geography-home, [data-geo-home]")) {
      state.geographyLayer = "states";
      chooseGeography({ level: "nation", id: "us:1", label: "United States" });
    }
  });
  window.addEventListener("polisim-geography-ready", () => renderMapGeometry());
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
    await loadReady();
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
