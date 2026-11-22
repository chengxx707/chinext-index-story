"""Resolve a bounded visual revision without altering the released director input."""

from copy import deepcopy
from hashlib import sha256
import json
import math
from pathlib import Path

from .editorial_clock import _CURRENT_X
from .model import MarketData


_PHOTO_SHOT = "GPT2015-21"
_WICK_SHOT = "GPT2015-06"
_PHOTO_CREDIT = "中新社发 刘冉阳 摄｜8月24日图集"
_CAMERA_FIELDS = {
    _WICK_SHOT: {"visible_trading_days", "target_y_domain", "transition_seconds"},
    _PHOTO_SHOT: {"scale", "visible_trading_days", "target_y_domain", "transition_seconds", "inherit_previous_projection"},
}


def _read(path: Path) -> dict:
    return json.loads(path.read_bytes())


def _digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _require(condition: bool, detail: str) -> None:
    if not condition:
        raise ValueError(f"WF-02R1 {detail}")


def _settled_wick_domain(root: Path, cue: dict, trial: dict) -> tuple[list[float], dict]:
    market = MarketData(root / "data/cyb_daily.csv")
    span = trial["visible_trading_days"]
    hit = market.index_for_date(cue["primary_anchor"]["date"])
    first = math.ceil(hit - _CURRENT_X * span)
    low, high = float(market.low[first:hit+1].min()), float(market.high[first:hit+1].max())
    spread = max(high - low, 40.0)
    result = [round(low - trial["y_padding_low_fraction"] * spread, 2),
              round(high + trial["y_padding_high_fraction"] * spread, 2)]
    return result, {"first_visible_trading_day": market.dates[first].date().isoformat(),
                    "last_reached_trading_day": market.dates[hit].date().isoformat(),
                    "observed_low": low, "observed_high": high, "hit_frame": cue["primary_anchor"]["hit_frame"]}


def validate_resolved_director(release: Path, director: dict) -> dict:
    """Prove the resolved data retains the exact released factual and timing inputs."""
    authored = _read(release / "director_timeline.json")
    authored_header = {key: value for key, value in authored.items() if key != "cues"}
    resolved_header = {key: value for key, value in director.items() if key not in {"cues", "visual_revision"}}
    _require(authored_header == resolved_header, "changed immutable timebase, provenance, global rules or rail")
    _require(len(authored["cues"]) == len(director["cues"]) == 28, "must keep all 28 shots")
    pictures = []
    allowed_cameras = []
    for baseline, resolved in zip(authored["cues"], director["cues"], strict=True):
        shot_id = baseline["shot_id"]
        exceptions = {"camera", "text_cue", "visual_revision"}
        _require({key: value for key, value in baseline.items() if key not in exceptions} ==
                 {key: value for key, value in resolved.items() if key not in exceptions},
                 f"changed immutable facts, cue order, geometry or dates at {shot_id}")
        expected_text = dict(baseline["text_cue"])
        if shot_id == _PHOTO_SHOT:
            expected_text["source_line"] = _PHOTO_CREDIT
            pictures.append(shot_id)
        _require(resolved["text_cue"] == expected_text, f"changed immutable on-screen text or reading times at {shot_id}")
        camera_fields = _CAMERA_FIELDS.get(shot_id, set())
        _require({key: value for key, value in baseline["camera"].items() if key not in camera_fields} ==
                 {key: value for key, value in resolved["camera"].items() if key not in camera_fields},
                 f"made an unauthorized camera change at {shot_id}")
        if baseline["camera"] != resolved["camera"]:
            allowed_cameras.append(shot_id)
        style = resolved.get("visual_revision", {})
        _require(style.get("presentation") in {"extremum_or_interval", "policy_or_event", "documentary_photo"},
                 f"has no recognized presentation for {shot_id}")
        _require(type(style.get("exit_frames")) is int and 4 <= style["exit_frames"] <= 7,
                 f"has an invalid exit envelope at {shot_id}")
        _require((style["presentation"] == "documentary_photo") == (shot_id == _PHOTO_SHOT),
                 f"changed the photo role at {shot_id}")
    _require(pictures == [_PHOTO_SHOT] and allowed_cameras == [_WICK_SHOT, _PHOTO_SHOT],
             "missing expected bounded camera and credit adjustments")
    by_id = {cue["shot_id"]: cue for cue in director["cues"]}
    wick = by_id[_WICK_SHOT]
    _require(wick["camera"]["visible_trading_days"] == 48 and wick["primary_anchor"]["hit_frame"] == 990,
             "wick shot must preserve the hit and use the requested 48-day span")
    photo_index = next(i for i, cue in enumerate(director["cues"]) if cue["shot_id"] == _PHOTO_SHOT)
    prior, photo = director["cues"][photo_index-1:photo_index+1]
    photo_camera = photo["camera"]
    _require(photo_camera.get("inherit_previous_projection") is True and photo_camera["transition_seconds"] == 0 and
             all(photo_camera[key] == prior["camera"][key] for key in ("scale", "visible_trading_days", "target_y_domain")),
             "photo cue must use the incoming camera in both asset branches")
    return {
        "passed": True, "revision_id": director["visual_revision"]["revision_id"],
        "shot_count": len(director["cues"]), "frame_count": director["frame_count"], "fps": director["fps"],
        "photo_available": director["visual_revision"]["photo_available"],
        "base_director_timeline_sha256": _digest(release / "director_timeline.json"),
        "photo_credit_change": pictures, "camera_change_shots": allowed_cameras,
        "immutable_fields_checked": ["cue order", "start/end frames", "market_clock", "primary_anchor", "event_clock",
                                      "all screen text lines", "reading times", "link_geometry", "earth_orbit", "rail"],
        "changes": director["visual_revision"]["changes"],
    }


