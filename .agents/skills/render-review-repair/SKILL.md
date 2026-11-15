---
name: render-review-repair
description: Inspect actual ChiNext rendered frames and media, compare the approved poster and motion reference, and repair defects with traceable evidence.
---

# Render review and repair

Use after any material visual/timing change, before the sample review, and before full-film delivery. Read the production specification and run the data/time skill first. This skill requires inspection of actual output; code inspection or a green test suite alone is insufficient.

## Prepare the review pack

Run from the repository root:

```bash
python render_v6.py --keyframes --output-dir output/v6_review
python render_v6.py --video --output-dir output/v6_review
python tools/validate_project.py --config config/v6_sample.json --events config/events_v6.json --output output/v6_review/validation.json --video output/v6_review/chinext_v6_sample.mp4 --layout
```

Use a separate directory for reduced-resolution drafts. Inspect target-resolution files before final review. Contact sheets help cover the timeline, but cannot prove temporal quality; inspect transitions and consecutive frames as well as key stills, and play the actual video when supported.

## Compare concrete visual behavior

Open `assets/reference/approved_visual_reference.png` and actual output side by side. Compare title hierarchy, candle clarity, negative space, chart/earth proportions, atmospheric edge and city detail, gold critical-point emphasis, red orbit integration, and restrained use of light. The poster's stylized chart and obsolete statistics are not allowed to overwrite true OHLC or the single-active-rail rule.

Check at a phone-like display size. Main text must be readable without pausing; count stable reading time from fully visible text to the start of exit, not from the first translucent pixel. The 0.6-second final-number hold is not permission to show a two-line event for only 0.6 seconds.

Against the NASDAQ-100 motion reference, check continuous market progression, motivated changes of scale, deceleration before an extremum, a visible synchronized hit, adequate reading holds, and real volatility after the high. Do not mechanically pop up a card every 1.5 seconds: the rule flags purposeless mechanical movement while allowing intentional breathing space.

The current delivery is silent. Check that the MP4 has no accidental audio stream; do not add a music selection task. Before final delivery also check complete frame count/duration, target dimensions/fps, black or frozen frames, clipping, text overlap, missing glyphs and segment joins. Declared FFmpeg success is only encoding evidence.

## Internal repair loop

1. Record a specific issue with version, timecode/frame, scene ID, screenshot or diagnostic, expected versus actual behavior and severity.
2. Find the responsible shared layer or configuration. Repair the common cause rather than copying a patch into many scenes.
3. Re-render the affected frames/scene. Rerun the relevant fact/time/layout checks.
4. Inspect the new output and compare it with the previous evidence and benchmark. Recheck surrounding transitions and, after assembly, the complete media.
5. Continue internal correction while there is a clear diagnosis. If two visual iterations make no material progress, present a concrete before/after comparison and one recommended choice at the concentrated sample review. Missing required source material or an unavailable execution capability must be reported precisely.

## Release gates and reporting

Blocking defects include wrong facts/dates, an unqualified event being displayed, invented OHLC, missing/illegible key text, hidden critical K, broken stage logic and corrupt/incomplete export. These prevent a formal candidate. Pacing/focus/benchmark-quality problems require visual repair, even if automatic checks pass. Cosmetic opportunities remain separately recorded and must not mask blocking defects with a high average score.

Keep automatic check results, agent visual findings and user aesthetic acceptance separate. Never claim “at least as good as the poster” from file resolution, a similarity score or a successful render. Report exactly what was inspected and any unperformed viewing checks. Deliver the sample for the agreed human visual checkpoint before batch-producing the entire film.
