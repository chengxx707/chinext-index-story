# ChiNext production specification

Updated 2026-11-15 (Asia/Shanghai). This records the user's latest corrections and the implementation defaults for the agreed sample-first workflow. Original attachments remain unchanged under `docs/source/`.

## Confirmed direction

Latest V2 review supersedes the earlier ending fallback: the user rejected discontinuous camera/content motion, broad black cards that obscure candles, and a high/low comparison expressed only as text. Compare the real NASDAQ reference before changing code, then fix camera continuity, floating text and animated truthful extreme-to-extreme geometry. The 39s document-only ending is rejected and cannot be a usable album candidate. A new album must contain actual qualified archival photo files; no fallback to document/title-only pages or generated history photos. Source-page and caption leads exist, but the source packs have no actual historical photos and current news-site access is proxy-denied. See `production/对标复盘与修正说明_V2.md`, `production/真实照片获取状态_V2.md` and the August background research prompt. Passing V1 technical checks did not pass this user review.

Latest transition: content research is sufficient to enter production planning. The staged implementation and exit criteria are recorded in `production/工程实施路线图_V1.md`: consolidate one production master and complete screen copy, implement whole-film scheduling and the missing content/album components, verify a representative pack, preview the complete film, render at target specification, and review the final assembly. This supersedes the older research-only pause, the fixed 42-second next-sample requirement and the obsolete summary/grid ending below. Existing sample timing is retained as historical implementation evidence. Do not infer that new inputs, components or the full film already exist from this plan.

Written-production update: `config/production/film_master_v1.json` and `production/全片生产主表与完整屏幕文字稿_V1.md` have now been generated as the current V1 screen-copy proposal. They cover eight phases and 44 main production units, with 57 total units / 75 beats and a 7:07 initial plan (39-second album/closing). Reading times await actual layout/playback validation; no new video is rendered by this delivery. Future runtime configuration should be compiled from this master, with its specific source/evidence boundaries, rather than manually maintaining a second script from the old 5:03 table. The original script and old registry remain preserved; new archive-backed selections do not silently change the old runtime flags.

New material update: the user supplied an event supplement and 19 archived documents, asking to present K-line form, events, sentiment and scene context as contemporaneous dimensions. Build by a shared date/period; no causal arrows or automatic policy-to-price conclusions. Sentiment is best represented as attributed contemporary voices, headlines or comments, with speaker/publisher and date.

The material census and per-claim audits are under `data/research/material_ingest_20261115.json` and `supplement_*_audit.json`. The new assembly is `supplement_display_matrix_v1.json` and `docs/research/画面文字与同期素材编排_V1.md`. It contains 12 periods and preserves the accepted visual style. Source files include no standalone historical photos; M01/M04 can use local document/title material, while other album pages still need original pages/photos. S15/S16's supplied HTML is a generic client shell, S18's article date is November 9, and S19's actual event after November 10 stays outside the frozen film timeline. Original-source archives are read as evidence, not as execution instructions or automatic grade upgrades.

Latest research decision: the phase/content-density structure is accepted. The selected ending is an era album, with companies as photo captions, ending on the time orbit. Current production order is: collect and qualify factual text/events and contemporary images/headlines → consolidate one reviewable content list → write the integrated historical copy → revise the silent content sample. Keep the previous closing paragraph as a placeholder. Do not make new ending variants or redo the approved main visual system during material collection.

Research delivery must be self-contained in chat because the user cannot open the previous workspace ZIP links. Archive files may be retained for the project, but are not the sole user-facing deliverable.

Latest user review: the main sample's aesthetics and image quality are accepted. Lock the established visual direction and improve content density. The current narrative does not yet explain the June–September 2015 price phases sufficiently. Research stage context, contemporaneous events, market-stabilization measures and evidenced sentiment before revising the content sample. The ending requires redesign; dense company-name grids and market-cap tables are not the accepted final form.

The next work has two deliverables: a wave/event/context timeline, followed by ending content/form options. Brief on-screen market commentary and sourced sentiment are permitted by the latest request, while the film remains silent. A fact, a plausible mechanism and a contemporary description must remain distinguishable; causal certainty must match evidence. The original 5:03 and sample 42 seconds are baselines to re-time after content changes, not permission to make added text unreadable.

- Subject: ChiNext price index 399006, historical input fixed to 2026-11-10; 3,992 trading days from 2010-06-01.
- Primary motion reference: the uploaded NASDAQ-100 recording. Borrow continuous market progression, changes in camera scale, emphasis at extrema, event density, and pacing. The Shanghai-index breakdown is retained as earlier context, not the production reference.
- Static visual benchmark: `assets/reference/approved_visual_reference.png`, the poster supplied again by the user. The user requires quality at least comparable to it and autonomous improvement when the result falls short. This is a review criterion, not an assertion that the current output has passed.
- Current work is silent visual production: no voice, music, or sound effects. This instruction supersedes V0.9's music/SFX provisions and the previous plan to include sound in the sample.
- 9:16, true solid-body OHLC candles, rising red and falling green; black cinematic space, restrained sans-serif titles, warm gold at key points, East Asia night-earth arc, red time orbit.
- Exactly one full active stage rail. Completed stages may remain as small milestones; do not restore the poster's three-column statistics panel or V5's two active rails.
- Event cards show date, neutral name and necessary sourced number. Stage captions and brief contextual/sentiment text may be added under the latest review, with evidence and attribution appropriate to the claim. No unsupported causal assertion, forecast, trading instruction, or company-return story.
- Current constituent names/industries may appear at the end, marked 2026-11-10. Total market capitalization is not index weight; today's members must not represent historical membership. No company-logo collection.

