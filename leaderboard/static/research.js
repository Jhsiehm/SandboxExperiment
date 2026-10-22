// Aggregate research evidence only. No participant records enter this view.
const $ = (id) => document.getElementById(id);
const escape = (value) => String(value ?? '').replace(/[&<>"']/g, (char) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
const number = (value) => value == null ? 'Not reported' : typeof value === 'number' ? new Intl.NumberFormat('en-US', {maximumFractionDigits: 6}).format(value) : String(value);
const statusLabel = (status) => ({saved_results:'Saved results',saved_progress:'Saved progress',protected:'Protected reserve',missing:'Not materialized',planned:'Planned',running:'Running',active:'Running'}[status] || String(status || 'Unknown').replaceAll('_',' '));
let payload, selectedId, scene, busy = false, sceneVisible = true, liveJob = null, latestError = false;
const active = () => ['research','library'].includes(document.body.dataset.view);
async function json(url) { const response = await fetch(url, {cache:'no-store'}); if (!response.ok) throw new Error(`Request failed (${response.status})`); return response.json(); }
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
  $('research-study-list').innerHTML = studies.map(study => `<button type="button" class="research-study-choice" data-study-id="${escape(study.id)}" aria-pressed="${study.id === selectedId}"><strong>${escape(study.title)}</strong><span>${escape(statusLabel(study.status))}</span></button>`).join('');
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
    if (!payload.studies.some(study => study.id === selectedId)) selectedId = payload.studies[0]?.id;
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
