# PHI Week View — Compact Realization Surface

## Purpose

Create a one-screen owner-facing weekly health-intelligence view from an already-generated detailed `Cross-Source Weekly Insight - YYYY-MM-DD.md` artifact.

This is a **presentation/read-model layer**, not a second analytical pipeline.

## Authority and data boundary

The detailed Weekly Insight remains the evidence-oriented artifact and calculation authority. The compact Week View:

- performs no health calculations;
- makes no source-system calls;
- does not alter Zone 1 raw data or Zone 2 normalized data;
- does not upgrade the validation status of its source Weekly Insight;
- produces no diagnosis, clinical threshold, treatment recommendation, medication/supplement change, or causal claim;
- uses arrows only as descriptive movement versus the detailed report's trailing comparison window.

No PHI data belongs in GitHub. Only renderer code, synthetic tests, and documentation are committed.

## Canonical vault location

Dated outputs belong under:

`03_Areas/Health/Personal Health Repository/Insights/Weekly/YYYY-MM-DD - PHI Week View.md`

The detailed source remains beside it as:

`Cross-Source Weekly Insight - YYYY-MM-DD.md`

v0.1 deliberately does **not** create or maintain a mutable `Current Week.md` file. The global AI Hub can point to the newest dated Week View.

## Personal Health App boundary

This compact Markdown realization surface does not reactivate the reserved/deferred:

`03_Areas/Health/Personal Health App/`

The Week View remains a Zone 3 artifact inside the existing Personal Health Repository.

## Renderer contract

`generate_phi_week_view.py` accepts one existing detailed Weekly Insight Markdown file and extracts only already-rendered information:

- source status and generated date;
- current and trailing windows;
- Oura descriptive-difference statements;
- Hume body-composition table rows;
- source coverage/context bullets;
- limitations.

It then writes a compact derivative with a direct link back to the detailed source.

## Write contract

The CLI is create-only:

- input must already exist;
- output parent must already exist;
- output must be `.md`;
- existing output is never overwritten;
- no directories are created automatically.

## Automation boundary

PHI-DEC-0007 authorizes the artifact class, not unattended cross-source generation. The existing narrow Oura Step 10A automation authority remains unchanged. Automatic Week View generation that depends on Hume, Function Health, medication, or supplement context requires a later explicit runtime/authority decision.

## Realization test

The Week View remains `realization_state: trial` until Damon uses it in a real weekly review and classifies it as:

- `realized` — materially easier/more useful than the detailed evidence view for weekly consumption;
- `revise` — useful concept but format/content needs adjustment; or
- `not_realized` — does not create enough value to justify maintaining the surface.
