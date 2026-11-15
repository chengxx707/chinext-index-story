"""Deterministic silent rendering, bounded parallelism and provenance."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time
import uuid
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

from PIL import Image, ImageDraw

from .model import SceneModel
from .drawing import SceneDrawer


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def production_provenance(root):
    root = Path(root)
    sources = sorted((root / "src").rglob("*.py")) + [root / "render_v6.py", root / "tools/render_ending.py"]
    sources = sorted(p for p in sources if p.is_file())
    digest = hashlib.sha256()
    for path in sources:
        digest.update(f"{path.relative_to(root).as_posix()}:{sha256(path)}\n".encode())
    assets = {p.relative_to(root).as_posix(): sha256(p)
              for p in sorted((root / "assets").rglob("*.png"))}
    return {"source_tree_sha256": digest.hexdigest(), "asset_hashes": assets}


def make_model(config, events, csv, width=None):
    model = SceneModel(config, events, csv)
    if width:
        model.video["height"] = int(round(width * model.video["height"] / model.video["width"]))
        model.video["width"] = int(width)
    return model


def encode_frames(frames, width, height, fps, output, preset="fast", crf=18):
    """Encode RGB PIL images/bytes; preserve errors, replace output only on success."""
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    partial = output.with_name(output.stem + ".partial.mp4")
    error_log = output.with_suffix(".ffmpeg.log")
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{width}x{height}",
           "-r", str(fps), "-i", "pipe:0", "-an", "-c:v", "libx264",
           "-threads", "2", "-preset", preset, "-crf", str(crf),
           "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(partial)]
    with error_log.open("wb") as log:
        p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=log)
        count = 0
        try:
            for frame in frames:
                data = frame if isinstance(frame, bytes) else frame.convert("RGB").tobytes()
                if len(data) != width * height * 3:
                    raise ValueError("RGB frame dimensions do not match encoder")
                p.stdin.write(data)
                count += 1
            p.stdin.close()
            rc = p.wait()
            if rc:
                raise RuntimeError(f"FFmpeg failed ({rc}); see {error_log}")
        except BaseException:
            if p.stdin and not p.stdin.closed:
                p.stdin.close()
            if p.poll() is None:
                p.terminate()
            p.wait()
            raise
    if not count:
        raise ValueError("Refusing zero-frame output")
    os.replace(partial, output)
    return count


_worker_model = None
_worker_drawer = None


def _worker_init(config, events, csv, assets, width):
    global _worker_model, _worker_drawer
    _worker_model = make_model(config, events, csv, width)
    _worker_drawer = SceneDrawer(_worker_model, assets)


def _worker_frame(number):
    return _worker_drawer.render(_worker_model.state(number)).convert("RGB").tobytes()


class Renderer:
    def __init__(self, config, events, csv, assets, width=None):
        self.paths = [str(Path(p).resolve()) for p in (config, events, csv, assets)]
        self.width_override = width
        self.model = make_model(config, events, csv, width)
        self.drawer = SceneDrawer(self.model, assets)

    def frame(self, n):
        return self.drawer.render(self.model.state(n))

    def frame_for_time(self, t):
        return int(round(max(0, min(self.model.duration, t)) / self.model.duration * (len(self.model.states) - 1)))

    def keyframes(self, out, times=None):
        out = Path(out)
        dest = out / "keyframes"
        dest.mkdir(parents=True, exist_ok=True)
        if times is None:
            times = [0, 2.5, 7.0, 10.5, 17.5, 22.0, 26.0, 32.0, 38.5, self.model.duration]
        paths = []
        diagnostics = []
        for t in times:
            n = self.frame_for_time(t)
            state = self.model.state(n)
            frame = self.frame(n)
            path = dest / f"frame_{t:05.2f}.png"
            frame.save(path)
            paths.append((path, state))
            if hasattr(self.drawer, "get_layout_diagnostics"):
                diagnostics.append(self.drawer.get_layout_diagnostics(state))
        self.contact_sheet(paths, out / "review_contact.jpg")
        (out / "layout_diagnostics.json").write_text(json.dumps(diagnostics, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        return paths

    @staticmethod
    def contact_sheet(paths, output):
        tw, th, cols = 270, 480, 4
        rows = (len(paths) + cols - 1) // cols
        sheet = Image.new("RGB", (cols * tw, rows * (th + 32)), (5, 10, 15))
        d = ImageDraw.Draw(sheet)
        for i, (path, state) in enumerate(paths):
            frame = Image.open(path).convert("RGB")
            frame.thumbnail((tw, th), Image.Resampling.LANCZOS)
            x, y = (i % cols) * tw, (i // cols) * (th + 32)
            sheet.paste(frame, (x, y))
            d.text((x + 6, y + th + 8), f"{state.t:.2f}s  {state.current_date:%Y.%m.%d}", fill=(220, 228, 234))
        sheet.save(output, quality=93)

    def diagnostics(self, out):
        out = Path(out)
        out.mkdir(parents=True, exist_ok=True)
        shots = []
        for s in self.model.states:
            shots.append({k: getattr(s, k) for k in ["frame_number", "t", "current_date", "current_close", "shot_id", "visible_days", "current_x_frac", "y_min", "y_max", "stage_mode", "stage_value", "active_event_ids"]})
        events = []
        for event in self.model.events:
            s = self.model.state(self.frame_for_time(event.hit_t))
            events.append({"id": event.id, "hit_t": event.hit_t, "event_date": event.date,
                           "actual_date": s.current_date, "event_index": event.index,
                           "actual_index": s.current_index,
                           "hold_seconds": event.post_seconds,
                           "date_matches": event.index == s.current_index})
        for name, value in [("shot_diagnostics.json", shots), ("event_diagnostics.json", events)]:
            (out / name).write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    def video(self, out, workers=2):
        out = Path(out)
        out.mkdir(parents=True, exist_ok=True)
        output = out / "chinext_v6_sample.mp4"
        total = len(self.model.states)
        start = time.monotonic()
        root = Path(__file__).resolve().parents[2]
        provenance = production_provenance(root)
        input_hashes = [sha256(path) for path in self.paths[:3]]
        def frames():
            if workers <= 1:
                for n in range(total):
                    if n % self.model.fps == 0:
                        print(f"render {n}/{total}", flush=True)
                    yield self.frame(n)
            else:
                # Bounded batches avoid retaining a full uncompressed film in RAM.
                with ProcessPoolExecutor(max_workers=workers, initializer=_worker_init,
                                         initargs=(*self.paths, self.width_override)) as pool:
                    size = max(4, workers * 4)
                    for first in range(0, total, size):
                        yield from pool.map(_worker_frame, range(first, min(first + size, total)))
                        if first % (size * 5) == 0:
                            print(f"render {min(first + size, total)}/{total} elapsed={time.monotonic()-start:.1f}s", flush=True)
        v = self.model.video
        count = encode_frames(frames(), int(v["width"]), int(v["height"]), self.model.fps, output,
                              preset=v.get("preset", "fast"), crf=v.get("crf", 18))
        if provenance != production_provenance(root) or input_hashes != [sha256(path) for path in self.paths[:3]]:
            raise RuntimeError("Production inputs changed during render; candidate has no valid manifest. Re-render after edits finish.")
        manifest = {"run_id": str(uuid.uuid4()), "config": self.paths[0], "events": self.paths[1],
                    "csv": self.paths[2], "config_sha256": sha256(self.paths[0]),
                    "events_sha256": sha256(self.paths[1]), "csv_sha256": sha256(self.paths[2]),
                    "video_path": str(output.resolve()), "width": v["width"], "height": v["height"],
                    "fps": self.model.fps, "duration": count / self.model.fps, "frame_count": count,
                    "elapsed_seconds": round(time.monotonic() - start, 2), "audio": "none"}
        manifest.update(provenance)
        (out / "render_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        return output
