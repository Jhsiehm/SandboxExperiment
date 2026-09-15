---
version: 1
slug: "leaderboard-static-index-html"
primary_target: "leaderboard/static/index.html"
related_targets: ["leaderboard/static/app.js","leaderboard/static/app.css","leaderboard/store.py","leaderboard/app.py"]
---

# Leaderboard surface

- Scope and mode: The `#leaderboard` tab is an Operate surface inside the existing dashboard.
- Audience and job: Research collaborators compare individual agents, scored swarm runs, model families, and corporations without leaving the selected epoch.
- Primary task: Change the ranking type or metric, inspect sample size and Brier evidence, then open a swarm result or its saved execution log.
- Proof: Rankings are computed from saved forecasts or swarm votes joined to later ground truth. Every row keeps Brier, forecast volume, and scope visible; the board never assigns a human-emulation score.
- Constraints: Preserve the archive's append-only behavior, distinguish individual votes from swarm aggregates, avoid official company marks, and keep all controls keyboard accessible and responsive.
- Direction: A tactical competition arena inside the voxel reconnaissance world. Original bot portraits use distressed screenprint, broken halftone, vertical ink drag, warm paper, and one restrained family color.
- Memorable moment: The three-agent podium turns current saved evidence into a game-like championship scene, while the adjacent standings and log keep the result auditable.
- Unresolved: None for the current `e2012` archive; future epochs inherit the same evidence rules.
