"""Exercise the browser's pure recording-selection rules with its actual JS."""
from pathlib import Path
import shutil
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
NODE = shutil.which("node") or str(Path.home() / ".cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node")


def test_recording_navigation_respects_selection_and_available_actions():
    if not Path(NODE).exists():
        pytest.skip("Node is not available")
    research = (ROOT / "leaderboard/static/research.js").read_text()
    live = (ROOT / "leaderboard/static/research-live.js").read_text()
    functions = research[research.index("function initialStudyId("):research.index("function scope(")]
    functions += live[live.index("function automaticRecording("):live.index("function stop(")]
    checks = r'''
const assert = require('node:assert/strict');
const studies = [{id:'individual'}, {id:'debate'}];
const runs = [{id:'older',mode:'replay',heartbeat_at:'2026-10-22'}, {id:'newer',mode:'replay',heartbeat_at:'2026-10-23'}];
const activities = [{events:[]}, {events:[],runs}];
assert.equal(initialStudyId(studies,activities,undefined),'debate');
assert.equal(initialStudyId(studies,activities,'individual'),'individual');
assert.equal(initialStudyId(studies,[null,null],undefined),'individual');
assert.equal(initialStudyId(studies,[{events:[{id:1}]},null],undefined),'individual');
assert.equal(automaticRecording({run_id:'missing',events:[],runs},''),'newer');
assert.equal(automaticRecording({run_id:'missing',events:[],runs},'explicit'),null);
assert.equal(automaticRecording({mode:'live',events:[],runs},''),null);
assert.equal(automaticRecording({events:[{id:1}],runs},''),null);
assert.equal(automaticRecording({coverage:{available_events:10},events:[],runs},''),null);
assert.equal(automaticRecording({events:[],runs:[...runs,{id:'active',mode:'live'}]},''),'active');
assert.equal(automaticRecording({events:[],runs:[{id:'missing',mode:'idle'}]},''),null);
'''
    subprocess.run([NODE, "-e", functions + checks], check=True, capture_output=True, text=True)
    for path in ("research.js", "research-live.js"):
        subprocess.run([NODE, "--check", str(ROOT / "leaderboard/static" / path)], check=True)
