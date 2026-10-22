// Observable events and explicitly labelled playback; this controller never launches a run.
const element = id => document.getElementById(id);
const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const labels = {run_started:'Run started',agent_started:'Agent began work',model_requested:'Model request sent',response_received:'Model response received',checkpoint_saved:'Checkpoint saved',message_sent:'Message delivered',evaluation_ready:'Evaluation saved',run_completed:'Run completed',run_failed:'Worker reported an error',evaluated:'Evaluation report saved',dialogue_phase:'Dialogue phase advanced'};
let studyId = null, requestedRun = '', currentRun = null, currentSession = null, events = [], selected = -1, feed = null;
let stage, watch = true, visible = true, playing = false, following = true, timer = null, pending = false, generation = 0, lastError = false, replayFromStart = false, controlEpoch = 0;
const isActive = () => document.body.dataset.view === 'research' && !document.hidden;
const eventKey = event => String(event.id ?? event.seq);
const summary = event => event.summary || labels[event.kind] || 'Recorded event';
const title = event => labels[event.kind] || String(event.kind || 'Recorded event').replaceAll('_',' ');
function stop() { controlEpoch++; stage?.pause?.(); playing = false; clearTimeout(timer); timer = null; element('research-play').textContent = 'Play recording'; }
async function ensureStage() {
  if (stage || !watch || !visible || !studyId) return;
  try { const {mountStudyTheater} = await import('/static/study-theater.js?v=1');
    if (!stage) stage = mountStudyTheater(element('research-theater'), {onActorSelect: actor => {
      const index = events.findLastIndex(event => event.actor === actor);
      if (index >= 0) { stop(); following = false; select(index); }
    }});
    drawStage();
  } catch { element('research-theater').textContent = '3D rendering unavailable. All recorded actions remain available in the playback list below.'; }
}
function drawStage() {
  const mode = following && feed?.mode === 'live' ? 'live' : 'replay';
  stage?.update({studyId, sessionId:`${currentRun}/${currentSession}`, event: events[selected] ? {...events[selected],id:`${currentRun}/${currentSession}/${events[selected].id}`} : null, mode, actors:[...new Set(events.map(e => e.actor).filter(Boolean))].slice(0,12)});
}
function select(index) {
  selected = events.length ? Math.max(0, Math.min(events.length - 1, index)) : -1;
  const event = events[selected];
  element('research-scrubber').value = String(Math.max(0,selected));
  element('research-event-position').textContent = `${selected + 1} / ${events.length}${feed?.has_more ? '+' : ''}`;
  const badge = following && feed?.mode === 'live' ? 'Live · following worker' : event ? 'Replay · recorded actions' : feed?.mode === 'unsupported' ? 'No action stream' : 'Waiting for recorded actions';
  element('research-feed-mode').textContent = badge;
  element('research-current-event').innerHTML = event ? `<strong>${escape(title(event))}${event.actor ? ` · ${escape(event.actor)}` : ''}</strong><span>${escape(summary(event))}</span><small>${escape(event.at || 'Original action time unavailable')}${event.phase ? ` · ${escape(event.phase)}` : ''}${event.model ? ` · ${escape(event.model)}` : ''}</small>` : '<strong>No recorded action to display</strong><span>The scene is illustrative and still. No model activity is being invented.</span>';
  element('research-play').disabled = !events.length;
  element('research-rewind').disabled = !events.length;
  element('research-step').disabled = !events.length || (selected === events.length - 1 && !feed?.has_more);
  element('research-follow').disabled = feed?.mode !== 'live';
  element('research-follow').setAttribute('aria-pressed',String(following && feed?.mode === 'live'));
  drawStage();
  document.querySelectorAll('[data-action-index]').forEach(button => button.setAttribute('aria-current', Number(button.dataset.actionIndex) === selected ? 'step' : 'false'));
}
function renderFeed() {
  if (!feed) return;
  const total = feed.coverage?.available_events ?? events.length;
  element('research-feed-status').textContent = lastError ? 'Connection lost. Showing the last recorded snapshot; live state is unconfirmed.' : `${feed.mode === 'live' ? 'Worker lease verified' : String(feed.status || 'Saved record').replaceAll('_',' ')} · ${events.length.toLocaleString()} actions loaded${total > events.length ? ` of ${Number(total).toLocaleString()}` : ''}`;
  element('research-action-disclosure').textContent = `${(feed.limitations || []).join(' ')} ${feed.coverage?.recent_window ? 'This timeline began with the most recent 120 events and adds new actions. Choose From beginning for the full replay.' : ''} Scenes and workstation positions are illustrative. Actions come from the record, not private model reasoning. Live view highlights the latest received action; replay steps through every recorded event. Playback compresses time.`;
  element('research-scrubber').max = String(Math.max(0,events.length - 1));
  element('research-scrubber').disabled = !events.length;
  element('research-event-count').textContent = `(${events.length.toLocaleString()})`;
  element('research-more-events').hidden = !feed.has_more;
  // A window around the cursor keeps the accessible log bounded, with the slider reaching all loaded events.
  const start = Math.max(0, selected - 10), end = Math.min(events.length,start + 30);
  const eventMarkup = events.slice(start,end).map((event,i) => `<li><button type="button" data-action-index="${start+i}" aria-current="${start+i === selected ? 'step' : 'false'}"><span>${start+i+1}</span><strong>${escape(title(event))}</strong><small>${escape(event.actor || 'Study')} · ${escape(event.phase || 'record')}</small></button></li>`).join('');
  const eventList = element('research-event-list');
  if (eventList.innerHTML !== eventMarkup) {
    const focusedIndex = eventList.contains(document.activeElement) ? document.activeElement.dataset.actionIndex : null;
    eventList.innerHTML = eventMarkup;
    if (focusedIndex != null) (eventList.querySelector(`[data-action-index="${Number(focusedIndex)}"]`) || element('research-scrubber')).focus({preventScroll:true});
  }
  const runs = feed.runs || [];
  const runOptions = [{id:'',label:'Automatic · follow current study'},...runs.filter(run=>run.id).map(run=>({id:run.id,label:run.label || run.id}))];
  if (currentRun && !runOptions.some(run=>run.id===currentRun)) runOptions.push({id:currentRun,label:currentRun});
  const optionSignature = JSON.stringify(runOptions);
  if (element('research-session').dataset.signature !== optionSignature) {
    element('research-session').innerHTML = runOptions.map(run=>`<option value="${escape(run.id)}">${escape(run.label)}</option>`).join('');
    element('research-session').dataset.signature = optionSignature;
  }
  element('research-session').value = requestedRun;
  select(selected);
}
async function fetchActivity({append = Boolean(feed && currentRun)} = {}) {
  if (!studyId || pending || !isActive()) return;
  pending = true;
  const token = generation;
  const params = new URLSearchParams({study_id:studyId,after:String(append ? feed?.next_after || 0 : 0),tail:String(!currentRun && !replayFromStart)});
  if (requestedRun) params.set('run_id',requestedRun);
  try {
    const response = await fetch(`/api/research/activity?${params}`,{cache:'no-store'});
    if (!response.ok) throw new Error(`Activity request failed (${response.status})`);
    const data = await response.json();
    if (token !== generation) return;
    const priorKey = events[selected] ? eventKey(events[selected]) : null;
    const changedRun = currentRun !== data.run_id || currentSession !== data.session_id;
    if (append && changedRun) { currentRun=null; currentSession=null; feed=null; events=[]; selected=-1; setTimeout(() => fetchActivity(),0); return; }
    if (changedRun) { stop(); events=[]; selected=-1; following=!replayFromStart; }
    currentRun = data.run_id; currentSession = data.session_id;
    const byId = new Map((append || !changedRun ? events : []).map(e=>[eventKey(e),e]));
    for (const event of data.events || []) byId.set(eventKey(event),event);
    events = [...byId.values()].sort((a,b)=>Number(a.seq)-Number(b.seq));
    // Keep the next-page cursor if a refresh just re-read the first page of a larger loaded record.
    if (!append && feed?.next_after > data.next_after && !changedRun) data.next_after = feed.next_after;
    if (!append && events.length >= (data.coverage?.available_events ?? Infinity)) data.has_more = false;
    if (append && feed?.coverage?.recent_window) {
      data.coverage = {...data.coverage, recent_window:true, prior_events:feed.coverage.prior_events};
    }
    feed=data; lastError=false;
    if (following && data.mode === 'live') selected=events.length-1;
    else if (priorKey && !changedRun) selected=Math.max(0,events.findIndex(e=>eventKey(e)===priorKey));
    else selected=events.length ? 0 : -1;
    renderFeed(); ensureStage();
  } catch {
    if (token !== generation) return;
    lastError=true; following=false; stop();
    if (feed) { feed={...feed,mode:'replay'}; renderFeed(); }
    else { element('research-feed-mode').textContent='Activity unavailable'; element('research-feed-status').textContent='Could not read the study event record. Refresh evidence to retry.'; }
  } finally { if (token === generation) pending=false; }
}
async function advance() {
  const token = generation, epoch = controlEpoch;
  if (selected >= events.length-1 && feed?.has_more) await fetchActivity({append:true});
  if (token !== generation || epoch !== controlEpoch) return false;
  if (selected < events.length-1) { select(selected+1); renderFeed(); return true; }
  return false;
}
async function playTick() {
  if (!playing || !isActive() || !watch) { stop(); return; }
  const epoch = controlEpoch;
  const advanced = await advance();
  if (epoch !== controlEpoch || !playing) return;
  if (!advanced) { stop(); return; }
  if (playing) timer=setTimeout(playTick,Number(element('research-speed').value));
}
function clearFeedDisplay() {
  element('research-feed-status').textContent='Reading the selected study’s event record…';
  element('research-event-list').replaceChildren();
  element('research-action-disclosure').textContent='Loading recorded actions. Scene positions are illustrative.';
  element('research-event-count').textContent='(0)';
  element('research-scrubber').max='0';
  element('research-scrubber').disabled=true;
  element('research-more-events').hidden=true;
  element('research-session').innerHTML='<option value="">Loading sessions…</option>';
  delete element('research-session').dataset.signature;
  select(-1);
  element('research-feed-mode').textContent='Loading activity';
}
function resetFeed({fromStart=false, run=requestedRun, follow=true}={}) {
  generation++; pending=false; stop(); replayFromStart=fromStart; requestedRun=run; currentRun=null; currentSession=null; events=[]; selected=-1; feed=null; following=follow; lastError=false;
  clearFeedDisplay(); fetchActivity();
}
function chooseStudy(id) {
  if (!id || id === studyId) { select(selected); return; }
  studyId=id; resetFeed({run:''}); ensureStage();
}
function setWatch(value) {
  watch=value; if (!watch) stop();
  element('research-watch-toggle').setAttribute('aria-pressed',String(watch));
  element('research-atlas-toggle').setAttribute('aria-pressed',String(!watch));
  element('research-theater').hidden=!watch || !visible;
  element('research-scene').hidden=watch || !visible;
  element('research-playback').hidden=!watch;
  element('research-scene-key').hidden=watch;
  element('research-stage-title').textContent=watch?'Agents at work':'Study atlas';
  if (watch) { ensureStage(); fetchActivity(); }
  else window.dispatchEvent(new CustomEvent('research-atlas-visible'));
}
element('research-watch-toggle').addEventListener('click',()=>setWatch(true));
element('research-atlas-toggle').addEventListener('click',()=>setWatch(false));
element('research-reset').addEventListener('click',()=>stage?.reset());
element('research-play').addEventListener('click',()=>{
  if (playing) {stop();return;}
  following=false;
  if (selected >= events.length-1 && !feed?.has_more) select(0);
  playing=true; element('research-play').textContent='Pause recording';
  timer=setTimeout(playTick,Number(element('research-speed').value)); select(selected);
});
element('research-step').addEventListener('click',()=>{stop();following=false;advance();});
element('research-follow').addEventListener('click',()=>resetFeed({follow:true}));
element('research-rewind').addEventListener('click',()=>resetFeed({fromStart:true,run:currentRun || '',follow:false}));
element('research-scrubber').addEventListener('input',event=>{stop();following=false;select(Number(event.target.value));renderFeed();});
element('research-more-events').addEventListener('click',()=>fetchActivity({append:true}));
element('research-session').addEventListener('change',event=>resetFeed({run:event.target.value}));
element('research-event-list').addEventListener('click',event=>{const button=event.target.closest('[data-action-index]');if(button){stop();following=false;select(Number(button.dataset.actionIndex));}});
element('research-refresh').addEventListener('click',()=>fetchActivity());
window.addEventListener('research-study-selected',event=>chooseStudy(event.detail.id));
window.addEventListener('research-scene-visibility',event=>{visible=event.detail.visible;setWatch(watch);});
window.addEventListener('research-view',()=>{if(!isActive())stop();else{ensureStage();fetchActivity();}});
document.addEventListener('visibilitychange',()=>{if(document.hidden)stop();else fetchActivity();});
setInterval(()=>{if(watch && isActive())fetchActivity();},2000);
const pressed=document.querySelector('[data-study-id][aria-pressed="true"]');
if(pressed)chooseStudy(pressed.dataset.studyId);
setWatch(true);
