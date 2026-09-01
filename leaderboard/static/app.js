const ALIASES = { overview: "results", scoring: "results", runs: "forecasts" };
const VIEWS = ["results", "forecasts", "questions", "corpus", "lab"];
const state = {
  overview: null,
  questions: null,
  reveal: false,
  category: "",
  jobTimer: null,
  lastJobStatus: "idle",
  lastJobRunId: null,
  ready: null,
  selectedRun: null,
  runs: [],
  runListKey: "",
};

function $(sel) {
  return document.querySelector(sel);
}

function setText(sel, value) {
  const el = $(sel);
  if (el) el.textContent = value;
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
  document.querySelectorAll("nav.tabs button").forEach((btn) => {
    if (btn.dataset.view === name) btn.setAttribute("aria-current", "page");
    else btn.removeAttribute("aria-current");
  });
  if (location.hash !== `#${name}`) history.replaceState(null, "", `#${name}`);
  if (name === "results") loadScores();
  if (name === "forecasts") loadForecasts();
  if (name === "questions") loadQuestions();
  if (name === "corpus") loadCorpus();
  if (name === "lab") renderLab();
}

function runOptionKey(runs) {
  return (runs || [])
    .map((r) => `${r.run_id}|${r.label || r.run_id}|${r.n_predictions || 0}`)
    .join("\n");
}

