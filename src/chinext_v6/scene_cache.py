"""Content-addressed scene outputs and checked silent-film assembly.

The key covers the selected node and the files the caller actually uses. It
does not include other nodes, the whole film manifest or unrelated sources.
Only a checked output with a matching byte digest is a cache hit.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import uuid
from fractions import Fraction
from pathlib import Path
from typing import Any, Iterable, Mapping


def file_sha256(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def _checked_spec(width: int, height: int, fps: int | float, frames: int) -> None:
    if width <= 0 or height <= 0 or width % 2 or height % 2:
        raise ValueError("Silent MP4 dimensions must be positive and even")
    if fps <= 0 or frames <= 0:
        raise ValueError("Expected frame count and frame rate must be positive")


def inspect_media(path: str | Path, *, width: int, height: int,
                  fps: int | float, expected_frames: int,
                  full_decode: bool = False) -> dict[str, Any]:
    """Inspect actual streams/frames; optionally decode the entire output.

    Invalid media returns a failed report; missing tools also fail rather than
    allowing a cache hit. Invalid requested output specifications raise.
    """
    _checked_spec(width, height, fps, expected_frames)
    path = Path(path)
    report: dict[str, Any] = {"passed": False, "checks": {}, "path": str(path)}
    try:
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-count_frames", "-show_streams",
             "-show_format", "-of", "json", str(path)],
            capture_output=True, text=True, check=True)
        metadata = json.loads(result.stdout)
        streams = metadata.get("streams", [])
        videos = [s for s in streams if s.get("codec_type") == "video"]
        checks = report["checks"]
        checks["one_video_stream"] = len(videos) == 1
        checks["no_audio_stream"] = not any(s.get("codec_type") == "audio" for s in streams)
        if len(videos) == 1:
            video = videos[0]
            checks["dimensions"] = (video.get("width"), video.get("height")) == (width, height)
            checks["frame_rate"] = Fraction(video["r_frame_rate"]) == Fraction(str(fps))
            checks["frame_count"] = int(video.get("nb_read_frames", -1)) == expected_frames
            duration = float(metadata["format"]["duration"])
            checks["duration"] = abs(duration - expected_frames / fps) <= 1 / fps + 1e-6
        # ffprobe can report decoder errors without returning a nonzero status.
        checks["probe_without_decode_errors"] = not result.stderr.strip()
        report["probe"] = metadata
        if full_decode:
            decoded = subprocess.run(
                ["ffmpeg", "-hide_banner", "-loglevel", "error", "-xerror",
                 "-threads", "2", "-i", str(path), "-map", "0:v:0",
                 "-an", "-f", "null", "-"],
                capture_output=True, text=True)
            checks["full_decode"] = decoded.returncode == 0 and not decoded.stderr.strip()
            if not checks["full_decode"]:
                report["decode_error"] = decoded.stderr[-2000:]
        report["passed"] = bool(checks) and all(checks.values())
    except (OSError, ValueError, TypeError, ZeroDivisionError, KeyError, subprocess.CalledProcessError) as exc:
        report["error"] = str(exc)
    return report


class SceneCache:
    """Store immutable rendered segments keyed by selected scene dependencies."""

    version = 1

    def __init__(self, root: str | Path, cache_dir: str | Path):
        self.root = Path(root).resolve()
        directory = Path(cache_dir)
        self.directory = (self.root / directory).resolve() if not directory.is_absolute() else directory.resolve()
        self.directory.mkdir(parents=True, exist_ok=True)
        self._signatures: dict[str, dict[str, Any]] = {}
        self.last_miss: str | None = None

    def _path(self, path: str | Path) -> Path:
        path = Path(path)
        return path.resolve() if path.is_absolute() else (self.root / path).resolve()

    def _file_record(self, value: str | Path) -> dict[str, str]:
        path = self._path(value)
        if not path.is_file():
            raise FileNotFoundError(f"Required scene dependency is missing: {path}")
        try:
            label = path.relative_to(self.root).as_posix()
        except ValueError:
            label = str(path)
        return {"path": label, "sha256": file_sha256(path)}

    @staticmethod
    def _source_files(record: Any) -> Iterable[str]:
        """Find actual provenance files, including nested documentary evidence."""
        file_keys = {"document", "extracted_text", "local_path", "text_path", "file_path"}
        if isinstance(record, dict):
            for key, value in record.items():
                if key in file_keys and isinstance(value, str) and value:
                    yield value
                elif key == "source_files" and isinstance(value, list):
                    yield from (item for item in value if isinstance(item, str))
                elif isinstance(value, (dict, list)):
                    yield from SceneCache._source_files(value)
        elif isinstance(record, list):
            for value in record:
                yield from SceneCache._source_files(value)

    def signature_for(self, node: Mapping[str, Any], *,
                      source_records: Mapping[str, Any],
                      code_paths: Iterable[str | Path] = (),
                      asset_paths: Iterable[str | Path] = (),
                      font_paths: Iterable[str | Path] = (),
                      width: int, height: int, fps: int | float,
                      extra: Any = None) -> str:
        """Compute a reproducible key from the node and its actual dependencies.

        Pass shared visual data such as the market CSV in ``asset_paths`` when
        that node renders it even though the foreground does not cite CSV.
        ``extra`` must include camera/crop parameters and compilation state used
        to draw this node, so changes in a predecessor cannot reuse stale motion.
        """
        _checked_spec(width, height, fps, 1)
        selected: dict[str, Any] = {}
        source_files: set[str] = set()
        for sid in sorted(set(node.get("source_ids", ()))):
            if sid not in source_records:
                raise ValueError(f"Scene references an unknown source: {sid}")
            selected[sid] = source_records[sid]
            source_files.update(self._source_files(source_records[sid]))
        payload = {
            "schema_version": self.version,
            "node": dict(node), "selected_sources": selected,
            "source_files": sorted((self._file_record(p) for p in source_files), key=lambda x: x["path"]),
            "code": sorted((self._file_record(p) for p in set(code_paths)), key=lambda x: x["path"]),
            "assets": sorted((self._file_record(p) for p in set(asset_paths)), key=lambda x: x["path"]),
            "fonts": sorted((self._file_record(p) for p in set(font_paths)), key=lambda x: x["path"]),
            "video": {"width": width, "height": height, "fps": fps},
            "extra": extra,
        }
        key = hashlib.sha256(_json_bytes(payload)).hexdigest()
        self._signatures[key] = payload
        return key

    def _paths(self, key: str) -> tuple[Path, Path]:
        if not re.fullmatch(r"[0-9a-f]{64}", key):
            raise ValueError("Cache keys must be lowercase SHA-256 digests")
        return self.directory / f"{key}.mp4", self.directory / f"{key}.json"

    def _verify_inputs_unchanged(self, key: str) -> dict[str, Any]:
        signature = self._signatures.get(key)
        if signature is None or hashlib.sha256(_json_bytes(signature)).hexdigest() != key:
            raise ValueError("Compute this scene signature before storing its output")
        for kind in ("source_files", "code", "assets", "fonts"):
            for record in signature[kind]:
                path = self._path(record["path"])
                if not path.is_file() or file_sha256(path) != record["sha256"]:
                    raise ValueError(f"Scene inputs changed since cache signature: {record['path']}")
        return signature

    def lookup(self, key: str, *, expected_frames: int,
               width: int, height: int, fps: int | float) -> Path | None:
        output, manifest_path = self._paths(key)
        self.last_miss = None
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            if manifest.get("schema_version") != self.version or manifest.get("key") != key:
                self.last_miss = "manifest_identity"
                return None
            signature = manifest.get("signature")
            if not signature or hashlib.sha256(_json_bytes(signature)).hexdigest() != key:
                self.last_miss = "manifest_signature"
                return None
            expected = {"width": width, "height": height, "fps": fps, "frame_count": expected_frames}
            if manifest.get("video") != expected:
                self.last_miss = "requested_specification"
                return None
            if not output.is_file() or file_sha256(output) != manifest.get("output_sha256"):
                self.last_miss = "missing_or_changed_output"
                return None
            actual = inspect_media(output, width=width, height=height, fps=fps,
                                   expected_frames=expected_frames)
            if not actual["passed"]:
                self.last_miss = "actual_media_validation"
                return None
            return output
        except (OSError, ValueError, TypeError):
            self.last_miss = "missing_or_invalid_manifest"
            return None

    def store(self, key: str, video_path: str | Path, *, expected_frames: int,
              width: int, height: int, fps: int | float) -> Path:
        """Copy, fully decode and atomically install a candidate and manifest."""
        output, manifest_path = self._paths(key)
        signature = self._verify_inputs_unchanged(key)
        token = uuid.uuid4().hex
        candidate = self.directory / f".{key}.{token}.partial.mp4"
        manifest_candidate = self.directory / f".{key}.{token}.partial.json"
        try:
            shutil.copyfile(video_path, candidate)
            media = inspect_media(candidate, width=width, height=height, fps=fps,
                                  expected_frames=expected_frames, full_decode=True)
            if not media["passed"]:
                raise ValueError(f"Refusing invalid scene cache candidate: {media}")
            self._verify_inputs_unchanged(key)
            manifest = {
                "schema_version": self.version, "key": key,
                "video": {"width": width, "height": height, "fps": fps, "frame_count": expected_frames},
                "output_sha256": file_sha256(candidate),
                "signature": signature, "media_checks": media["checks"],
            }
            manifest_candidate.write_bytes(_json_bytes(manifest) + b"\n")
            os.replace(candidate, output)
            os.replace(manifest_candidate, manifest_path)
            return output
        finally:
            candidate.unlink(missing_ok=True)
            manifest_candidate.unlink(missing_ok=True)


def concat_segments(paths: Iterable[str | Path], target: str | Path, *,
                    width: int, height: int, fps: int | float,
                    expected_frames: int, full_decode: bool = True,
                    allow_transcode_fallback: bool = True) -> dict[str, Any]:
    """Join compatible segments and replace the target only after validation.

    Short H.264 segments can have overlapping B-frame decode timestamps. Try
    stream-copy first; if its actual result fails, optionally decode/concatenate
    and rebuild a constant-rate timeline. The report records this fallback.
    """
    _checked_spec(width, height, fps, expected_frames)
    paths = [Path(path).resolve() for path in paths]
    if not paths:
        raise ValueError("Cannot assemble an empty segment list")
    target = Path(target).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    # Input codecs and timing must agree for stream-copy assembly. Each source
    # is inspected rather than trusting old render reports or file extensions.
    signatures = []
    frame_counts = []
    for path in paths:
        raw = subprocess.run(
            ["ffprobe", "-v", "error", "-count_frames", "-show_streams", "-of", "json", str(path)],
            capture_output=True, text=True, check=True)
        streams = json.loads(raw.stdout).get("streams", [])
        if len(streams) != 1 or streams[0].get("codec_type") != "video" or raw.stderr.strip():
            raise ValueError(f"Assembly input must contain only a valid silent video stream: {path}")
        stream = streams[0]
        if (stream.get("width"), stream.get("height")) != (width, height) or Fraction(stream["r_frame_rate"]) != Fraction(str(fps)):
            raise ValueError(f"Assembly input specification differs: {path}")
        signatures.append(tuple(stream.get(k) for k in ("codec_name", "profile", "pix_fmt", "time_base")))
        frame_counts.append(int(stream["nb_read_frames"]))
    if len(set(signatures)) != 1:
        raise ValueError("Stream-copy assembly requires matching codecs, pixel formats and time bases")
    if sum(frame_counts) != expected_frames:
        raise ValueError("Assembly input frame count differs from the declared total")
    with tempfile.TemporaryDirectory(prefix=".assemble-", dir=target.parent) as temporary:
        temp = Path(temporary)
        listing = temp / "segments.txt"
        for path in paths:
            if "\n" in str(path) or "\r" in str(path):
                raise ValueError("Newlines in segment paths are unsupported")
        listing.write_text("".join("file '" + str(path).replace("'", "'\\''") + "'\n" for path in paths), encoding="utf-8")
        candidate = temp / "assembled.partial.mp4"
        assembly_mode = "stream_copy"
        try:
            subprocess.run(
                ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0",
                 "-i", str(listing), "-map", "0:v:0", "-an", "-c", "copy", "-movflags", "+faststart", str(candidate)],
                capture_output=True, text=True, check=True)
            report = inspect_media(candidate, width=width, height=height, fps=fps,
                                   expected_frames=expected_frames, full_decode=full_decode)
        except subprocess.CalledProcessError as exc:
            report = {"passed": False, "error": str(exc), "stderr": exc.stderr[-2000:]}
        copy_report = report
        if not report["passed"] and allow_transcode_fallback:
            assembly_mode = "transcode_fallback"
            rate = str(Fraction(str(fps)))
            inputs = [item for path in paths for item in ("-i", str(path))]
            normalized = "".join(f"[{i}:v:0]setpts=N/({rate}*TB)[v{i}];" for i in range(len(paths)))
            labels = "".join(f"[v{i}]" for i in range(len(paths)))
            filters = normalized + labels + f"concat=n={len(paths)}:v=1:a=0,setpts=N/({rate}*TB)[joined]"
            subprocess.run(
                ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", *inputs,
                 "-filter_complex_threads", "1", "-filter_complex", filters, "-map", "[joined]",
                 "-an", "-r", rate, "-c:v", "libx264", "-threads", "2", "-preset", "fast",
                 "-crf", "18", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(candidate)],
                capture_output=True, text=True, check=True)
            report = inspect_media(candidate, width=width, height=height, fps=fps,
                                   expected_frames=expected_frames, full_decode=full_decode)
        if not report["passed"]:
            raise ValueError(f"Assembled output failed validation: {report}")
        digest = file_sha256(candidate)
        os.replace(candidate, target)
    report.update({"path": str(target), "output_sha256": digest,
                   "segment_count": len(paths), "segment_frame_counts": frame_counts,
                   "segments": [str(path) for path in paths],
                   "assembly_mode": assembly_mode})
    if assembly_mode == "transcode_fallback":
        report["stream_copy_attempt"] = copy_report
    return report
