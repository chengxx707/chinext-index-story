"""Encode the four-second B08 handoff using the delivered V1.0.2 compositor."""

from __future__ import annotations

import argparse
from hashlib import sha256
from io import BytesIO
import json
import math
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from zipfile import ZipFile

from PIL import Image, ImageChops


BASE = "b0d71e895a7d756fa2ebbb7d8f3f471d581f1ccb"
DIRECTOR_DECISION = "9f0a628b787e7d4345c4acdbee9c81ac687aa446"
RUNTIME = "67a8cc6740c521675f71c6c733997e429681c3a2"
BASE_DIR = "editorial/2015/director/visual-tests/v1.0.2"
ZIP_SHA = "dd46b813641e683bb751a3dfdd83abbdc1d8e6ae261b11bf9196beb06e34834e"
SOURCE_SIZE = (1080, 1920)
PHONE_SIZE = (390, 694)
FPS = 30
START, END = 2550, 2670
POLICY_END, MONDAY, TUESDAY = 2640, 2649, 2657
MARKER = "6/28 · 实施"
MARKER_ROLE = "retired_policy_date"
APPROVED_MARKER = {
    "text": MARKER,
    "start_frame": POLICY_END,
    "fade_from_frame": 2653,
    "end_frame_exclusive": TUESDAY,
    "opacity": 0.5,
}
B08_HANDOFF = "V102-B08-04"
HIGH_CLOSE = 3982.25


def git_blob(repo, ref, path):
    return subprocess.check_output(["git", "-C", str(repo), "show", f"{ref}:{path}"])


def digest(data):
    return sha256(data).hexdigest()


def load_scene(repo, work, selected_path):
    inputs = {}
    for name in ("data/cyb_daily.csv", "assets/earth_cinematic.png", "assets/earth_body.png"):
        pinned = git_blob(repo, BASE, name)
        if (repo / name).read_bytes() != pinned:
            raise ValueError(f"Local source differs from the baseline at {name}")
        inputs[name] = digest(pinned)

    storyboard = git_blob(repo, DIRECTOR_DECISION, "editorial/2015/director/B08_LAYERED_STORYBOARD_V1.0.2.md")
    inputs["approved_storyboard"] = digest(storyboard)
    package = git_blob(repo, BASE, f"{BASE_DIR}/director-v1.0.2-representative-visual-review.zip")
    inputs["baseline_review_archive"] = digest(package)
    if inputs["baseline_review_archive"] != ZIP_SHA:
        raise ValueError("Unexpected baseline render archive")
    with ZipFile(BytesIO(package)) as review:
        candidate = review.read("candidate.json")
        if candidate != git_blob(repo, BASE, f"{BASE_DIR}/candidate.json"):
            raise ValueError("The delivered archive and committed candidate differ")
        inputs["baseline_candidate"] = digest(candidate)
        for name in ("render_visual.py", "visual_overlay.py"):
            contents = review.read(f"tools/{name}")
            (work / name).write_bytes(contents)
            inputs[name] = digest(contents)
        segments = json.loads(review.read("legacy/segments.json"))
        for segment in segments:
            name = f"legacy/{segment['id']}.json"
            contents = review.read(name)
            inputs[name] = digest(contents)
            segment["timeline"] = json.loads(contents)

    pinned = subprocess.check_output(["git", "-C", str(repo), "archive", RUNTIME,
                                      "src/chinext_v6", "tools/render_editorial_preview.py",
                                      "editorial/2015/releases/v1.0.1"])
    runtime = work / "runtime"
    runtime.mkdir()
    subprocess.run(["tar", "-xf", "-", "-C", str(runtime)], input=pinned, check=True)
    sys.path.insert(0, str(work))
    from render_visual import build_scene

    candidate = json.loads(candidate)
    cue = next(cue for cue in candidate["cues"] if cue["shot_id"] == B08_HANDOFF)
    cue["camera_story_clock"]["retired_policy_marker"] = APPROVED_MARKER
    if selected_path is not None:
        selected = selected_path.read_bytes()
        variants = [cue for cue in json.loads(selected)["cues"] if cue["beat_id"] == "B08"]
        if variants != [cue for cue in candidate["cues"] if cue["beat_id"] == "B08"]:
            raise ValueError("Selected candidate changes B08 beyond the approved date marker")
        inputs["selected_candidate"] = digest(selected)
    scene = build_scene(repo, candidate, segments, runtime, width=SOURCE_SIZE[0])
    return scene, inputs


