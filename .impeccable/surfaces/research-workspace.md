---
version: 2
slug: "research-workspace"
primary_target: "leaderboard/static/index.html"
related_targets: ["leaderboard/static/research.css", "leaderboard/static/research.js", "leaderboard/static/study-scene.js", "leaderboard/static/study-theater.js", "leaderboard/static/research-live.js", "leaderboard/research_activity.py", "leaderboard/static/app.js"]
---

# Research workspace

## Scope and direction

Mode: **Operate**. This is a code-led local extension of the incumbent Voxel Reconnaissance Table, with no generated design comps. The user requested balanced current-experiment and data-library views, creative 3D pixel studies, and clearer navigation and launch workflows across tabs. Preserve the matte shell, Plex typography, flat square controls, evidence boundaries, and incumbent population geography. The approved symbolic study dioramas and game-style action stage extend the visual language within the atlas. The user subsequently requested realistic custom work animations and a live view of agent actions; animation remains an illustrative translation of recorded events.

Exact targets are `#view-research` (Study atlas, route `#research`) and `#view-library` (Data library, route `#library`), plus the shared tab rail, `.forecast-workflow`, and `#run-box`. The atlas is the no-hash default after initialization. Existing detail routes remain intact: Forecast eras, Execution log, Forecast rankings, Run builder, How it works, Population map, ANES analysis, Forecast results, Forecast answers, Question bank, Frozen evidence, and Setup.

## Primary task and signature interaction

Inspect a study's recorded scope, measures, limitations, and provenance; then open its supported detail view or inspect the source inventory. Clicking a study island, a study button, or a table study name synchronizes selection and the evidence inspector. Study buttons provide the keyboard-equivalent path. The bounded scene renders at most twelve studies, substituting the selected study into that set when needed; the complete button list and table remain authoritative.

The overview signature is a set of original small research dioramas: isolated interview stations, paired ablation desks, a discussion table, household comparisons, a sealed reserve vault, and an archive. Drag to orbit/pan; use explicit zoom buttons and Reset camera. Wheel zoom is disabled so page scrolling remains available. The 3D view toggle hides only the scene. A WebGL failure leaves the evidence list usable. Camera motion is not required to understand the study.

## Selected-study action stage

Agents at work is the default stage; Watch/Atlas switches to the original overview. Crisp orthographic voxel environments adapt to the selected study: individual interview stations, paired ablation desks, a discussion room, household setting, forecast archive, and sealed reserve. Anonymous figures come from recorded agent aliases, with at most twelve visible and the selected actor included. Clicking a figure selects its latest loaded event. Station positions, appearance, furniture, and figure counts are illustrative, not respondent geography, population counts, or observed social ties.

The action player provides a run selector, play/pause, next action, playback speed, scrubber, Follow live, From beginning, and a text event list with additional pages. Live follows the latest received action; it does not promise to animate every event in a burst. Replay steps through the loaded record and can fetch further pages. Time is compressed. The event text, original timestamp when available, phase, coverage, and limitations remain adjacent to the scene.

Custom work vignettes depict the event kind: alternating hands at the keyboard for a model request, reading and pointing at a returned document, lifting and stacking a saved checkpoint sheet, a sender's speech tile and gesture for delivered messages, and a review gesture for evaluation. Articulated arms, head and torso poses, document props, and terminal highlights make actions legible. They are symbolic choreography, not observed physical motion or private reasoning. A message does not establish a recipient path. Each transition is bounded; no recorded activity leaves the scene still. Reduced motion, document visibility, and scene visibility suppress animation. The text log remains the accessible equivalent and WebGL fallback.

## Content truth

`research.js` reads aggregate summaries from `/api/research/overview` and forecast-job state separately from `/api/jobs/run`. It does not render participant records. The selected inspector reports the saved status, completed/total scope with units, measures, limitations, source path, and an allowed detail link. A missing number reads “Not reported”; absence is not zero. Study-specific 0–1 error bars retain numeric labels and the “lower is better” qualifier. The cross-study table explicitly disclaims ranking because measures differ.

Only a completion tower encodes quantity: its fixed frame contains the clamped recorded completed/total fraction when the denominator is positive and completion is known. Unknown completion is labeled unreported. In the overview, figures, desks, houses, books, and vault dimensions are illustrative; their counts are not sample sizes, agents, observed ties, scientific quality, or behavioral evidence. Action-stage figures separately identify recorded anonymous agent aliases without encoding population size. The scene legend states this distinction adjacent to the canvas.

Library search matches title, summary, and source; the availability filter separates locally present and unmaterialized entries. Each row keeps source, count/unit, optional breakdown, and runtime-access language separate. An available file does not establish agent access. Protected targets and comparison layers must remain outside runtime context according to their study boundaries. Do not turn plan readiness or saved progress into claims that paid calls have started or a process is currently running.

## Refresh and activity contract

