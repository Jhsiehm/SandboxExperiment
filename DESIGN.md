---
name: Prediction Sandbox
description: A tactical voxel-reconnaissance workbench for inspecting cutoff-controlled model experiments and their evidence.
colors:
  void: "#070b09"
  shell: "#0b110e"
  surface: "#0e1511"
  surface-raised: "#111a15"
  ink: "#e8eee9"
  ink-control: "#cbd8d1"
  muted: "#92a097"
  divider: "#26332d"
  divider-strong: "#43564c"
  phosphor: "#a9f05f"
  focus-amber: "#d5b35b"
  exception-red: "#ff5353"
  validated-terrain: "#667b4d"
  comparison-terrain: "#536b73"
  source-terrain: "#7f734c"
  missing-terrain: "#2a3330"
  active-tab: "#17231c"
  dark-on-accent: "#071006"
typography:
  display:
    fontFamily: '"IBM Plex Sans", "Helvetica Neue", sans-serif'
    fontSize: "clamp(40px, 4.3vw, 60px)"
    fontWeight: 500
    lineHeight: 1.2
    letterSpacing: "-0.035em"
  headline:
    fontFamily: '"IBM Plex Sans", "Helvetica Neue", sans-serif'
    fontSize: "26px"
    fontWeight: 600
    lineHeight: 1.2
    letterSpacing: "-0.02em"
  body:
    fontFamily: '"IBM Plex Sans", "Helvetica Neue", sans-serif'
    fontSize: "16px"
    fontWeight: 400
    lineHeight: 1.5
  control:
    fontFamily: '"IBM Plex Sans", "Helvetica Neue", sans-serif'
    fontSize: "13px"
    fontWeight: 600
    lineHeight: 1
    letterSpacing: "0.02em"
  telemetry:
    fontFamily: '"IBM Plex Mono", ui-monospace, monospace'
    fontSize: "10px"
    fontWeight: 500
    lineHeight: 1.2
    letterSpacing: "0.08em"
rounded:
  square: "0px"
  signal: "50%"
spacing:
  xxs: "4px"
  xs: "8px"
  sm: "12px"
  md: "16px"
  lg: "24px"
  xl: "30px"
components:
  button-primary:
    backgroundColor: "{colors.phosphor}"
    textColor: "{colors.dark-on-accent}"
    typography: "{typography.control}"
    rounded: "{rounded.square}"
    padding: "10px 12px"
    height: "44px"
  button-secondary:
    backgroundColor: "{colors.surface-raised}"
    textColor: "{colors.ink-control}"
    typography: "{typography.control}"
    rounded: "{rounded.square}"
    padding: "10px 12px"
    height: "44px"
  field:
    backgroundColor: "{colors.surface-raised}"
    textColor: "{colors.ink}"
    typography: "{typography.telemetry}"
    rounded: "{rounded.square}"
    padding: "7px 30px 7px 9px"
    height: "44px"
  tab-active:
    backgroundColor: "{colors.active-tab}"
    textColor: "{colors.phosphor}"
    typography: "{typography.telemetry}"
    rounded: "{rounded.square}"
    padding: "12px 8px"
    height: "46px"
---

# Design System: Prediction Sandbox

## Overview

**Creative North Star: "The Voxel Reconnaissance Table"**

Prediction Sandbox is an original tactical/industrial research instrument. The dataset is the world: a bounded terrain to inspect, select, and audit, while the surrounding interface behaves like a matte command shell. Block-world references appear through extruded, data-generated geometry and crisp compartmentalization—not scenery, ornament, or playful simulation tropes.

This is an **Operate** surface. Dense information is welcome when it improves comparison and provenance, but every screen must make the evidence boundary, current scope, available actions, and unavailable claims immediately legible. Visual drama belongs to the terrain; controls and evidence remain restrained.

**Key Characteristics:**

- Matte near-black green surfaces, hairline compartments, square controls, and phosphor telemetry.
- Wide editorial headings paired with compact monospaced labels and tabular data.
- Official boundaries rendered as low-poly extrusions whose height and color encode declared data state.
- Explicit language for what is validated, source-only, comparison-only, missing, or blocked.
- A list/index equivalent for every map selection path.

**The Evidence Is the Interface Rule.** Provenance, cutoff, validation state, and cost limits are primary UI, never footnotes hidden behind visual spectacle.

## Colors

The palette is a low-luminance field of green-black surfaces with one high-energy phosphor accent. Olive and slate terrain colors communicate data classes; amber directs focus and caution; red is reserved for exceptions and failed or incomplete states.

### Operational roles

