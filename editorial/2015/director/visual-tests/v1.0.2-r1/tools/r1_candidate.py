"""Derive an isolated visual R1 candidate from the delivered 48-cue V1.0.2 baseline."""

from copy import deepcopy
from hashlib import sha256
import json


BASE_COMMIT = "b0d71e895a7d756fa2ebbb7d8f3f471d581f1ccb"
BASE_CANDIDATE_SHA256 = "c9dfa6638885d55b712f0546f55df695b1f29c66a543c1733255bbd46084e86a"
BASE_CANONICAL_SHA256 = "14e4f698ea79ea96741cfb4f5562567931f0e4378db9905ebd0576d36e38add0"
B17_HOLD_EXTENSION = {
    "V102-B17-01": 12,
    "V102-B17-02": 12,
    "V102-B17-03": 24,
    "V102-B17-ETF": 18,
    "V102-B17-04": 24,
    "V102-B17-TURNOVER": 12,
    "V102-B17-05": 18,
}


def _intro(cue: dict, fps: int) -> None:
    start, stop = cue["start_frame"], cue["end_frame_exclusive"]
    story = cue["camera_story_clock"]
    settled = 48
    full = 54
    story["intro_camera"] = {
        "start_frame": start, "settled_frame": settled,
        "initial_visible_trading_days": 72, "initial_y_domain": [1000, 4800],
        "easing": "smoothstep",
    }
    story["intro_reveal"] = {
        "date_in_frame": start, "date_full_frame": 6,
        "value_in_frame": settled, "value_full_frame": full, "source_in_frame": settled,
    }
    story["focus_windows"] = [
        {"start_frame": start, "end_frame_exclusive": settled, "primary_focus": "L1_MARKET", "mode": "M1_MARKET"},
        {"start_frame": settled, "end_frame_exclusive": stop, "primary_focus": "L1_MARKET", "mode": "M2_KEY_POINT"},
    ]
    story["reading_window"] = [full, stop]
    cue["text_cue"].update(
        in_frame=settled, full_alpha_from_frame=full,
        stable_reading_seconds=(stop - full) / fps,
    )
    cue["earth_orbit"]["hit_frame"] = settled


def _move_hold(cue: dict, shift: int, extension: int, fps: int) -> None:
    """Move an existing cue and add time only after its last market-day arrival."""
    cue["start_frame"] += shift
    cue["end_frame_exclusive"] += shift + extension

    keys = cue["market_clock"]["keyframes"]
    if extension and keys[-1]["date"] != keys[-2]["date"]:
        raise ValueError(f"Cannot extend a cue without a terminal market hold: {cue['shot_id']}")
    keys[-1]["frame_offset"] += extension
    cue["primary_anchor"]["hit_frame"] += shift
    cue["earth_orbit"]["hit_frame"] += shift

    event = cue["event_clock"]
    if event is not None:
        event["activation_frame"] += shift
    for reference in cue["event_refs"]:
        if reference is not event:
            reference["activation_frame"] += shift
    text, story = cue["text_cue"], cue["camera_story_clock"]
    text["in_frame"] += shift
    text["full_alpha_from_frame"] += shift
    text["out_frame_exclusive"] += shift + extension
    windows = story["focus_windows"]
    for window in windows:
        window["start_frame"] += shift
        window["end_frame_exclusive"] += shift
    windows[-1]["end_frame_exclusive"] += extension

    # The existing release keeps only six frames for fade-out on B17. Extend
    # full reading without altering the duration of the dissolve.
    reading_start, reading_end = story["reading_window"]
    story["reading_window"] = [reading_start + shift, reading_end + shift + extension]
    story["focus_exit_frame"] += shift + extension
    if "exit_window" in story:
        story["exit_window"] = [frame + shift + extension for frame in story["exit_window"]]
    if extension:
        text["stable_reading_seconds"] = (reading_end - reading_start + extension) / fps


def _rebind_tail_checkpoints(candidate: dict) -> None:
    first_reveal = {}
    for cue in candidate["cues"]:
        if cue["beat_id"] in {"B17", "B18"}:
            for key in cue["market_clock"]["keyframes"]:
                first_reveal.setdefault(
                    (cue["beat_id"], key["date"]), cue["start_frame"] + key["frame_offset"],
                )
    for beat in candidate["beat_ranges"]:
        if beat["id"] in {"B17", "B18"}:
            checkpoints = [beat["primary_anchor"], *beat["secondary_anchors"], *beat["verified_price_checkpoints"]]
            for checkpoint in checkpoints:
                checkpoint["hit_frame"] = first_reveal[beat["id"], checkpoint["date"]]


def apply_r1_candidate(base: dict) -> dict:
    """Apply the approved intro, PMI context label and longer B17 readings."""
    encoded = json.dumps(base, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    if sha256(encoded).hexdigest() != BASE_CANONICAL_SHA256:
        raise ValueError("Visual R1 requires the delivered b0d71e8 48-cue baseline candidate.")
    candidate = deepcopy(base)
    fps = candidate["fps"]
    cues = {cue["shot_id"]: cue for cue in candidate["cues"]}
    _intro(cues["V102-B01-01"], fps)
    cues["V102-B13-02"]["camera_story_clock"]["context_label"] = "2015.08.21 · 当日回顾"

    shift = 0
    for cue in candidate["cues"]:
        if cue["beat_id"] == "B17":
            extension = B17_HOLD_EXTENSION[cue["shot_id"]]
            _move_hold(cue, shift, extension, fps)
            shift += extension
        elif cue["beat_id"] == "B18":
            _move_hold(cue, shift, 0, fps)
    for beat in candidate["beat_ranges"]:
        if beat["id"] == "B17":
            beat["end_frame_exclusive"] += shift
        elif beat["id"] == "B18":
            beat["start_frame"] += shift
            beat["end_frame_exclusive"] += shift
    candidate["frame_count"] += shift
    _rebind_tail_checkpoints(candidate)

    candidate["source_provenance"]["visual_r1"] = {
        "base_commit": BASE_COMMIT, "base_candidate_sha256": BASE_CANDIDATE_SHA256,
        "preserved_cue_count": len(cues), "frame_extension": shift,
        "extended_market_hold_frames": dict(B17_HOLD_EXTENSION),
    }
    return candidate