Refresh evidence fetches summaries without cache. Automatic polling occurs every 15 seconds only while Study atlas or Data library is active and the document is visible. Returning to a visible document requests a refresh; returning to an already-loaded tab may display the saved snapshot until the next poll. The status line identifies the evidence-read time, refresh failures, and independently observed forecast activity. A failed overview refresh preserves the previous snapshot with a failure label; an initial failure presents retry guidance. Job-fetch failure reports live status unavailable.

Saved checkpoints do not establish liveness. Overview terminal/antenna animation can reflect the independently observed forecast job. The selected-study player separately polls `/api/research/activity` every two seconds while Watch is active, the research tab is selected, and the document is visible. It uses session-scoped cursors and 120-event pages; the initial verified live view starts at the most recent 120 events, explicitly discloses the omitted earlier window, and offers From beginning. A lost connection preserves the recorded snapshot and removes the live claim.

New instrumented invocations of individual validation, profile ablation, and the social benchmark emit safe append-only action telemetry and a status heartbeat. Live requires both a current heartbeat lease and matching process identity. Events include run/agent start, model request, response received, checkpoint saved, message delivered, evaluation ready, completion, and failure where emitted by that runner. Cached work does not fabricate fresh model calls. Actor and group labels are anonymous ordinals; prompts, message bodies, private profiles, predictions, and evaluation targets are not exposed. Completion in telemetry is scoped to checkpoint events in the current invocation; resumed runs may have earlier saved checkpoints.

Historic runs without telemetry expose a checkpoint inventory and saved evaluation markers only. Discovery order is not original execution order, original action times are unavailable, and intermediate model or message actions cannot be reconstructed. A changing inventory is not a live worker. Forecast exposes job state here but no per-agent action telemetry; Execution log remains its monitoring route. Oregon has no instrumented action stream and remains an illustrative household setting. The reserve is protected and shows no agents or activity. No continuous decorative idle animation is required.

## Forecast workflow

The shared route is Check setup → Choose era → Configure run → Monitor → Review results. It is hidden on Study atlas, Data library, and ANES analysis to avoid implying those studies share the forecast launch contract. The compact research/library masthead hides forecast run selection and metadata.

Run builder, Execution log, and Setup expose the forecast-control heading, prerequisite/state text, and three actions: Run practice, Run live mix, and Run configured swarm. These controls remain visible on mobile and use a 44px minimum height. The disclosure explains run types and points to Run builder and Setup; ANES, DEBATE, and Oregon retain separate contract-driven CLI workflows. Other forecast tabs retain run selection without the launch-action cluster. Existing readiness, paid-traffic, and cost checks remain authoritative.

## Implemented visual and responsive contract

- Research headings: Plex Sans, `clamp(32px, 3.6vw, 52px)`, weight 500, line height 1.12, tracking -0.035em. Inspector titles: 26px/1.2; explanatory inspector text: 14px/1.65. Table body: 13px; mono headers: 11px/1.5.
- The workspace shares borders: flexible scene plus 340px inspector, reduced to 290px at 1100px and stacked at 800px. Overview scene heights are 430px, 390px at 1100px, and 320px at 520px. Action-stage heights are 490px, 430px at 1100px, and 360px at 520px; transport and run controls wrap on narrow screens. Study choices use three columns, then two at 520px, and at least 90px height.
- Research-specific CSS colors are teal `#93bcb7`, scene-side surface `#0a100e`, hover `#15231c`, and selected study `#1a2b20`. The scene's illustrative material palette includes green `#a9f05f`, teal `#76b4ad`, amber `#d4b571`, paper `#d2dcc5`, timber `#6f7758`, and skin `#b8a88a`; these do not redefine operational status colors. The action stage intentionally adds floor `#425440`, ground `#101c17`, edges `#283a2e`, dark furniture `#17271f`, and paper caption text `#d2dcc5` with a muted floor-colored border. These are local voxel material and overlay colors, not accidental global token drift.
- In-scene selection uses a thicker paper-colored strip; pressed study buttons also use phosphor text and an inset baseline. Preserve text and pressed-state feedback instead of relying on material color alone.
- Display buttons have a 36px minimum height; scene zoom buttons are 36px square. Library fields are at least 44px high. Focus inherits the amber outline with a 3px offset on research controls.
- Library rows use three columns, then two at 800px, then one at 520px. Search/filter controls wrap on narrow screens. Long source paths wrap inside the inspector and rows.
- All tab buttons scroll within the tab rail. Evidence tables scroll inside `.sheet-wrap` or `.research-table-wrap`, which are positioned and have `min-width: 0` to contain accessible labels. At 620px and below a visible horizontal-swipe hint appears. Composition tables retain a 640px minimum width, 200px first column, 240px model column, and unbroken model IDs. Prevent viewport-wide overflow rather than compressing identifiers into unreadable fragments.

## Review record and limits

This document records the implemented extension, not new research conclusions. The original atlas/library review returned SHIP after all three findings were resolved; that verdict predates the action-stage extension. The focused final mobile check confirmed a 390px document width without viewport overflow. This documentation does not claim a final review verdict for the newer action stage or that a paid experiment was launched. Local artifact availability, study process observation, and future study results remain runtime-dependent.
