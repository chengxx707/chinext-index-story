---
name: data-time-consistency
description: Validate ChiNext facts, event qualification and deterministic frame-to-market-time consistency before rendering or extending scenes.
---

# Data and time consistency

Use whenever changing data loading, event configuration, timeline keyframes, camera shots, stage state, on-screen numbers, or the final endpoint. Read the production specification and event audit first.

## Fact rules

- One frozen `data/cyb_daily.csv` supplies all OHLC. Check required columns, ascending unique dates, finite positive prices, and `low <= min(open, close) <= max(open, close) <= high`.
- A display labeled as a daily close must equal that trading day's true close. Do not mix a floored date with a visually interpolated next-day close.
- Prices are 2 decimals. Percentage labels have a signed 2-decimal value derived from a declared numerator and denominator. State official base-1,000 return separately from first-observed-close return.
- Use actual daily OHLC for candles; never stretch a selected candle independently. The base date 2010-05-31 has no input OHLC; render a base marker, not a fabricated candle.
- 2015-06-03 3,982.25 is a stage high. 2026-06-25 4,371.99 is the full-sample highest close. Intraday highs are separate facts.
- July 2026 standard monthly return uses June 30 close, not July 1 close. Keep an explicit interval label if showing the latter calculation.
- Current member counts, industry groups and total market caps carry the 2026-11-10 snapshot label. Total market capitalization is not index weight.

## Event qualification

Look up stable event IDs in `config/event_registry.json`. A-grade supplied documentary verification and new online verification are separate fields. Do not invent source URLs or claim a new online check from the former. B/C records remain disabled until supported primary evidence is recorded and the grade explicitly updated.

Keep `day`, `month`, `year` and `range` precision separate from trading-day observation anchors. Exact day events use strict date lookup. A non-trading-day event must retain its actual date with an explicitly chosen observation day if necessary; never use a nearest-date fallback that changes the historical event. Month/range events must retain their precision on screen.

The latest user review permits brief sourced market context and emotion descriptions. Record whether a statement is an observable fact, a possible mechanism or contemporary sentiment, and give evidence/attribution accordingly. Unverified research hypotheses do not become certain on-screen causes; no fabricated sentiment index or universal claim about all investors. Keep an announcement date/time separate from implementation and price reaction; a later event cannot explain an earlier peak. Stock-return stories remain outside scope. The April 20–24 value 413.03万户 is new A-share accounts over a week, not unique people or a single-day figure.

## Timeline rules

One playhead generates date, exact market state, event activation, candle anchor, orbit node, and stage state. A separately hand-filled event time must be diagnosed against that playhead before rendering.

Check the first frame, last valid frame and every event/critical boundary. The endpoint must be reached inside `0 .. frame_count - 1`; an event at the excluded duration boundary is not displayed. Event text, current date, current close and the referenced K must agree at the intended hit frame.

Exactly one full stage rail is active. A rise rail follows actual pullbacks backward, not elapsed time. Stage changes occur once, after the agreed high/low hold, while completed stages become small milestones. Camera windows change scale without changing real price proportions; reading holds keep a stable vertical range.

## Checks and evidence

From the repository root:

```bash
pytest -q
python tools/validate_project.py --config config/v6_sample.json --events config/events_v6.json --output output/v6_review/validation.json
```

When layout and the target video exist, run:

```bash
python tools/validate_project.py --config config/v6_sample.json --events config/events_v6.json --output output/v6_review/validation.json --video output/v6_review/chinext_v6_sample.mp4 --layout
```

Preserve the real command exit status and inspect current-run report content. A zero-test run, skipped check, absent video or stale report is not a pass. Fix the responsible data/model/config layer, rerun the affected checks, and record any unresolved failure before rendering the formal candidate.