def add_retired_policy_date(original):
    from visual_overlay import Caption, MUTED

    def draw(image, drawer, state, cue, frame, t2_state=None):
        report = original(image, drawer, state, cue, frame, t2_state=t2_state)
        marker_config = cue["camera_story_clock"].get("retired_policy_marker")
        if marker_config is None:
            return report
        end = marker_config["end_frame_exclusive"]
        if not marker_config["start_frame"] <= frame < end:
            return report
        fade_length = end - marker_config["fade_from_frame"]
        opacity = marker_config["opacity"] * min(1.0, (end - frame) / fade_length)
        layer = drawer._new()
        start = len(drawer.text_boxes)
        marker = Caption(drawer, layer, 1.0)
        marker.text(marker_config["text"], 69, 166, 22, role=MARKER_ROLE, color=MUTED, opacity=opacity, width=420)
        image.alpha_composite(layer)
        return {
            **report,
            "text_visible": True,
            "caption_lines": [*report["caption_lines"], *marker.lines],
            "caption_boxes": [*report["caption_boxes"], *drawer.text_boxes[start:]],
            "text_roles": [*report["text_roles"], *marker.roles],
            "retired_policy_marker": {"text": marker_config["text"], "opacity": opacity, "end_frame_exclusive": end},
        }

    return draw


def check_timing(rows):
    def levels(start, end, date, close, focus):
        return all(
            (row["market_date"], row["market_close"], row["primary_focus"])
            == (date, close, focus)
            and math.isclose(row["stage_value"], close / HIGH_CLOSE - 1, abs_tol=1e-6)
            for row in (rows[frame] for frame in range(start, end))
        )

    marker = [
        frame for frame, row in rows.items()
        if row["overlay"].get("retired_policy_marker")
    ]
    return {
        "only_expected_frame_span": list(rows) == list(range(START, END)),
        "one_unobscured_rail_and_no_future_candles": all(
            row["active_track_count"] == 1 and not row["layout_errors"] and row["no_future_candles"]
            for row in rows.values()
        ),
        "frozen_friday_during_sunday_policy": levels(START, POLICY_END, "2015-06-26", 2920.70, "L2_EVENT"),
        "market_focus_returns_before_monday": levels(POLICY_END, MONDAY, "2015-06-26", 2920.70, "L1_MARKET"),
        "monday_close_candle_and_rail_share_market_row": levels(MONDAY, TUESDAY, "2015-06-29", 2689.76, "L1_MARKET")
        and rows[MONDAY]["market_index"] == rows[MONDAY - 1]["market_index"] + 1,
        "tuesday_resumes_with_no_marker": rows[TUESDAY]["market_date"] == "2015-06-30"
        and not rows[TUESDAY]["overlay"].get("retired_policy_marker"),
        "marker_only_during_handoff": marker == list(range(POLICY_END, TUESDAY)),
        "only_secondary_date_no_policy_body": all(
            row["overlay"]["caption_lines"] == [MARKER] and
            [entry["role"] for entry in row["overlay"]["text_roles"]] == [MARKER_ROLE]
            for row in (rows[frame] for frame in marker)
        ),
        "marker_reduced_opacity_then_fades": rows[MONDAY]["overlay"]["retired_policy_marker"]["opacity"] == 0.5
        and 0 < rows[TUESDAY - 1]["overlay"]["retired_policy_marker"]["opacity"] < 0.5,
    }