- **Phosphor:** selected terrain, primary action fills, active navigation, live indicators, and short system identifiers. Its rarity creates authority.
- **Focus amber:** the universal focus outline and caution/next-state emphasis. It must remain distinguishable from selected phosphor.
- **Exception red:** errors, unavailable materializations, and incomplete source states. Never use it decoratively.
- **Ink and muted text:** high-contrast reading text versus supporting explanations, timestamps, and field labels.
- **Void, shell, and surfaces:** adjacent tones establish hierarchy without floating cards or ornamental gradients.

### Map semantics

- **Validated terrain:** a validated population profile exists; runnable status still appears in adjacent text.
- **Comparison terrain:** the selected display/evaluation layer covers the feature; this does not imply a population profile.
- **Source terrain:** a source pack exists, but the population profile is not built.
- **Missing terrain:** boundary-only or unmaterialized profile state.
- **Selected terrain:** overrides the class color with phosphor while the inspector preserves the underlying truth in words.

**The Semantic Pairing Rule.** Never communicate state with color or extrusion alone. Pair every swatch with a legend label and every selection with a status badge, summary, and factual readout.

**The Runtime Boundary Rule.** Comparison-layer styling must stay visually and verbally distinct from evidence available to agents.

## Typography

**Display and body:** IBM Plex Sans with Helvetica Neue and system sans fallbacks.

**Telemetry and data:** IBM Plex Mono with a system monospace fallback.

Plex Sans gives the workbench a sober editorial voice; Plex Mono marks machine state, IDs, dates, counts, controls, and provenance. Large headings are broad and calm, while uppercase mono labels are small, tracked, and economical.

### Hierarchy

- **World display:** medium weight with tight tracking; use once per major world surface. On desktop it scales fluidly, and on small screens it resolves to a fixed 38px.
- **Section headline:** semibold, usually 23–39px for major operational regions and 26px for standard view headings.
- **Body:** 16px/1.5 for general reading; dense inspectors may use 11–14px only when labels and contrast remain clear. Explanatory lines typically stop at 62–76 characters.
- **Telemetry:** 8–12px mono, uppercase, tracked, and never used for long prose.
- **Numeric readouts:** mono with tabular numerals; put units and qualifiers in the value, not only in a nearby legend.

**The Two-Voice Rule.** Sans explains; mono identifies, measures, and reports system state. Do not introduce decorative display faces.

## Layout

The desktop shell is a centered, nearly full-width command frame (`min(1580px, calc(100% - 40px))`). Its masthead is a three-compartment grid for identity, frozen-world metadata, and run controls, followed by a sticky, horizontally scrollable ten-tab rail. Main content uses borders and shared edges rather than nested floating cards.

The World Model leads with a two-column title band, then a collapsible population audit and the dominant geography workspace. The workspace sequence is fixed: operational heading, six-cell control bar, breadcrumb/level rail, then a split stage. On wide screens the terrain owns roughly 70% of the split (`1.75fr / 0.72fr`), with a 640px map inside a minimum 700px stage; the inspector remains at least 360px wide.

Spacing is compact and systematic: 8–16px inside controls and telemetry, 18–24px inside panels, and about 30px between major evidence sections. Borders align across neighboring compartments. Avoid gratuitous wrappers that create cards inside cards.

### Responsive behavior

- **At 1180px and below:** the masthead becomes two columns with run controls on a full second row; the geography toolbar becomes three columns.
- **At 900px and below:** outer gutters become 10px, headings stack, and terrain stacks above the inspector. The terrain remains prominent at 540px high.
- **At 620px and below:** fields become one column, the Terrain/Index switch spans the width, the map becomes 430px high, camera controls move to the lower right, and index cells use two columns. The masthead is compacted; nonessential lede and run controls yield to world navigation.
- Navigation may scroll horizontally; evidence tables and long indexes use deliberate internal overflow. Do not force the entire page sideways.
- Interactive targets remain at least 44px high wherever a compact data control is not an icon-only 42px map control.

## Elevation & Depth

The shell is flat by default: no ambient card shadows and no floating glass layers. Hierarchy comes from tonal surface changes and 1px dividers. The translucent map telemetry plate may use a small blur because it overlays live geometry; it is an instrument overlay, not a general card style.

The terrain is the system's signature depth. Official polygon shapes are extruded without bevels, rendered with flat shading, dark sides, hard boundary edges, a gridded floor, restrained fog, and directional light. Height is normalized data or coverage state—not decorative topography. Selection may add a restrained emissive phosphor edge.

**The One Source of Depth Rule.** Keep interface chrome planar so the data terrain remains the unmistakable spatial focus.

## Shapes

