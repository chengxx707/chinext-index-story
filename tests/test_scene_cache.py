from pathlib import Path
import shutil
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from chinext_v6.scene_cache import SceneCache, concat_segments, inspect_media


SPEC = dict(width=32, height=48, fps=6)


def make_clip(path, color="red", frames=2):
    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
        "-i", f"color=c={color}:s=32x48:r=6", "-frames:v", str(frames), "-an",
        "-c:v", "libx264", "-threads", "1", "-pix_fmt", "yuv420p", str(path),
    ], check=True, capture_output=True)
    return path


@pytest.fixture(autouse=True)
def require_media_tools():
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        pytest.skip("FFmpeg/FFprobe are required for actual cache media checks")


def test_scene_signature_tracks_only_selected_files_and_render_inputs(tmp_path):
    doc = tmp_path / "article.html"
    text = tmp_path / "article.txt"
    unrelated = tmp_path / "other.html"
    code = tmp_path / "draw.py"
    font = tmp_path / "font.ttf"
    asset = tmp_path / "earth.png"
    for file in [doc, text, unrelated, code, font, asset]:
        file.write_text(file.name)
    sources = {"AR1": {"document": "article.html", "extracted_text": "article.txt"},
               "AR2": {"document": "other.html"}}
    cache = SceneCache(tmp_path, "cache")
    node = {"id": "S01", "source_ids": ["AR1"], "screen_lines": ["原文"]}

    def key():
        return cache.signature_for(node, source_records=sources, code_paths=[code],
                                   asset_paths=[asset], font_paths=[font], **SPEC,
                                   extra={"crop": [0, 0, 20, 20]})

    original = key()
    unrelated.write_text("another scene changed")
    sources["AR2"]["unrelated_revision"] = 2
    assert key() == original
    text.write_text("selected extracted text changed")
    changed = key()
    assert changed != original
    code.write_text("new drawing code")
    assert key() != changed
    font.unlink()
    with pytest.raises(FileNotFoundError):
        key()


def test_cache_checks_actual_media_spec_and_byte_digest(tmp_path):
    clip = make_clip(tmp_path / "scene.mp4")
    cache = SceneCache(tmp_path, "cache")
    key = cache.signature_for({"id": "S01", "source_ids": []}, source_records={}, **SPEC)
    cached = cache.store(key, clip, expected_frames=2, **SPEC)
    assert cache.lookup(key, expected_frames=2, **SPEC) == cached
    assert cache.lookup(key, expected_frames=3, **SPEC) is None
    assert cache.last_miss == "requested_specification"

    invalid = tmp_path / "invalid.mp4"
    invalid.write_bytes(b"not a movie")
    with pytest.raises(ValueError, match="invalid scene cache"):
        cache.store(key, invalid, expected_frames=2, **SPEC)
    assert cache.lookup(key, expected_frames=2, **SPEC) == cached

    cached.write_bytes(cached.read_bytes() + b"modified")
    assert cache.lookup(key, expected_frames=2, **SPEC) is None
    assert cache.last_miss == "missing_or_changed_output"


def test_inputs_cannot_change_between_signature_and_cache_store(tmp_path):
    clip = make_clip(tmp_path / "scene.mp4")
    asset = tmp_path / "earth.png"
    asset.write_bytes(b"first asset")
    cache = SceneCache(tmp_path, "cache")
    key = cache.signature_for({"id": "S01", "source_ids": []}, source_records={},
                              asset_paths=[asset], **SPEC)
    asset.write_bytes(b"revised during rendering")
    with pytest.raises(ValueError, match="inputs changed"):
        cache.store(key, clip, expected_frames=2, **SPEC)
    assert not (cache.directory / f"{key}.json").exists()


def test_assembly_decodes_correct_order_and_preserves_valid_target_on_failure(tmp_path):
    # Apostrophes and spaces must work without shell interpretation.
    red = make_clip(tmp_path / "red's scene.mp4", "red", 2)
    blue = make_clip(tmp_path / "blue scene.mp4", "blue", 3)
    target = tmp_path / "film.mp4"
    report = concat_segments([red, blue], target, expected_frames=5, **SPEC)
    assert report["passed"] and report["checks"]["full_decode"]
    assert report["segment_frame_counts"] == [2, 3]
    decoded = subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(target),
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-",
    ], capture_output=True, check=True).stdout
    size = 32 * 48 * 3
    assert len(decoded) == size * 5
    assert decoded[0] > decoded[2]  # First frame is red.
    assert decoded[-size + 2] > decoded[-size]  # Last frame is blue.
    original = target.read_bytes()
    with pytest.raises(ValueError, match="frame count"):
        concat_segments([red, blue], target, expected_frames=6, **SPEC)
    assert target.read_bytes() == original
    assert inspect_media(target, expected_frames=5, full_decode=True, **SPEC)["passed"]
