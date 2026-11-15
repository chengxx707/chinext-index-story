"""Compile the production master without weakening the sample's date checks.

Film time is an integer-frame clock.  Historical events retain their original
precision, source publication/effective dates are metadata, and market clocks
refer only to real CSV rows.  This first compiler holds a beat's observation
anchor; it deliberately does not claim to implement the renderer's continuous
market progression or to have passed a reading/visual review.
"""
from __future__ import annotations

from bisect import bisect_right
import calendar
from dataclasses import dataclass
from datetime import date
import hashlib
import html
import json
from pathlib import Path
import re
from typing import Any

from .model import MarketData


class ProductionError(ValueError):
    """The selected master cannot safely be compiled for production."""


@dataclass(frozen=True)
class SourceDateContext:
    source_id: str
    publication_date: str | None
    published_at: str | None
    event_dates: tuple[str, ...]
    effective_dates: tuple[str, ...]
    page_date: str | None


@dataclass(frozen=True)
class CompiledBeat:
    node_id: str
    beat_index: int
    phase_id: str
    role: str
    title: str
    start_frame: int
    end_frame_exclusive: int
    screen_lines: tuple[str, ...]
    source_line: str | None
    source_ids: tuple[str, ...]
    historical_date: str | None
    date_precision: str
    market_anchor: str | None
    observation_date: str | None
    observation_index: int | None
    observation_policy: str
    hud_label: str
    stable_frames_min: int
    source_date_context: tuple[SourceDateContext, ...]
    implementation_note: str

    @property
    def id(self) -> str:
        return f"{self.node_id}_b{self.beat_index + 1:02d}"


@dataclass(frozen=True)
class ProductionFrameState:
    frame_number: int
    node_id: str
    beat_index: int
    phase_id: str
    role: str
    local_frame: int
    beat_progress: float
    screen_lines: tuple[str, ...]
    source_line: str | None
    source_ids: tuple[str, ...]
    historical_date: str | None
    date_precision: str
    event_market_anchor: str | None
    current_date: str | None
    current_close: float | None
    market_index: int | None
    show_hud: bool
    show_chart: bool
    hud_label: str
    observation_policy: str
    clock_policy: str = "beat_anchor_hold_v1"


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _date(value: Any, context: str) -> str:
    try:
        if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            raise ValueError
        return date.fromisoformat(value).isoformat()
    except (TypeError, ValueError) as error:
        raise ProductionError(f"Invalid exact date for {context}: {value!r}") from error


def _bounds(value: str | None, precision: str) -> tuple[str, str] | None:
    if value is None:
        return None
    if precision == "day":
        d = _date(value, "historical event")
        return d, d
    if precision == "month" and re.fullmatch(r"\d{4}-\d{2}", value):
        try:
            year, month = map(int, value.split("-"))
            last_day = calendar.monthrange(year, month)[1]
            return date(year, month, 1).isoformat(), date(year, month, last_day).isoformat()
        except ValueError as error:
            raise ProductionError(f"Invalid event month: {value}") from error
    if precision == "year" and re.fullmatch(r"\d{4}", value):
        return f"{value}-01-01", f"{value}-12-31"
    if precision in {"range", "year_range"} and "/" in value:
        first, last = value.split("/", 1)
        if precision == "year_range" and re.fullmatch(r"\d{4}", first) and re.fullmatch(r"\d{4}", last):
            first, last = f"{first}-01-01", f"{last}-12-31"
        first, last = _date(first, "range start"), _date(last, "range end")
        if first > last:
            raise ProductionError(f"Historical range reverses: {value}")
        return first, last
    raise ProductionError(f"Date {value!r} does not preserve declared precision {precision!r}")


def _source_dates(source_id: str, source: dict[str, Any]) -> SourceDateContext:
    values = source.get("date_context", {})
    events: list[str] = []
    effects: list[str] = []
    for key, value in values.items():
        if "event" in key or key in {"index_launch_date", "reported_policy_date"}:
            events.extend(value if isinstance(value, list) else [value])
        if "effective" in key and value is not None:
            effects.extend(value if isinstance(value, list) else [value])
    published_at = values.get("published_at")
    publication = values.get("published_date", values.get("reprint_date"))
    if publication is None and published_at:
        publication = published_at[:10]
    return SourceDateContext(source_id, publication, published_at, tuple(events),
                             tuple(effects), values.get("page_date"))