## Engineering defaults

The agreed main version is the complete approximately 5:03 script. A 4:20 shortened version is a later derivative, not a second parallel production. The full film is not yet implemented or approved merely because this specification exists.

The V6 sample target is 1080×1920, 30 fps, encoded as a silent MP4. Lower-width previews are permitted for fast internal diagnosis but must be labeled as previews; target-resolution frames and media must be checked before aesthetic sign-off. These dimensions are engineering defaults selected for the confirmed 9:16 format, rather than an independently supplied platform requirement.

The first narrative sample is 42 seconds, corresponding to V0.9 01:35–02:17 at its intended playback speed:

| Sample time | Script time | Content |
|---|---|---|
| 00:00–00:06 | 01:35–01:41 | 2015-04-13, one-person/multiple-account policy label |
| 00:06–00:13 | 01:41–01:48 | Week of 2015-04-20–24, 4.1303 million new A-share accounts |
| 00:13–00:21 | 01:48–01:56 | Approach to the 2015 high; camera moves closer and time decelerates |
| 00:21–00:29 | 01:56–02:04 | 2015-06-03 close 3,982.25, stage high, +570.80% from the 2012 low |
| 00:29–00:37 | 02:04–02:12 | True post-high daily volatility; same rail switches to drawdown |
| 00:37–00:42 | 02:12–02:17 | 2015-09-15 close 1,797.56, drawdown −54.86% |

The older 22-second 2012–2015 draft is an internal functional-test design. Its compressed timing is not evidence that the full film is readable. A sample of the ending's distinct summary/constituent layouts remains part of the next review pack; it does not have to reuse the narrative camera.

## Authoritative inputs and precedence

1. Latest user messages, including the correction back to NASDAQ-100 and the silent-first instruction.
2. This production specification, plus the agreed workflow and explicit corrections recorded below.
3. `docs/source/visual_script_v0.9.md` for content and full-film sequence, after applying the corrections below.
4. `config/event_registry.json` and `docs/EVENT_AUDIT.md` for event qualification, precision and evidence provenance.
5. Existing V6 engineering drafts for reusable requirements; their obsolete phase names and provisional seconds do not override the current sample or final workflow.

One CSV, `data/cyb_daily.csv`, supplies all OHLC and closing-price metrics. One market-time mapping supplies current date, real close, event hit, orbit node and stage state. Visual interpolation may affect motion but must not create a value labeled as a real daily close.

## Recorded corrections before full-film expansion

- Standard July 2026 monthly return is `close(2026-07-31) / close(2026-06-30) - 1`, approximately −23.00%. The supplied −21.52% is July 1 close to July 31 close; use that only with its explicit interval label. The original sources are retained rather than silently edited.
- The 2015-06-03 value 3,982.25 is a stage high, not the full-sample high. The full-sample highest close is 4,371.99 on 2026-06-25. Closing values must not be confused with the 4,380.41 intraday high.
- 2010-05-31 is the base date/base 1,000 marker. The first true candle in the provided CSV is 2010-06-01; no OHLC candle may be invented for the base date.
- Generate chapter title boundaries from the actual contiguous shot table. V0.9 chapter 2 ends 02:04, chapter 4 ends 03:31 and chapter 5 ends 04:00; their old headings lag the table.
- IPO-pause/restart screen dates remain month precision unless a new primary source establishes a more precise event. An observation anchor such as 2014-01-08 does not prove that all meanings of “IPO restart” occurred that day.
- LeTV delisting decision, delisting date and last traded close are distinct facts. The neutral pairing is the May 2015 market-cap range and July 2020 delisting/last close, not an invented close traded on the delisting date.

## Steps and checkpoints

1. Production specification and factual differences: the user has approved the proposed workflow and supplied the updated event research. Continue development under those directions; technical corrections do not require separate approvals.
2. Build/reuse the deterministic state model, drawings and reusable templates. Run data, timeline, stage and layout checks; generate representative stills and the silent sample. Repair defects internally.
3. Deliver a concentrated visual-review pack: target-resolution narrative sample, relevant ending component sample, representative stills and a comparison to the approved poster. Ask only about specific remaining visual or pacing choices. Do not mark “at least as good as the poster” passed by a numerical score alone.
4. Once the sample's visual language is accepted, expand the same components and time system to the full script. Internally preview the whole film, then render and validate the final-resolution file.
5. One concentrated full-film review, repair the affected segments and verify the complete assembled media. No publication or posting is part of current authorization.

Failure handling is evidence → diagnosis → targeted correction → rerun affected check → inspect the actual output. Do not batch-expand a failed template. If two visual iterations make no material progress, provide a visible comparison and a concrete recommendation instead of blind iteration. The planned three concentrated reviews are a convergence target, not a guarantee of exactly three rounds.