def render(repo, out, selected_path):
    with TemporaryDirectory(prefix="chinext-b08-") as temp:
        scene, inputs = load_scene(repo, Path(temp), selected_path)
        from chinext_v6.renderer import encode_frames
        from chinext_v6.scene_cache import inspect_media

        original = scene._overlay
        selected = add_retired_policy_date(original)
        rows = {}
        checks_pixel = {}

        def phone_frames():
            for frame in range(START, END):
                scene._overlay = selected
                image, diagnostics = scene.frame(frame)
                if image.size != SOURCE_SIZE:
                    raise AssertionError("Unexpected source dimensions")
                rows[frame] = diagnostics
                if frame in (POLICY_END - 1, POLICY_END, MONDAY, TUESDAY - 1, TUESDAY):
                    scene._overlay = original
                    without_marker, _ = scene.frame(frame)
                    changed = ImageChops.difference(without_marker, image).getbbox()
                    marker_boxes = [box["bbox"] for box in diagnostics["overlay"]["caption_boxes"]
                                    if box["role"] == MARKER_ROLE]
                    if marker_boxes:
                        x0, y0, x1, y1 = marker_boxes[0]
                        valid = bool(changed and changed[0] >= x0 - 1 and changed[1] >= y0 - 1
                                     and changed[2] <= x1 + 1 and changed[3] <= y1 + 1)
                    else:
                        valid = changed is None
                    checks_pixel[frame] = {"changed_roi_source_px": changed, "only_date_marker_differs": valid}
                yield image.resize(PHONE_SIZE, Image.Resampling.LANCZOS).tobytes()

        media = out / "phone-390.mp4"
        count = encode_frames(phone_frames(), *PHONE_SIZE, FPS, media, preset="veryfast", crf=20)
        probe = inspect_media(media, width=PHONE_SIZE[0], height=PHONE_SIZE[1], fps=FPS,
                              expected_frames=END - START, full_decode=True)
        checks = {
            **check_timing(rows),
            "control_pixels_match_except_date_marker": all(check["only_date_marker_differs"] for check in checks_pixel.values()),
            "video_frame_count_matches": count == END - START,
            "probe_and_full_decode": probe["passed"],
        }
        frames = {}
        for frame in (2556, POLICY_END - 1, POLICY_END, MONDAY, TUESDAY - 1, TUESDAY, END - 1):
            row = rows[frame]
            frames[frame] = {
                "clip_local_seconds": round((frame - START) / FPS, 4),
                "focus": row["primary_focus"],
                "market_date": row["market_date"],
                "market_close": row["market_close"],
                "last_candle_index": row["last_eligible_candle_index"],
                "drawdown_pct": round(100 * row["stage_value"], 2),
                "caption_lines": row["overlay"]["caption_lines"],
                "roles": row["overlay"]["text_roles"],
                "marker": row["overlay"].get("retired_policy_marker"),
                "changed_pixels_vs_no_marker": checks_pixel.get(frame),
            }
        result = {
            "passed": all(checks.values()),
            "approving_commit": DIRECTOR_DECISION,
            "picture_baseline_commit": BASE,
            "clock_implementation_commit": RUNTIME,
            "marker_config": APPROVED_MARKER,
            "checks": checks,
            "market_boundaries": frames,
            "inputs_sha256": inputs,
            "frame_interval_end_exclusive": [START, END],
            "duration_seconds": (END - START) / FPS,
            "media": {"name": media.name, "sha256": digest(media.read_bytes()), "probe": probe},
        }
        (out / "manifest.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps(checks, ensure_ascii=False), flush=True)
        return result["passed"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", default=Path.cwd(), type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--candidate", type=Path, help="Optional selected candidate to bind to the B08 build")
    args = parser.parse_args()
    repo, out = args.repo_root.resolve(), args.out.resolve()
    if not out.is_relative_to(repo / "output") or out == repo / "output":
        parser.error("Use a dedicated output directory under the repo's output/")
    out.mkdir(parents=True, exist_ok=True)
    return 0 if render(repo, out, args.candidate) else 1


if __name__ == "__main__":
    raise SystemExit(main())