def resolve_director(root: Path, release: Path, revision: Path, photo_available: bool) -> dict:
    """Bind R1 to the released package and return its actual renderer input."""
    plan = _read(revision)
    base, trial, picture, style = (plan[key] for key in ("base", "camera_trial", "photo", "presentation"))
    manifest_path = release / "manifest.json"
    director_path = release / "director_timeline.json"
    manifest = _read(manifest_path)
    _require(plan["schema_version"] == 1 and plan["revision_id"] == "WF-02R1" and
             type(photo_available) is bool and manifest["version"] == base["version"],
             "revision or released manifest identity is invalid")
    _require(_digest(manifest_path) == base["manifest_sha256"] and
             _digest(director_path) == base["director_timeline_sha256"], "base file digest differs from the bound release")
    _require(_digest(root / "data/cyb_daily.csv") == manifest["market_sha256"] and
             _digest(root / "config/production/film_master_v1.json") == manifest["frozen_master_sha256"],
             "frozen market or master digest differs from the bound release")
    director = _read(director_path)
    _require(director["fps"] == 30 and director["frame_count"] == 5010 and len(director["cues"]) == 28,
             "requires the 167-second, 30 fps release")
    _require(trial["shot_id"] == _WICK_SHOT and trial["y_domain"] == "visible_ohlc_through_hit" and
             trial["visible_trading_days"] == 48 and trial["transition_seconds"] == 1.0,
             "has an unexpected wick camera revision")
    _require(picture["shot_id"] == _PHOTO_SHOT and picture["camera"] == "inherit_previous_projection" and
             picture["photo_fit"] == "contain" and picture["source_line"] == _PHOTO_CREDIT,
             "has an unexpected photo camera, fit, or credit revision")
    photo_manifest = _read(release / "photo_manifest.json")
    photos = {item["asset_id"]: item for item in photo_manifest["assets"]}
    _require(picture["asset_id"] == photo_manifest["selected_asset_id"] and
             picture["asset_sha256"] == photos[picture["asset_id"]]["sha256"],
             "photo identity differs from the released documentary asset")
    changed = []
    prior = None
    for cue in director["cues"]:
        shot = cue["shot_id"]
        camera = cue["camera"]
        presentation = style["default"]
        if shot == _WICK_SHOT:
            before = deepcopy(camera)
            domain, bounds = _settled_wick_domain(root, cue, trial)
            camera.update(visible_trading_days=trial["visible_trading_days"], target_y_domain=domain,
                          transition_seconds=trial["transition_seconds"])
            changed.append({"shot_id": shot, "field": "camera", "before": before, "after": deepcopy(camera),
                            "reason": "bounded_wick_zoom_with_hit_visible_frozen_ohlc", "market_range": bounds})
        if shot in style["extremum_or_interval"]:
            presentation = "extremum_or_interval"
        if shot == _PHOTO_SHOT:
            _require(prior is not None and cue["photo_asset_id"] == picture["asset_id"], "photo cue identity mismatch")
            before = deepcopy(camera)
            camera.update({key: deepcopy(prior[key]) for key in ("scale", "visible_trading_days", "target_y_domain")})
            camera.update(inherit_previous_projection=True, transition_seconds=0)
            changed.append({"shot_id": shot, "field": "camera", "before": before, "after": deepcopy(camera),
                            "reason": "photo_layer_inherits_preceding_projection_in_both_asset_branches"})
            before_credit = cue["text_cue"]["source_line"]
            cue["text_cue"]["source_line"] = picture["source_line"]
            changed.append({"shot_id": shot, "field": "text_cue.source_line", "before": before_credit,
                            "after": picture["source_line"], "reason": "use_original_caption_credit"})
            presentation = "documentary_photo"
        cue["visual_revision"] = {"presentation": presentation, "exit_frames": style["exit_frames"],
                                  "target_font_px_at_1080": dict(style["target_font_px_at_1080"])}
        if short := style.get("source_short", {}).get(shot):
            cue["visual_revision"]["source_short"] = short
            changed.append({"shot_id": shot, "field": "visual_revision.source_short", "after": short,
                            "reason": "display_friendly_source_with_full_original_provenance_retained"})
        prior = camera

    director["visual_revision"] = {
        "revision_id": plan["revision_id"], "review_commit": plan["review_commit"],
        "review_files_sha256": plan["review_files_sha256"], "base": base, "revision_sha256": _digest(revision),
        "photo_available": photo_available, "expected_photo_sha256": picture["asset_sha256"],
        "target_font_px_at_1080": style["target_font_px_at_1080"], "changes": changed,
    }
    validate_resolved_director(release, director)
    return director
