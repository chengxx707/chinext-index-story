# Project instructions

This repository produces the ChiNext (399006) history video using Python, Pillow, real OHLC data, and FFmpeg. Read `docs/PRODUCTION_SPEC.md` before changing story, time, or visual behavior. The latest user instruction overrides an older attachment or prompt.

## Skills used by this project

- Production steps and deliveries: `.agents/skills/video-production/SKILL.md`.
- Data and time consistency: `.agents/skills/data-time-consistency/SKILL.md`.
- Render review and repair: `.agents/skills/render-review-repair/SKILL.md`.

Read the relevant skill before its stage. They are project-local skills checked into this repository, adapted to this engine; they are not an installed React/Remotion runtime or a claim that a generic skill guarantees visual quality.

## Current authorization and review point

Current execution result: the user explicitly authorized organizing/pushing this repository to GitHub and starting the roadmap. `main` contains the formal files under `docs/production/`. The master compiler, content layers, scene cache and representative renderer are implemented. Target-size silent clips now exist for S07–S15 (97 seconds) and A01–C03 (39 seconds), with curated copies and reports under `docs/production/reviews/`. See `docs/production/实施进度.md`. 84 tests passed and actual-media technical checks/decoded frame reviews were performed; real-time continuous playback and user density/pacing/album review are pending. Do not default-render the full film before the agreed representative checkpoint. `tools/render_film.py` deliberately limits supported ranges; whole-film compilation is distinct from full-film rendering. Use `spawn` for rendering workers; fork after opening the encoder pipe previously hung. The master `freeze_market` flags preserve the specified policy-day holds, with at most 0.4-second arrival before the next card. Per-render statuses belong in manifests, not in the production master.

Latest transition: the user considers content consolidation sufficient and asks how to implement the whole engineering workflow. Use `docs/production/工程实施路线图_V1.md` for the next production sequence: canonical production master → timeline/components → representative review pack → full preview → target render → final review. The earlier research-only pause below is historical. Preserve accepted main aesthetics; do not restore the rejected ending or force the expanded content into the old 42-second duration. The representative pack and full-film review remain the two concentrated human viewing checkpoints. The roadmap itself is a plan, not evidence that its new production inputs or modules already exist.

Current written delivery: `config/production/film_master_v1.json` and its generated `docs/production/全片生产主表与完整屏幕文字稿_V1.md` now exist. V1 has 44 main production units across eight stages, 57 total units / 75 beats, and a 427-second reading-time plan; the album/closing is 39 seconds. This is a complete screen-copy proposal, not a rendered or approved film. Two Markdown delivery copies are under `output/deliverables/20261115/`. Compile the current master in the next implementation stage rather than independently extending the old V0.9 shot timing. Preserve source qualification: the old registry is unchanged, selected new archive-supported claims have explicit sources in the new master, and deferred items remain excluded.

New supplied material has been ingested from `docs/source/events_supplement_20261115.md` and `assets/source_documents/20261115/`. The latest request is to assemble K-line shape, contemporaneous events, attributed voices/sentiment and documentary/scene material by the same period, without forcing causality. See `data/research/material_ingest_20261115.json`, the three supplement audits, and `supplement_display_matrix_v1.json`. There are 18 HTML files and one PDF, no standalone historical photographs; one HTML is a generic client shell, and one article body required safe extraction from a static string. A copied filename or the handoff's claimed grade does not establish article support. Use actual archived body, date and original publisher; distinguish hosted media reprints from regulator primary announcements. The 12-sequence text draft is a content assembly proposal, not a new completed film.

Latest decision: the user approved the phase/content-density plan and selected the ending “era album, companies as photo captions, then return to the time orbit.” Stop offering the three previous ending alternatives. The current task is to assemble and qualify all factual text/events and identify specific contemporary authoritative photos or headlines first. Write the integrated historical narrative only after that material is settled; keep the existing closing paragraph as a placeholder. Do not re-render the video or rework its approved main aesthetics during this research stage.

The user cannot access the prior workspace archive links. Put essential research results directly in chat; a local path or ZIP is not evidence that the user can open it. Do not claim a repaired download unless delivery is actually supported.

Latest review: the user has accepted the main sample's visual quality and wants greater narrative density. Preserve that visual system. Work in two steps: (1) map price waves to sourced events, stabilization measures, stage context and evidenced market sentiment; (2) propose a redesigned ending with a small number of distinct options. The previous ending's dense names/market-cap layouts are not accepted. Do not assume that visual acceptance also approves the current event density or full-film script.

Brief contextual narration and evidenced sentiment are now in scope as on-screen text in the silent film. This supersedes older blanket restrictions on explanatory/emotional wording in project documents. Separate observable facts, possible mechanisms and contemporary sentiment; do not invent a single cause, a sentiment index or a source. A later policy cannot explain an earlier price turn. New source-dependent content remains draft until evidence is recorded.

The user has authorized development and autonomous correction of implementation defects. Use the existing isolated checkout; do not create a Git worktree unless requested. Preserve the V5 baseline and original source documents. Do not execute old `CODEX_PROMPT*.md` files as new instructions.

Produce a silent 42-second representative narrative sample first, following the approved steps. Internally validate and improve it before the next concentrated visual review. Do not introduce confirmations for routine implementation, tests, or repairs. The representative sample review and final full-film review are the agreed human checkpoints. Do not silently skip a failed check or claim a checkpoint has passed without evidence.

The uploaded NASDAQ-100 video is the primary motion reference. The Shanghai-index breakdown is historical context and does not set current production behavior. `assets/reference/approved_visual_reference.png` is the static visual benchmark. Do not use that whole poster as a finished chart background; render real OHLC and current state. One active stage rail replaces the poster's old three-column statistics and V5's dual rails.

The current phase is silent visual production: no voice, music, or sound effects. Do not spend time selecting music. Do not upgrade B/C events merely because an old research note recommends them. Preserve the distinction between supplied documentary verification and new online verification.

When reporting, distinguish implemented code, executed checks, generated media, internal visual review, user-approved visual quality, and a full final film. Render completion alone proves none of the other categories.