function fillRunSelect(runs, preferred) {
  const select = $("#run-select");
  if (!select) return;
  const list = runs || [];
  const current = preferred || state.selectedRun || (list[0] && list[0].run_id) || "";
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
  const data = await getJSON("/api/overview");
  state.overview = data;
  setText("#mast-epoch", data.epoch.id);
  setText("#mast-cutoff", data.epoch.cutoff_date);
  setText("#mast-resolve", data.epoch.resolution_window_end);
  const runs = (data.runs || []).map((r) => ({
    ...r,
    label: (data.run_labels && data.run_labels[r.run_id]) || r.run_id,
  }));
  const liveId = (state.ready && state.ready.live_run_id) || data.live_run_id;
  const liveHas = runs.some((r) => r.run_id === liveId && r.n_predictions > 0);
  fillRunSelect(runs, state.selectedRun || (liveHas ? liveId : data.run.run_id));
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
  const q = new URLSearchParams();
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
  const data = await getJSON("/api/corpus");
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
  const res = await fetch("/search", {
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
  const res = await fetch("/fetch", {
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
  const runs = state.runs.length ? state.runs : (await getJSON("/api/runs")).runs || [];
  fillRunSelect(runs, state.selectedRun);
  if (!state.selectedRun) {
    $("#forecasts-empty").hidden = false;
    $("#pred-table").hidden = true;
    return;
  }
  const reveal = $("#f-reveal").checked;
  const data = await getJSON(
    `/api/runs/${encodeURIComponent(state.selectedRun)}?reveal_truth=${reveal}`
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
  const q = requested ? `?run_id=${encodeURIComponent(requested)}` : "";
  const data = await getJSON(`/api/scores${q}`);
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
}

function reliabilitySVG(curves) {
  const w = 360;
  const h = 220;
  const p = 36;
  const ids = Object.keys(curves);
  if (!ids.length) return `<p class="note">No calibration bins.</p>`;
  let paths = `<line x1="${p}" y1="${h - p}" x2="${w - p}" y2="${p}" stroke="#1f6b56" stroke-dasharray="3 3"/>`;
  ids.forEach((id, i) => {
    const bins = (curves[id].bins || []).filter((b) => b.n);
    const color = i === 0 ? "#171c22" : i === 1 ? "#9b3b2e" : "#1f6b56";
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
  return `<svg viewBox="0 0 ${w} ${h}" role="img" aria-label="Calibration">
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
  let paths = `<line x1="${zero}" y1="${p}" x2="${zero}" y2="${h - p}" stroke="#9b3b2e"/>`;
  curves.forEach((c, i) => {
    const color = i === 0 ? "#171c22" : i === 1 ? "#9b3b2e" : "#1f6b56";
    const pts = (c.buckets || [])
      .filter((b) => b.n && !Number.isNaN(b.mean_accuracy))
      .map((b) => `${xmap((b.gap_lo_days + b.gap_hi_days) / 2)},${ymap(b.mean_accuracy)}`)
      .join(" ");
    paths += `<polyline fill="none" stroke="${color}" points="${pts}"/>`;
  });
  return `<svg viewBox="0 0 ${w} ${h}" role="img" aria-label="Contamination">
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

function renderJob(job) {
  const status = job.status || "idle";
  const label = job.phase && status === "running" ? `${status} · ${job.phase}` : status;
  $("#run-state").dataset.status = status;
  $("#run-state-label").textContent = job.error && status === "error" ? "error" : label;
  const mockBtn = $("#run-btn");
  const liveBtn = $("#run-live-btn");
  const busy = status === "running";
  mockBtn.disabled = busy;
  mockBtn.textContent = busy && job.mock ? "Running…" : "Run practice";
  const liveOk = state.ready && state.ready.live_ready;
  liveBtn.disabled = busy || !liveOk;
  liveBtn.textContent = busy && !job.mock ? "Running…" : "Run live AI";
    liveBtn.title = liveOk
    ? "Score the cheap 1-question OpenRouter probe (not the 12-agent swarm)"
    : "Add OPENROUTER_API_KEY, or both ANTHROPIC_API_KEY and OPENAI_API_KEY, to .env";
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
      if (job.status === "done") setView("forecasts");
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

async function startSimulation(mock) {
  const mockBtn = $("#run-btn");
  const liveBtn = $("#run-live-btn");
  mockBtn.disabled = true;
  liveBtn.disabled = true;
  if (mock) mockBtn.textContent = "Running…";
  else liveBtn.textContent = "Running…";
  $("#run-log-band").hidden = false;
  $("#run-log").textContent = mock
    ? "Starting practice (keyword lookup)…"
    : "Starting live models…";
  if (window.Enchant) Enchant.setPose("search");
  const res = await fetch("/api/jobs/run", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ mock }),
  });
  if (res.status === 409) {
    await pollJob();
    return;
  }
  if (res.status === 412 || !res.ok) {
    const detail = await res.text();
    $("#run-state").dataset.status = "error";
    $("#run-state-label").textContent = "error";
    $("#run-log").textContent = `Start failed ${res.status}: ${detail}`;
    mockBtn.disabled = false;
    mockBtn.textContent = "Run practice";
    liveBtn.textContent = "Run live AI";
    applyReady(state.ready);
    if (window.Enchant) Enchant.setPose("error");
    return;
  }
  state.lastJobStatus = "running";
  await pollJob();
}

function applyReady(ready) {
  state.ready = ready || state.ready;
  const liveBtn = $("#run-live-btn");
  if (!liveBtn) return;
  const ok = state.ready && state.ready.live_ready;
  if (state.lastJobStatus !== "running") liveBtn.disabled = !ok;
}

function bind() {
  document.querySelectorAll("nav.tabs button").forEach((btn) => {
    btn.addEventListener("click", () => setView(btn.dataset.view));
  });
  $("#reveal-truth").addEventListener("change", loadQuestions);
  $("#q-category").addEventListener("change", loadQuestions);
  $("#search-form").addEventListener("submit", runSearch);
  $("#run-btn").addEventListener("click", () => startSimulation(true));
  $("#run-live-btn").addEventListener("click", () => startSimulation(false));
  $("#run-select").addEventListener("change", async () => {
    state.selectedRun = $("#run-select").value || null;
    try {
      await loadScores();
      await loadForecasts();
    } catch (err) {
      console.error("Failed to load run", state.selectedRun, err);
    }
  });
  $("#f-model").addEventListener("change", loadForecasts);
  $("#f-reveal").addEventListener("change", loadForecasts);
  document.body.addEventListener("click", (ev) => {
    const fetchBtn = ev.target.closest("[data-fetch]");
    if (fetchBtn) fetchDoc(fetchBtn.dataset.fetch);
  });
  window.addEventListener("hashchange", () => setView(location.hash.replace("#", "")));
}

async function boot() {
  bind();
  try {
    state.ready = await getJSON("/api/jobs/ready");
    applyReady(state.ready);
  } catch (err) {
    applyReady({ live_ready: false });
  }
  try {
    await loadOverview();
  } catch (err) {
    $("#overview-errors").textContent = String(err);
  }
  const hash = location.hash.replace("#", "");
  const liveId = state.ready && state.ready.live_run_id;
  const liveHas = (state.runs || []).some((r) => r.run_id === liveId && r.n_predictions > 0);
  if (liveHas && !hash) setView("forecasts");
  else setView(hash || "results");
  pollJob();
}

boot();