Controls, panels, badges, tables, and navigation use square corners. Compartments are rectangular, aligned, and bounded by thin strokes. Circular geometry is reserved for tiny online/offline signal lights; it is not a container language.

Map silhouettes come from the registered geography, including their irregular outlines and holes. Extrusions have no bevel and one segment/step, preserving a faceted, surveyed quality. Never substitute generic hex maps, smooth blobs, or decorative land masses for official boundaries.

## Components

### Command header and tabs

- The header binds product identity, world clock, evaluation horizon, active cell, run selection, and run state into one continuous frame.
- Tabs are uppercase mono compartments. The active tab uses a phosphor label, a dark-green fill, and a 2px phosphor baseline; hover and focus remain visually distinct.
- Implement WAI-ARIA tabs with roving focus and Arrow, Home, and End navigation.

### Fields, buttons, and switches

- Fields use a dark solid fill, 1–2px green-gray border, square shape, compact mono value text on the World Model, and an explicit uppercase label above.
- Primary buttons are phosphor with dark text. Secondary actions are dark and outlined. Disabled actions lose emphasis, keep readable text, and explain why they are blocked.
- Two-way switches share a border; the pressed option becomes a filled phosphor cell. Do not use pill toggles.
- Focus uses the 3px amber outline with a 2px offset. Active press movement is at most 1px.

### Geography workspace

- **Toolbar:** boundary, dataset family, primary layer, comparison layer, terrain encoding, and Terrain/Index mode appear before the map so the encoding is inspectable.
- **Breadcrumb rail:** always reports national/state/sub-state context and a compact level code such as `L01 · STATE`.
- **Terrain:** supports rotate/pan, hover tooltip, click selection, zoom in/out, and camera reset. A telemetry plaque identifies source agency, vintage, and selectable-cell count.
- **Index fallback:** exposes the same states and subareas as real buttons with the same status language. It is the keyboard and WebGL fallback, not a lesser visualization.
- **Inspector:** names the geography level and selection, shows a text status, factual measures, data-layer coverage, source adapter state, demographic distributions when validated, and representative-swarm configuration.
- **Empty/loading:** the animated scan bar is used only while geometry materializes. Empty and error states name what is absent and explicitly avoid implying demographic availability.

### Truth and cost guardrails

- Keep boundary materialization, source readiness, comparison coverage, profile validation, and runnable status as separate rows or labels. A selectable boundary is not automatically swarm-ready.
- State that comparison layers are display/evaluation metadata with runtime access off wherever their coverage is summarized.
- The cost envelope is a compact 2×2 fact grid: paid mode, paid-agent cap, run ceiling, and conservative request/cost ceiling with status.
- Disable swarm configuration unless the selected profile is validated and runnable and the chosen size passes local caps. Present the blocking reason in text; do not rely on dimming alone.
- Present representative panels as weighted/compressed simulation units and keep disclosure copy adjacent to the controls.

### Motion and accessibility

- Terrain meshes materialize from near-flat to their target depth and camera damping makes direct manipulation feel measured. Animate only while the document is visible and the map intersects the viewport.
- Respect `prefers-reduced-motion`: remove CSS transitions/animations, disable damping, and render terrain immediately at its settled depth.
- Keep the WebGL canvas hidden from assistive technology and label its enclosing region. Preserve skip links, visible focus, `aria-live` status, semantic tables, labeled groups, and the full Index alternative.
- Status labels, legends, text summaries, and controls must remain understandable without color, motion, hover, or WebGL.

## Do's and Don'ts

### Do:

- **Do** let data state drive visual state: geometry, height, color, labels, and inspector facts must agree.
- **Do** lead with the terrain on the World Model while keeping provenance and control labels immediately visible.
- **Do** use short, plain-language disclosures next to technical readouts.
- **Do** keep primary actions rare, square, and unmistakably phosphor.
- **Do** preserve keyboard-equivalent selection, reduced-motion behavior, and text status for every map state.
- **Do** show conservative caps before an action can incur paid traffic.

### Don't:

- **Don't** turn the product into a decorative game scene, illustrated control room, or nostalgic pixel-art interface; the generated dataset is the visual world.
- **Don't** add rounded cards, pill controls, soft drop shadows, glossy gradients, or generic dashboard widgets.
- **Don't** use phosphor, amber, or red as decoration; each color carries operational meaning.
- **Don't** imply that geometry, registered sources, or comparison coverage constitutes a validated or runnable population.
- **Don't** hide missing, partial, blocked, or runtime-inaccessible states behind optimistic copy.
- **Don't** add geographic scope, demographic claims, or data equivalence that the active registry does not support.
