"""Present the existing compiled schedule as a standalone, timing-only preview."""

from hashlib import sha256
import json
from pathlib import Path


def build_preview(compiled: Path, out: Path) -> None:
    payload = compiled.read_bytes()
    timeline = json.loads(payload)
    fps = timeline["video"]["fps"]
    frame_count = timeline["video"]["frame_count_plan"]
    beats = []
    for scene in timeline["scenes"]:
        for beat in scene["beats"]:
            beats.append({
                "scene_id": scene["id"],
                "beat_id": beat["id"],
                "title": scene["title"],
                "start_frame": beat["start_frame"],
                "end_frame_exclusive": beat["end_frame_exclusive"],
                "screen_lines": beat["screen_lines"],
                "source_line": beat["source_line"],
                "historical_date": beat["historical_date"],
                "market_observation_date": beat["market_observation_date"],
                "placeholder": "档案照片占位 · 仅供粗预演" if scene["role"] == "album" else None,
            })
    next_frame = 0
    for beat in beats:
        if beat["start_frame"] != next_frame or beat["end_frame_exclusive"] <= next_frame:
            raise ValueError(f"Compiled beat coverage is invalid at {beat['beat_id']}")
        next_frame = beat["end_frame_exclusive"]
    if fps <= 0 or next_frame != frame_count or not beats:
        raise ValueError("Compiled schedule has invalid duration or no beats")
    report = {
        "status": "timing_preview_ready",
        "visual_rendered": False,
        "compiled_sha256": sha256(payload).hexdigest(),
        "master_sha256": timeline["master_sha256"],
        "fps": fps,
        "frame_count": frame_count,
        "duration_seconds": frame_count / fps,
        "placeholder_scene_ids": list(dict.fromkeys(
            beat["scene_id"] for beat in beats if beat["placeholder"]
        )),
        "beats": beats,
    }
    out.mkdir(parents=True, exist_ok=True)
    (out / "preview_timing.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    page_data = json.dumps(report, ensure_ascii=False).replace("<", "\\u003c")
    html = Path(__file__).with_name("preview.html").read_text(encoding="utf-8")
    (out / "preview.html").write_text(html.replace("/* PREVIEW_DATA */", page_data), encoding="utf-8")