class ProductionTimeline:
    """Validate one source master and expose frame-indexed production state.

    Month/range observations that lack an explicit market anchor use a clearly
    diagnosed period-end CSV observation.  They never acquire a fabricated
    event day: ``market_anchor``/``event_market_anchor`` remain ``None``.
    """

    def __init__(self, master_path: str | Path, *, root: str | Path | None = None,
                 csv_path: str | Path | None = None, verify_sources: bool = True):
        self.master_path = Path(master_path).resolve()
        if root is None:
            root = next((p for p in self.master_path.parents
                         if (p / "data/cyb_daily.csv").is_file()), None)
        if root is None:
            raise ProductionError("Cannot locate project root; supply root explicitly")
        self.root = Path(root).resolve()
        self.checks: list[dict[str, Any]] = []
        self.warnings: list[dict[str, Any]] = []
        self.dependencies: dict[str, str] = {}
        try:
            self.master = json.loads(self.master_path.read_text(encoding="utf-8-sig"))
            self._compile(csv_path, verify_sources)
        except ProductionError:
            raise
        except (KeyError, TypeError, ValueError, OSError) as error:
            raise ProductionError(f"Invalid production master: {error}") from error

    def _path(self, relative: str, context: str) -> Path:
        if not isinstance(relative, str) or not relative:
            raise ProductionError(f"Missing file path for {context}")
        path = (self.root / relative).resolve()
        if not path.is_relative_to(self.root):
            raise ProductionError(f"Source path escapes project root: {context}")
        if not path.is_file():
            raise ProductionError(f"Missing source file for {context}: {relative}")
        self.dependencies[path.relative_to(self.root).as_posix()] = _hash(path)
        return path

    def _sources(self, source_ids: set[str], verify: bool) -> None:
        self.sources = self.master["sources"]
        self._source_text: dict[str, str] = {}
        self._source_raw: dict[str, str] = {}
        allowed = {"local_market_data", "editorial_copy", "user_supplied_local_archive",
                   "supplied_documentary_A"}
        supplied_facts: dict[str, dict[str, Any]] = {}
        if verify and any(self.sources.get(s, {}).get("kind") == "supplied_documentary_A" for s in source_ids):
            fact_path = self._path("data/research/full_film_facts_v1.json", "original documentary eligibility")
            supplied_facts = {c["id"]: c for c in json.loads(fact_path.read_text(encoding="utf-8"))["claims"]}
        for source_id in sorted(source_ids):
            if source_id not in self.sources:
                raise ProductionError(f"Unregistered selected source: {source_id}")
            source = self.sources[source_id]
            if source.get("id") != source_id or source.get("kind") not in allowed:
                raise ProductionError(f"Unknown evidence class or mismatched source ID: {source_id}")
            if not verify:
                continue
            if source["kind"] == "editorial_copy":
                continue
            path = self._path(source.get("document", source.get("evidence", {}).get("document")), source_id)
            if source["kind"] in {"local_market_data", "user_supplied_local_archive"}:
                expected = source.get("sha256")
                if not isinstance(expected, str) or not re.fullmatch(r"[a-f0-9]{64}", expected):
                    raise ProductionError(f"Selected source needs a SHA-256 digest: {source_id}")
                if _hash(path) != expected:
                    raise ProductionError(f"Source hash differs from selected input: {source_id}")
            if source["kind"] == "supplied_documentary_A":
                evidence = source.get("evidence", {})
                if not evidence.get("supplied_document_excerpts"):
                    raise ProductionError(f"Supplied fact lacks its documentary excerpt: {source_id}")
                claim_id = source.get("claim_id")
                if source_id != f"U:{claim_id}" or supplied_facts.get(claim_id, {}).get("evidence_class") != "USER_A":
                    raise ProductionError(f"Supplied fact was not qualified as documentary A: {source_id}")
                body = "".join(path.read_text(encoding="utf-8-sig").split())
                if any("".join(excerpt.split()) not in body for excerpt in evidence["supplied_document_excerpts"]):
                    raise ProductionError(f"Supplied fact excerpt differs from original research: {source_id}")
            if source["kind"] == "user_supplied_local_archive":
                text_path = self._path(source.get("extracted_text"), f"{source_id} extracted body")
                self._source_text[source_id] = text_path.read_text(encoding="utf-8-sig")
                self._source_raw[source_id] = path.read_text(encoding="utf-8-sig", errors="replace")
        self.checks.append({"id": "selected_sources", "status": "passed" if verify else "skipped",
                            "source_count": len(source_ids), "new_online_verification": False})

    def _quotes(self, raw: dict[str, Any], source_ids: tuple[str, ...], verify: bool,
                context: str) -> None:
        quotes = raw.get("direct_quotes", [])
        declared = {q.get("text") for q in quotes}
        screen = "\n".join(raw["screen_lines"])
        on_screen = set(re.findall(r"“([^”]+)”|「([^」]+)」", screen))
        quoted_spans = {a or b for a, b in on_screen}
        if quoted_spans != declared:
            raise ProductionError(f"Screen quote differs from declared evidence: {context}")
        for quote in quotes:
            source_id, text = quote.get("source_id"), quote.get("text")
            if not isinstance(text, str) or not text or source_id not in source_ids:
                raise ProductionError(f"Direct quote lacks an assigned selected source: {context}")
            if self.sources[source_id].get("kind") != "user_supplied_local_archive":
                raise ProductionError(f"Direct quote requires a checked archived body: {context}")
            if text not in screen:
                raise ProductionError(f"Verified quote is not the text shown on screen: {context}")
            if verify:
                body = self._source_text[source_id]
                raw_body = html.unescape(re.sub(r"<[^>]+>", "", self._source_raw[source_id]))
                compact = lambda value: "".join(value.split())
                if text not in body or compact(text) not in compact(raw_body):
                    raise ProductionError(f"Quote not supported by its archived body: {context}")

    def _observation(self, raw: dict[str, Any], cutoff: str) -> tuple[str | None, int | None, str]:
        historical = raw.get("historical_date")
        precision = raw.get("date_precision", "day")
        bounds = _bounds(historical, precision)
        explicit = raw.get("market_anchor")
        if bounds and bounds[0] > cutoff:
            raise ProductionError(f"Selected event starts after film cutoff: {historical}")
        if explicit is not None:
            explicit = _date(explicit, "market anchor")
            if explicit > cutoff or (bounds and explicit > bounds[1]):
                raise ProductionError(f"Market anchor reveals a later observation: {historical} / {explicit}")
            index = self.market.index_for_date(explicit)
            return explicit, index, "explicit_market_observation"
        if bounds is None or bounds[1] < self.first_market_date:
            return None, None, "no_market_observation"
        if precision == "day":
            raise ProductionError(f"Dated event needs an explicit market anchor: {historical}")
        end = min(bounds[1], cutoff)
        candidates = [d for d in self.market_dates if bounds[0] <= d <= end]
        if not candidates:
            return None, None, "period_has_no_market_observation"
        observed = candidates[-1]
        self.warnings.append({"id": "period_observation_selected", "historical_date": historical,
                              "date_precision": precision, "observation_date": observed,
                              "event_market_anchor": None,
                              "note": "Editorial period-end observation; not an exact event date."})
        return observed, self.market.index_for_date(observed), "period_end_observation_not_event_day"

    def _metrics(self, node: dict[str, Any]) -> None:
        for metric in node.get("metrics", []):
            if metric["kind"] == "interval_return":
                first, last = metric["start_date"], metric["end_date"]
            elif metric["kind"] == "daily_return":
                first, last = metric["previous_date"], metric["date"]
                if self.market.index_for_date(last) - self.market.index_for_date(first) != 1:
                    raise ProductionError(f"Daily return does not use prior trading day: {node['id']}")
            else:
                raise ProductionError(f"Unsupported production metric: {metric.get('kind')}")
            a, b = self.market.index_for_date(first), self.market.index_for_date(last)
            if first > last or last > self.cutoff:
                raise ProductionError(f"Metric range outside production chronology: {node['id']}")
            value = (float(self.market.close[b]) / float(self.market.close[a]) - 1) * 100
            if abs(value - float(metric["value_pct"])) > 0.000001:
                raise ProductionError(f"Metric differs from the frozen CSV: {node['id']}")
            display = f"{value:+.2f}%".replace("-", "−")
            if metric.get("display_pct") != display:
                raise ProductionError(f"Metric display has the wrong precision or value: {node['id']}")

    def _compile(self, csv_path: str | Path | None, verify: bool) -> None:
        video = self.master["video"]
        self.fps = int(video["fps"])
        self.duration_seconds = float(video["duration_seconds_estimate"])
        self.total_frames = int(video["frame_count_plan"])
        if self.fps <= 0 or self.total_frames < 2 or self.duration_seconds <= 0:
            raise ProductionError("Film requires positive duration/fps and at least two frames")
        if self.total_frames != round(self.duration_seconds * self.fps):
            raise ProductionError("Film duration and frame count disagree")
        if video.get("audio") is not False:
            raise ProductionError("Current production must remain silent")
        self.cutoff = _date(self.master["data_cutoff"], "film cutoff")
        self.nodes = tuple(self.master["nodes"])
        if not self.nodes or len({n["id"] for n in self.nodes}) != len(self.nodes):
            raise ProductionError("Production nodes must exist and have unique IDs")
        used = {s for n in self.nodes for s in n.get("source_ids", [])}
        self._sources(used, verify)
        market_source = self.master["sources"].get("CSV", {})
        data_path = Path(csv_path).resolve() if csv_path else self._path(market_source.get("document"), "CSV")
        self.market = MarketData(data_path)
        if verify and _hash(data_path) != market_source.get("sha256"):
            raise ProductionError("Explicit market CSV differs from the frozen source hash")
        self.market_dates = tuple(d.strftime("%Y-%m-%d") for d in self.market.dates)
        self.first_market_date = self.market_dates[0]
        if self.market_dates[-1] != self.cutoff:
            raise ProductionError("Frozen market endpoint differs from the film cutoff")
        if market_source.get("rows") is not None and len(self.market_dates) != market_source["rows"]:
            raise ProductionError("Frozen market row count differs from its source declaration")
        if market_source.get("date_range") != [self.market_dates[0], self.market_dates[-1]]:
            raise ProductionError("Frozen market date range differs from its source declaration")
        self.checks.append({"id": "frozen_market", "status": "passed", "rows": len(self.market_dates),
                            "first_date": self.first_market_date, "last_date": self.cutoff})
        beats: list[CompiledBeat] = []
        previous_frame = 0
        main_index: int | None = None
        global_observation: str | None = None
        album_mode = False
        transition_kinds = {"explicit_rewind", "context_insert", "declared_album_recap", "return_from_album"}
        entry_exit = float(self.master.get("timing_policy", {}).get("entry_exit_budget_seconds_per_beat_max", 1))
        for node in self.nodes:
            node_id = node["id"]
            if node.get("selection_status") != "selected_in_script_v1":
                raise ProductionError(f"Unsupported selection status for node: {node_id}")
            if node["start_frame"] != previous_frame or node["end_frame_exclusive"] <= previous_frame:
                raise ProductionError(f"Node gap, overlap or nonpositive duration: {node_id}")
            self._time_fields(node, node["start_frame"], node["end_frame_exclusive"], node_id)
            sources = tuple(node.get("source_ids", []))
            if not sources:
                raise ProductionError(f"Selected node has no evidence assignment: {node_id}")
            jump = node.get("declared_time_jump")
            if jump:
                kind = jump.get("kind")
                if kind not in transition_kinds:
                    raise ProductionError(f"Undeclared transition type: {node_id}")
                if node.get("role") == "main":
                    raise ProductionError(f"Main market progression cannot use a rewind: {node_id}")
                if kind == "explicit_rewind":
                    if jump.get("from") != global_observation:
                        raise ProductionError(f"Rewind source differs from current film history: {node_id}")
                    global_observation = _date(jump.get("to"), "rewind target")
                elif kind == "context_insert":
                    if jump.get("resume") != global_observation:
                        raise ProductionError(f"Context insertion does not authorize an outer rewind: {node_id}")
                elif kind == "declared_album_recap":
                    if jump.get("from") != global_observation:
                        raise ProductionError(f"Album recap starts from wrong market time: {node_id}")
                    global_observation = _date(jump.get("to"), "album recap target")
                    album_mode = True
                else:
                    if not album_mode:
                        raise ProductionError(f"Return from album without declared album: {node_id}")
                    global_observation = _date(jump.get("to"), "return target")
                    album_mode = False
            raw_beats = node.get("beats", [])
            if not raw_beats:
                raise ProductionError(f"Selected node has no reading beats: {node_id}")
            for beat_index, raw in enumerate(raw_beats):
                context = f"{node_id}/beat{beat_index + 1}"
                start, end = raw["start_frame"], raw["end_frame_exclusive"]
                if type(start) is not int or type(end) is not int or start != previous_frame or end <= start:
                    raise ProductionError(f"Beat gap, overlap or noninteger frame range: {context}")
                if end > node["end_frame_exclusive"]:
                    raise ProductionError(f"Beat exceeds its node: {context}")
                self._time_fields(raw, start, end, context)
                lines = raw.get("screen_lines")
                if not isinstance(lines, list) or not lines or any(not isinstance(s, str) or not s.strip() for s in lines):
                    raise ProductionError(f"Selected beat needs nonempty screen copy: {context}")
                self._quotes(raw, sources, verify, context)
                observation, index, policy = self._observation(raw, self.cutoff)
                if observation is not None:
                    if node.get("role") == "main":
                        if main_index is not None and index < main_index:
                            raise ProductionError(f"Main market clock reverses: {context}")
                        main_index = index
                    if global_observation is not None and observation < global_observation:
                        raise ProductionError(f"Historical reversal lacks an explicit scene jump: {context}")
                    global_observation = observation
                stable = raw.get("planned_stable_seconds_min")
                if stable is None:
                    stable = max(0, (end-start)/self.fps-entry_exit)
                    self.warnings.append({"id": "reading_budget_default", "beat": context,
                                          "stable_seconds_min": stable})
                stable_frames = round(float(stable) * self.fps)
                if stable_frames < 1 or stable_frames > end-start:
                    raise ProductionError(f"Invalid stable-reading budget: {context}")
                chars = sum(len(re.sub(r"\W", "", s, flags=re.UNICODE)) for s in lines)
                if chars / (stable_frames/self.fps) > 12:
                    self.warnings.append({"id": "reading_density_review", "beat": context,
                                          "characters_per_stable_second": round(chars/(stable_frames/self.fps), 2)})
                hud_label = raw.get("hud_label", "当日收盘")
                bounds = _bounds(raw.get("historical_date"), raw.get("date_precision", "day"))
                if raw.get("date_precision", "day") == "day" and bounds and observation and observation < bounds[0]:
                    if hud_label != "上一交易日":
                        raise ProductionError(f"Earlier market observation needs prior-day HUD label: {context}")
                    event_index = self.market.index_for_date(bounds[0], strict=False)
                    if self.market_dates[event_index] == bounds[0]:
                        event_index -= 1
                    if index != event_index:
                        raise ProductionError(f"Prior-day HUD must use the latest completed trading day: {context}")
                beats.append(CompiledBeat(node_id, beat_index, node["phase_id"], node["role"], node["title"],
                    start, end, tuple(lines), raw.get("source_line"), sources,
                    raw.get("historical_date"), raw.get("date_precision", "day"), raw.get("market_anchor"),
                    observation, index, policy, hud_label, stable_frames,
                    tuple(_source_dates(s, self.sources[s]) for s in sources), raw.get("implementation_note", "")))
                previous_frame = end
            if previous_frame != node["end_frame_exclusive"]:
                raise ProductionError(f"Beats do not cover node: {node_id}")
            self._metrics(node)
        if previous_frame != self.total_frames:
            raise ProductionError("Scenes do not cover the complete planned film")
        self.beats = tuple(beats)
        self._starts = tuple(b.start_frame for b in self.beats)
        self.checks.extend([
            {"id": "integer_frame_coverage", "status": "passed", "frames": self.total_frames,
             "nodes": len(self.nodes), "beats": len(self.beats)},
            {"id": "main_history_and_explicit_jumps", "status": "passed"},
            {"id": "quotes_and_metrics", "status": "passed" if verify else "source_bodies_skipped"},
        ])

    def _time_fields(self, raw: dict[str, Any], start: int, end: int, context: str) -> None:
        if abs(float(raw["start_seconds"])*self.fps-start) > 1e-8:
            raise ProductionError(f"Second/frame start differs: {context}")
        if abs(float(raw["end_seconds_exclusive"])*self.fps-end) > 1e-8:
            raise ProductionError(f"Second/frame end differs: {context}")
        if abs(float(raw["duration_seconds"])*self.fps-(end-start)) > 1e-8:
            raise ProductionError(f"Duration differs from frame range: {context}")

    def state_at_frame(self, frame_number: int) -> ProductionFrameState:
        if type(frame_number) is not int or not 0 <= frame_number < self.total_frames:
            raise IndexError(f"Film frame outside 0..{self.total_frames-1}: {frame_number}")
        beat = self.beats[bisect_right(self._starts, frame_number)-1]
        has_market = beat.observation_index is not None
        show_hud = has_market and beat.role in {"opening", "main", "closing"}
        show_chart = has_market and beat.role in {"opening", "main", "closing"}
        local = frame_number-beat.start_frame
        return ProductionFrameState(frame_number, beat.node_id, beat.beat_index, beat.phase_id, beat.role,
            local, local/max(1, beat.end_frame_exclusive-beat.start_frame-1), beat.screen_lines,
            beat.source_line, beat.source_ids, beat.historical_date, beat.date_precision, beat.market_anchor,
            beat.observation_date if has_market else None,
            float(self.market.close[beat.observation_index]) if has_market else None,
            beat.observation_index, show_hud, show_chart, beat.hud_label, beat.observation_policy)

    def to_dict(self) -> dict[str, Any]:
        def source_dates(context: SourceDateContext) -> dict[str, Any]:
            return {"source_id": context.source_id, "publication_date": context.publication_date,
                    "published_at": context.published_at, "event_dates": list(context.event_dates),
                    "effective_dates": list(context.effective_dates), "page_date": context.page_date}
        scenes = []
        for node in self.nodes:
            compiled = [b for b in self.beats if b.node_id == node["id"]]
            scenes.append({"id": node["id"], "phase_id": node["phase_id"], "role": node["role"],
                "title": node["title"], "start_frame": node["start_frame"],
                "end_frame_exclusive": node["end_frame_exclusive"],
                "declared_time_jump": node.get("declared_time_jump"),
                "beats": [{"id": b.id, "beat_index": b.beat_index,
                    "start_frame": b.start_frame, "end_frame_exclusive": b.end_frame_exclusive,
                    "screen_lines": list(b.screen_lines), "source_line": b.source_line,
                    "source_ids": list(b.source_ids), "historical_date": b.historical_date,
                    "date_precision": b.date_precision, "event_market_anchor": b.market_anchor,
                    "market_observation_date": b.observation_date,
                    "market_observation_index": b.observation_index,
                    "market_observation_policy": b.observation_policy, "hud_label": b.hud_label,
                    "stable_frames_min": b.stable_frames_min,
                    "source_date_context": [source_dates(c) for c in b.source_date_context],
                    "implementation_note": b.implementation_note} for b in compiled]})
        return {"schema_version": "compiled_film_v1", "status": "compiled_not_rendered",
                "source_master": str(self.master_path), "master_sha256": _hash(self.master_path),
                "video": self.master["video"], "data_cutoff": self.cutoff,
                "market_clock_policy": "beat_anchor_hold_v1_not_continuous_progression",
                "layout_review": "pending_actual_layout_and_playback",
                "frame_interval": "[start_frame,end_frame_exclusive)",
                "node_count": len(self.nodes), "beat_count": len(self.beats),
                "dependencies": dict(sorted(self.dependencies.items())),
                "checks": self.checks, "warnings": self.warnings, "scenes": scenes}
