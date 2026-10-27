// Aggregate research evidence only. No participant records enter this view.
const $ = (id) => document.getElementById(id);
const escape = (value) => String(value ?? '').replace(/[&<>"']/g, (char) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
const number = (value) => value == null ? 'Not reported' : typeof value === 'number' ? new Intl.NumberFormat('en-US', {maximumFractionDigits: 6}).format(value) : String(value);
const statusLabel = (status) => ({saved_results:'Saved results',saved_progress:'Saved progress',protected:'Protected reserve',missing:'Not materialized',planned:'Planned',running:'Running',active:'Running'}[status] || String(status || 'Unknown').replaceAll('_',' '));
const recordingStudies = new Set();
let payload, selectedId, scene, busy = false, sceneVisible = true, liveJob = null, latestError = false;
const active = () => ['research','library'].includes(document.body.dataset.view);
async function json(url) { const response = await fetch(url, {cache:'no-store'}); if (!response.ok) throw new Error(`Request failed (${response.status})`); return response.json(); }
function initialStudyId(studies, activities, currentSelection) {
  if (studies.some(study => study.id === currentSelection)) return currentSelection;
  const recorded = studies.find((study, index) => {
    const activity = activities[index];
    return activity && (activity.events?.length || activity.runs?.some(run => ['live','replay'].includes(run.mode)));
  });
  return recorded?.id || studies[0]?.id;
}
function scope(study) {
  if (study.completed == null) return 'Not reported';
  return `${number(study.completed)}${study.total == null ? '' : ` / ${number(study.total)}`} ${study.unit || 'records'}`;
}
function sceneModel() {
  return { studies: (payload?.studies || []).map(study => ({...study, status: study.id === 'forecast' && liveJob?.status === 'running' ? 'running' : study.status})), selectedId };
}
async function ensureScene() {
  if (scene || !payload || !sceneVisible || document.body.dataset.view !== 'research') return;
  try {
    const {mountStudyScene} = await import('/static/study-scene.js?v=1');
    if (!scene) scene = mountStudyScene($('research-scene'), {onSelect: selectStudy});
    scene.update(sceneModel());
  } catch { $('research-scene').textContent = '3D view unavailable. Select a study below to inspect all recorded evidence.'; }
}
function selectStudy(id) {
  if (!payload?.studies.some(study => study.id === id)) return;
  selectedId = id;
  document.querySelectorAll('[data-study-id]').forEach(button => button.setAttribute('aria-pressed', String(button.dataset.studyId === id)));
  const study = payload.studies.find(item => item.id === id);
  const measures = study.measures || [];
  const scores = measures.filter(m => typeof m.value === 'number' && m.value >= 0 && m.value <= 1 && /brier|rps|direct|review|prevalence|smoothed/i.test(m.label));
  const counts = measures.filter(m => !scores.includes(m));
  const detail = ['anes','runs','activity','results','population'].includes(study.detailView) ? study.detailView : null;
  $('research-inspector').innerHTML = `<span class="research-state" data-state="${escape(study.status)}">${escape(statusLabel(study.status))}</span><h3>${escape(study.title)}</h3><p>${escape(study.summary)}</p><dl><div><dt>Recorded scope</dt><dd>${escape(scope(study))}</dd></div>${counts.map(measure => `<div><dt>${escape(measure.label)}</dt><dd>${escape(number(measure.value))}</dd></div>`).join('')}</dl>${scores.length ? `<div class="research-score-chart" aria-label="Within-study recorded error measures">${scores.map(m => `<div><span>${escape(m.label.replaceAll('_', ' '))}</span><strong>${escape(number(m.value))}</strong><div class="research-score-track"><i style="width:${m.value * 100}%"></i></div></div>`).join('')}<p>Recorded error · 0–1 scale · lower is better</p></div>` : ''}<h4>Interpretation</h4><ul>${(study.limitations || []).map(item => `<li>${escape(item)}</li>`).join('')}</ul><h4>Evidence source</h4><code class="research-source">${escape(study.source)}</code>${detail ? `<a href="#${detail}">Open ${detail === 'anes' ? 'ANES detail' : detail === 'runs' ? 'forecast run archive' : detail}</a>` : ''}`;
  scene?.update(sceneModel());
  window.dispatchEvent(new CustomEvent("research-study-selected", {detail: {id, title: study.title}}));
}
function renderStudies() {
  const studies = payload.studies || [];
  $('research-study-list').innerHTML = studies.map(study => `<button type="button" class="research-study-choice" data-study-id="${escape(study.id)}" aria-pressed="${study.id === selectedId}"><strong>${escape(study.title)}</strong><span>${recordingStudies.has(study.id) ? 'Recording available · ' : ''}${escape(statusLabel(study.status))}</span></button>`).join('');
  $('research-measures').innerHTML = studies.map(study => `<tr><td><button type="button" data-inspect-study="${escape(study.id)}">${escape(study.title)}</button></td><td>${escape(statusLabel(study.status))}</td><td>${escape(scope(study))}</td><td>${escape(number(study.metricValue))}<small>${escape(study.metricLabel || 'No quantitative measure reported')}</small></td></tr>`).join('');
  const plan = payload.plan || {};
  $('research-plan').textContent = `${plan.summary || 'Individual prediction, social updating and observed behavior.'} Plan: ${statusLabel(plan.status)}. ${plan.paidCallsStarted === false ? 'Paid calls for this plan have not started.' : 'Paid-call status follows the saved plan.'}`;
  $('research-caveats').innerHTML = (payload.caveats || []).map(item => `<li>${escape(item)}</li>`).join('');
  selectStudy(selectedId);
  ensureScene();
}
function renderLibrary() {
  if (!payload) return;
  const query = $('research-library-query').value.trim().toLowerCase();
  const filter = $('research-library-filter').value;
  const entries = (payload.library || []).filter(item => `${item.title} ${item.summary} ${item.source}`.toLowerCase().includes(query) && (filter === 'all' || (filter === 'available' ? item.available : !item.available)));
  $('research-library-count').textContent = `${entries.length} of ${payload.library.length} sources`;
  $('research-library-list').innerHTML = entries.length ? entries.map(item => `<article class="research-library-row"><div><h3>${escape(item.title)}</h3><p>${escape(item.summary)}</p><code class="research-source">${escape(item.source)}</code>${item.measures?.length ? `<p class="research-library-breakdown">${item.measures.map(m => `${escape(m.label)}: ${escape(number(m.value))}`).join(' · ')}</p>` : ''}</div><div class="research-library-count">${escape(number(item.count))}<small>${escape(item.unit || 'records')}</small></div><div class="research-library-access"><strong>${item.available ? 'Available locally' : 'Not materialized'}</strong><span class="research-state">${item.runtimeAccess === true ? 'Study-controlled input' : item.runtimeAccess === false ? 'Runtime access off' : 'Study-specific access'}</span><p>${typeof item.runtimeAccess === 'string' ? escape(item.runtimeAccess) : 'Availability and agent access are separate.'}</p></div></article>`).join('') : '<p class="empty">No sources match these filters. Try a broader search or choose All sources.</p>';
}
function panelDevelopmentMarkup(panel) {
  if (!panel) return '';
  const q = panel.quality;
  return `<section aria-label="Statistical reference and panel readiness"><h4>Reference retained · next panel preparation</h4><p>${panel.reference_retained ? `Six-category DEBATE statistical reference retained: ${escape(number(q.unique_people))} people across ${escape(number(q.unique_groups))} groups; ${escape(number(q.unchanged_count))} unchanged responses and ${escape(number(q.changed_count))} changed.` : 'Reference retention is unverified.'}</p><p>Planned ANES seven-category party identification: 2016 → 2020 development; 2020 → 2024 later readout. This requires a separate model and source mapping.</p><p>Development export tooling: ${panel.development_export_tool_ready ? 'ready' : 'unverified'}. Real panel records audited: ${escape(number(panel.real_panel_records_audited))}. ${panel.status === 'blocked_on_source_metadata' ? `Source metadata blocks ingestion (${escape(number(panel.source_blocker_count))} blockers): official source archive, question construction, and release mapping remain pending.` : 'Source readiness is unverified.'}</p><p>Model training ${panel.model_training_enabled === false ? 'disabled' : 'status unverified'}; later-wave readout ${panel.later_wave_readout_enabled === false ? 'disabled' : 'status unverified'}. Preparation is not deployment validation.</p></section>`;
}
function residualCalibrationMarkup(calibration) {
  if (!calibration) return '';
  const states = {
    prepared_or_running_unverified: 'Prepared · process state not verified',
    summary_saved_unverified: 'Summary saved · completion not verified',
    forwards_completed: '92 model evaluations completed · calibration results pending',
    forward_stopped: 'Model evaluation stopped',
    calibration_failed: 'Calibration stopped before a valid result',
    results_saved_unverified: 'Results saved · execution completion not verified',
    oof_gate_failed: 'Cross-validation gate failed',
    oof_passed_internal_pending: 'Cross-validation gate passed · internal readout pending',
    internal_direction_failed: 'Internal readout did not retain improvement',
    gates_passed_review_required: 'Development gates passed · review required'
  };
  const oof = calibration.oof;
  const internal = calibration.internal;
  const results = oof ? `<p>Five-fold training cross-validation · normalized RPS, lower is better: transition baseline <strong>${escape(number(oof.mean_rps.transition))}</strong>; calibrated control <strong>${escape(number(oof.mean_rps.control))}</strong>; base-logit extension <strong>${escape(number(oof.mean_rps.extension))}</strong>.</p><p>Extension improvement versus control: ${escape(number(oof.extension_gain.control))}; versus transition: ${escape(number(oof.extension_gain.transition))}. Positive means improvement; the fixed gate requires at least 0.01 against both, with a component-level harm limit.</p>` : '<p>Cross-validation results have not been recorded.</p>';
  const stopped = calibration.status === 'oof_gate_failed' ? '<p>The extension did not pass the fixed progression gate. Full-data refitting and the internal readout were not started; outer validation and interaction did not advance.</p>' : '';
  const internalResult = internal ? `<p>Already-exposed internal readout: transition ${escape(number(internal.mean_rps.transition))}; control ${escape(number(internal.mean_rps.control))}; extension ${escape(number(internal.mean_rps.extension))} RPS. Improvement direction ${internal.direction_retained === true ? 'retained' : internal.direction_retained === false ? 'not retained' : 'not reported'}.</p>` : '';
  return `<section id="research-residual-calibration" aria-label="Residual calibration experiment"><h4>Does frozen-base information improve the transition baseline?</h4><p><strong>${escape(states[calibration.status] || 'Status not reported')}</strong></p><p>Saved model evaluations: ${escape(number(calibration.completed))}/92${calibration.forward_completed && calibration.elapsed_seconds != null ? ` · ${escape(number(calibration.elapsed_seconds))} seconds` : ''}. One fixed base model; no model training or generated conversation.</p>${results}${stopped}${internalResult}<p>Development evidence only. Saved files do not establish that a process is currently running. These results do not establish deployment readiness or valid human simulation.</p></section>`;
}

function renderLocalProgress() {
  const panel = $('research-local-progress');
  if (!panel) return;
  const progress = payload?.local_comparison;
  panel.hidden = !progress;
  if (!progress) return;
  const labels = {completed:'Completed', stopped:'Stopped', summary_saved_unverified:'Summary saved · completion unverified', progress_saved_unverified:'Progress saved · process state unverified', not_recorded:'Not recorded yet'};
  const decision = progress.stage_decision;
  const decisionMarkup = decision ? `<section aria-label="Comparison stage decision"><h4>Belief-transfer stage · ${escape(decision.status)}</h4><p>Base: ${escape(number(decision.base_valid))} / ${escape(number(decision.base_planned))} valid. Adapter: ${escape(number(decision.adapter_valid))} / ${escape(number(decision.adapter_planned))} valid after ${escape(number(decision.adapter_attempted))} attempt(s).</p>${decision.reason === 'pilot_adapter_first_prediction_invalid_json' ? '<p>The adapter’s first output was invalid JSON, so the format gate stopped belief-transfer testing. Message-scoring improvement does not establish belief-prediction improvement.</p>' : ''}<p>${decision.outcome_scoring_performed === false ? 'Belief outcomes were not scored.' : decision.outcome_scoring_performed === true ? 'Outcome scoring was recorded.' : 'Outcome-scoring status is unreported.'} ${decision.B2 === 'not_started_format_gate_failed' ? 'Private reflection and social interaction (B2) were deferred.' : 'B2 status is unreported.'}</p><p>Retries: ${escape(number(decision.retries))} · repairs: ${escape(number(decision.repairs))} · new paid calls: ${escape(number(decision.new_paid_calls))}</p></section>` : '';
  const smoke = progress.format_smoke;
  const smokeMarkup = smoke ? `<section aria-label="Training format diagnostic"><h4>Separate training-only format test · ${smoke.passed ? 'passed' : 'gate failed'}</h4><p>Base valid responses: original ${escape(number(smoke.counts.base.original))}/4; JSON prefix ${escape(number(smoke.counts.base.assistant_prefill))}/4. Adapter: original ${escape(number(smoke.counts.pilot_adapter.original))}/4; JSON prefix ${escape(number(smoke.counts.pilot_adapter.assistant_prefill))}/4.</p><p>Sixteen fixed attempts; no repairs or prompt search. This tests output format, not belief accuracy. The earlier stopped comparison remains unchanged.</p></section>` : '';
  const classifier = progress.classifier;
  const classifierMarkup = classifier ? `<section aria-label="Six-category classifier pilot"><h4>New six-category classifier · development pilot</h4><p>Training: ${classifier.training_completed ? 'completed' : 'saved progress; completion unverified'} · ${escape(number(classifier.steps))}/52 steps.</p>${classifier.internal_completed ? `<p>Internal check, 24 people: base RPS ${escape(number(classifier.base_rps))}; candidate ${escape(number(classifier.candidate_rps))}. Lower is better. Numerical progression gate ${classifier.gate_passed ? 'passed' : 'failed'}.</p><p>Persistence RPS ${escape(number(classifier.persistence_rps))}; training-only transition baseline ${escape(number(classifier.transition_rps))}.</p>` : '<p>Internal outcome evaluation not yet recorded.</p>'}<p>Probabilities are calculated over six declared categories. Valid output does not establish calibration or behavioral improvement.</p></section>` : '';
  const calibrationMarkup = residualCalibrationMarkup(progress.residual_calibration);
  const investigation = progress.investigation;
  const investigationNext = progress.residual_calibration ? 'Current test: the residual calibration panel above reports whether frozen base-model information adds value beyond the initial-state baseline.' : 'Next proposed test: fit a small correction using training data to determine whether frozen base-model scores add value beyond the initial-state baseline.';
  const investigationMarkup = investigation ? `<section aria-label="Classifier investigation"><h4>Investigation · already-scored internal cases</h4><p>The candidate favored category 4 for ${escape(number(investigation.candidate_category4_count))}/${escape(number(investigation.people))} people. Unchanged respondents accounted for about ${escape(number(100 * investigation.unchanged_gap_fraction))}% of its disadvantage against the statistical baseline.</p><p>Reconstructed training exposure: ${escape(number(investigation.reconstructed_exposed_rows))}/${escape(number(investigation.fit_rows))} records. A statistical control fitted to those same reconstructed records still scored ${escape(number(investigation.sampled_baseline_rps))} RPS.</p><p>These are post-hoc diagnostics, not a proven cause. ${escape(investigationNext)}</p></section>` : '';
  panel.innerHTML = `<h3>${escape(progress.description)}</h3>${panelDevelopmentMarkup(progress.panel_development)}${calibrationMarkup}${investigationMarkup}${classifierMarkup}${decisionMarkup}${smokeMarkup}<ul>${progress.arms.map(arm => `<li><strong>${escape(arm.label)}</strong>: ${escape(labels[arm.status] || 'Unknown')} · ${escape(number(arm.completed))} / ${escape(number(arm.total))} messages${arm.status === 'completed' && arm.token_weighted_nll != null ? ` · token-weighted NLL ${escape(number(arm.token_weighted_nll))}` : ''}</li>`).join('')}</ul><p>${escape(progress.limitation)}</p><small>${escape(progress.source)}</small>`;
}
function updateStatus() {
  if (!payload) return;
  const stamp = new Date(payload.generated_at);
  const time = Number.isNaN(stamp.valueOf()) ? 'just now' : stamp.toLocaleTimeString([], {hour:'2-digit',minute:'2-digit',second:'2-digit'});
  const activity = liveJob?.status === 'running' ? 'Forecast job running · atlas activity observed' : liveJob ? 'No forecast job running · selected study activity shown below' : 'Live job status unavailable';
  $('research-status').textContent = `${latestError ? 'Refresh failed · showing last snapshot' : `Evidence read ${time}`} · ${activity}`;
}
async function refresh() {
  if (busy || !active() || document.hidden) return;
  busy = true;
  $('research-refresh').disabled = true;
  const results = await Promise.allSettled([json('/api/research/overview'),json('/api/jobs/run')]);
  liveJob = results[1].status === 'fulfilled' ? results[1].value : null;
  if (results[0].status === 'fulfilled') {
    const next = results[0].value;
    const changed = JSON.stringify([payload?.studies,payload?.library,payload?.plan]) !== JSON.stringify([next.studies,next.library,next.plan]);
    payload = next; latestError = false;
    renderLocalProgress();
    if (!payload.studies.some(study => study.id === selectedId)) {
      // Aggregate reports and action recordings have independent availability.
      const activities = await Promise.all(payload.studies.map(study =>
        ['live_model_record','mixed_archive'].includes(study.kind)
          ? json(`/api/research/activity?study_id=${encodeURIComponent(study.id)}&tail=true`).catch(() => null)
          : Promise.resolve(null)));
      activities.forEach((activity, index) => {
        if (activity && (activity.events?.length || activity.runs?.some(run => ['live','replay'].includes(run.mode)))) recordingStudies.add(payload.studies[index].id);
      });
      // A user may have selected a study while discovery was in flight.
      selectedId = initialStudyId(payload.studies, activities, selectedId);
    }
    if (changed) { renderStudies(); renderLibrary(); }
    else scene?.update(sceneModel());
    updateStatus();
  } else {
    latestError = true;
    if (payload) updateStatus();
    else { $('research-status').textContent = 'Research evidence could not be loaded. Use Refresh evidence to retry.'; $('research-library-list').innerHTML = '<p class="empty">Research evidence could not be loaded. <button type="button" class="act ghost" data-research-retry>Retry</button></p>'; }
  }
  busy = false; $('research-refresh').disabled = false;
}
$('research-refresh').addEventListener('click', refresh);
$('research-library-query').addEventListener('input', renderLibrary);
$('research-library-filter').addEventListener('change', renderLibrary);
$('research-reset').addEventListener('click', () => scene?.reset());
$('research-scene-toggle').addEventListener('click', () => {
  sceneVisible = !sceneVisible; $('research-scene').hidden = !sceneVisible || $('research-atlas-toggle').getAttribute('aria-pressed') !== 'true';
  window.dispatchEvent(new CustomEvent('research-scene-visibility', {detail: {visible: sceneVisible}}));
  $('research-scene-toggle').setAttribute('aria-pressed', String(sceneVisible));
  $('research-scene-toggle').textContent = sceneVisible ? '3D view' : 'Show 3D view';
  $('research-reset').disabled = !sceneVisible;
  ensureScene();
});
document.addEventListener('click', event => {
  const button = event.target.closest('[data-study-id], [data-inspect-study]');
  if (button) {
    selectStudy(button.dataset.studyId || button.dataset.inspectStudy);
    if (button.dataset.inspectStudy) $('research-inspector').scrollIntoView({block:'nearest',behavior:matchMedia('(prefers-reduced-motion: reduce)').matches ? 'instant' : 'smooth'});
  }
  if (event.target.closest('[data-research-retry]')) refresh();
});
window.addEventListener('research-view', () => { if (active()) { if (!payload) refresh(); else { ensureScene(); updateStatus(); } } });
document.addEventListener('visibilitychange', () => { if (!document.hidden) refresh(); });
setInterval(refresh, 15000);
if (active()) refresh();

window.addEventListener('research-atlas-visible', ensureScene);
