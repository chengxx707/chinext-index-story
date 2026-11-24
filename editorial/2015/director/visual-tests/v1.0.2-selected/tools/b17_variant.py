"""B17 timing alternative for the delivered 48-cue V1.0.2 visual baseline."""

from copy import deepcopy
from hashlib import sha256
import json


_BASE_SHA256 = "14e4f698ea79ea96741cfb4f5562567931f0e4378db9905ebd0576d36e38add0"
# Each moving cue keeps the full sequence of real dates. Its terminal hold
# begins at the arrival offset, with the existing six-frame caption fade-in
# and six-frame fade-out intact. The ETF and turnover cues remain unchanged
# in length and stay on their completed closing rows.
_TIMING = (
    ("V102-B17-01", 5880, 5949, 8),
    ("V102-B17-02", 5949, 6024, 17),
    ("V102-B17-03", 6024, 6114, 20),
    ("V102-B17-ETF", 6114, 6264, 0),
    ("V102-B17-04", 6264, 6348, 12),
    ("V102-B17-TURNOVER", 6348, 6462, 0),
    ("V102-B17-05", 6462, 6540, 8),
)


def _retime_cue(cue: dict, start: int, stop: int, arrival: int, fps: int) -> None:
    old_start = cue["start_frame"]
    old_stop = cue["end_frame_exclusive"]
    old_hit = cue["primary_anchor"]["hit_frame"]
    hit = start + arrival
    hit_shift = hit - old_hit
    end_shift = stop - old_stop

    keys = cue["market_clock"]["keyframes"]
    days = list(dict.fromkeys(key["date"] for key in keys))
    if len(days) == 1:
        keys = [{"frame_offset": 0, "date": days[0]}]
    else:
        keys = [
            {"frame_offset": round(i * arrival / (len(days) - 1)), "date": day}
            for i, day in enumerate(days)
        ]
    keys.append({"frame_offset": stop - start - 1, "date": days[-1]})
    if any(a["frame_offset"] >= b["frame_offset"] for a, b in zip(keys, keys[1:])):
        raise ValueError(f"Treatment B cannot fit every trading row of {cue['shot_id']}.")
    cue.update(start_frame=start, end_frame_exclusive=stop)
    cue["market_clock"]["keyframes"] = keys
    cue["primary_anchor"]["hit_frame"] = hit
    cue["earth_orbit"]["hit_frame"] += hit_shift

    event = cue["event_clock"]
    if event is not None:
        event["activation_frame"] += hit_shift
    for reference in cue["event_refs"]:
        if reference is not event:
            reference["activation_frame"] += hit_shift

    text = cue["text_cue"]
    old_in = text["in_frame"]
    text["in_frame"] += hit_shift
    text["full_alpha_from_frame"] += hit_shift
    text["out_frame_exclusive"] = stop
    story = cue["camera_story_clock"]
    bounds = {old_start: start, old_in: text["in_frame"], old_stop: stop}
    for window in story["focus_windows"]:
        window["start_frame"] = bounds[window["start_frame"]]
        window["end_frame_exclusive"] = bounds[window["end_frame_exclusive"]]
    reading_start, reading_stop = story["reading_window"]
    reading_start += hit_shift
    reading_stop += end_shift
    story["reading_window"] = [reading_start, reading_stop]
    story["exit_window"] = [frame + end_shift for frame in story["exit_window"]]
    story["focus_exit_frame"] += end_shift
    text["stable_reading_seconds"] = (reading_stop - reading_start) / fps


def make_b17_b(base: dict) -> dict:
    """Return treatment B with only B17's internal timings changed."""
    raw = json.dumps(base, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    if sha256(raw).hexdigest() != _BASE_SHA256:
        raise ValueError("B17 A/B requires the exact delivered b0d71e8 48-cue candidate.")
    candidate = deepcopy(base)
    cues = [cue for cue in candidate["cues"] if cue["beat_id"] == "B17"]
    first_reveal = {}
    for cue, (shot_id, start, stop, arrival) in zip(cues, _TIMING, strict=True):
        if cue["shot_id"] != shot_id:
            raise ValueError(f"Unexpected B17 cue before retiming: {cue['shot_id']}.")
        _retime_cue(cue, start, stop, arrival, candidate["fps"])
        for key in cue["market_clock"]["keyframes"]:
            first_reveal.setdefault(key["date"], start + key["frame_offset"])
    beat = next(item for item in candidate["beat_ranges"] if item["id"] == "B17")
    checkpoints = [beat["primary_anchor"], *beat["secondary_anchors"], *beat["verified_price_checkpoints"]]
    for checkpoint in checkpoints:
        checkpoint["hit_frame"] = first_reveal[checkpoint["date"]]
    return candidate
