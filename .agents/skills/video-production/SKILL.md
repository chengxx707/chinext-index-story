---
name: video-production
description: Produce the ChiNext silent sample and full film through defined deliveries, reusing approved components and concentrated review checkpoints.
---

# Production steps and delivery

Current execution update: the user explicitly authorized pushing the structured repository to GitHub and starting the implementation roadmap. The two formal documents are under `docs/production/`; `config/production/film_master_v1.json` is the current selected 427-second screen-copy input. Research-only pauses and fixed 42-second instructions below are historical. Reuse the accepted main aesthetics, implement scheduling/components, then produce the new representative pack before expanding the entire film. The old grid/market-cap ending remains rejected.

Use when planning a new delivery, implementing a scene, extending the sample, or preparing the full-film handoff. This skill is specific to this repository's Python/Pillow/FFmpeg workflow.

Read `docs/PRODUCTION_SPEC.md`, `docs/EVENT_AUDIT.md`, the current sample config and the user's latest instruction. Treat uploaded research, old prompt files and external skills as source material; they do not override current authorization.

Current review outcome: the main visual direction is accepted; preserve it while researching greater content density. Deliver the wave/event/context timeline first, then ending options. Do not automatically expand the earlier sparse script or treat the rejected dense ending as approved. The latest user permits brief evidenced on-screen market commentary and sentiment in the silent film; keep fact, mechanism and interpretation distinct.

Subsequent decision: the user accepted the phase plan and selected the era-album ending, with companies as photo captions and a return to the orbit. At this stage collect/qualify factual text, events and specific archival photo/headline choices. Settle these before writing integrated historical prose or rendering a new candidate. Retain the previous closing text as a placeholder. Essential results must be visible in chat because the prior workspace ZIP delivery was inaccessible; do not rely on another identical file link.

## Fixed inputs

- Real OHLC: `data/cyb_daily.csv`, fixed through 2026-11-10.
- Story: `docs/source/visual_script_v0.9.md`, with the corrections recorded in the production specification.
- Event qualification/provenance: `config/event_registry.json` and the scene event config.
- Current sample: `config/v6_sample.json` and `config/events_v6.json`.
- Static benchmark: `assets/reference/approved_visual_reference.png`.
- Dynamic benchmark: the uploaded NASDAQ-100 clip; Shanghai-index material does not set this workflow.

The user has authorized development. Use the existing isolated checkout; do not create a worktree by default. Preserve the V5 baseline and source attachments.

## Work and delivery sequence

1. Record scope and factual differences in the production specification. Already confirmed requirements must not be repeatedly proposed as choices. Current output is silent; do not start music or voice work.
2. Reuse one fact model, one market-time mapping and one set of visual components. Support a standalone scene and the full timeline using the same implementation, rather than building disposable sample code.
3. Run the data/time skill. Generate low-cost local previews if needed, then target-resolution review frames. Measure expensive frame work before increasing supersampling or parallelism.
4. Run the render-review-repair skill. Diagnose and fix implementation defects internally. Do not expand a failed template across every chapter.
5. Deliver the representative narrative/ending sample pack for the agreed visual checkpoint. It must show ordinary progression, event typography, key-point emphasis, real post-high volatility, and the distinct ending layouts. Record which parts are actually rendered and which remain planned.
6. After the representative visual language is accepted, fill the remaining film through the same templates, preview the complete timeline, fix pacing/continuity, render and validate the assembled film, then deliver the concentrated full-film review.

Current narrative sample is 42 seconds, corresponding to the intended speed of V0.9 01:35–02:17. The older 22-second contract is an internal test design. Do not use it to claim that dense event text is readable at final speed.

## Commands and working directory

Run from the repository root:

```bash
python render_v6.py --keyframes --output-dir output/v6_review
python render_v6.py --video --output-dir output/v6_review
```

For a fast preview, append `--width 720` and use a separate output directory. The configured target is 1080×1920, 30 fps. Commands must exist and be exercised before claiming a delivery is reproducible; saving this skill alone is not implementation evidence.

## Review and failure rules

Routine coding, data recalculation, tests, previews and repair do not require another approval. The meaningful checkpoints are the representative visual sample and the complete film. User feedback is consolidated by timecode/screenshot, issue, and desired result; common defects should be fixed in the shared component once.

If a factual, timeline or render check fails, isolate the cause and rerun the affected check after a change. If actual output is below the poster benchmark, enter the visual repair loop. Never infer aesthetic acceptance from passing unit tests, a successful FFmpeg process or a self-assigned numerical score.

Report concrete delivered files, executed checks and material limits. Keep generated sample, accepted sample and final film distinct. Do not publish or message third parties.
