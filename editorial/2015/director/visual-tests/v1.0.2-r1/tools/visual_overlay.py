"""Phone-readable display cuts for the V1.0.2 representative clips."""

from __future__ import annotations

import re

from chinext_v6.drawing import C, rgba, smooth
from chinext_v6.editorial_overlay import _draw_links, _draw_orbit


TEXT = C["text"]
SECONDARY = (184, 204, 216)
MUTED = (147, 176, 193)
HAIRLINE = (125, 169, 192)

# Labels use the approved cues, with shorter retired headings for the same
# facts. The earliest event never becomes primary again inside the sequence.
POLICY_SEQUENCE = {
    "V102-B09-01": ("7/4 券商承诺", "7/4 暂缓发行", "7/5 流动性支持"),
    "V102-B09-02": ("7/4 券商承诺", "7/4 暂缓发行", "7/5 流动性支持"),
    "V102-B09-03": ("7/4 券商承诺", "7/4 暂缓发行", "7/5 流动性支持"),
}

VALUE = re.compile(r"[+−-]?(?:\d{1,3}(?:,\d{3})+|\d+)\.\d{2}%?")


class Caption:
    def __init__(self, drawer, layer, alpha):
        self.drawer = drawer
        self.pen = drawer._pen(layer, True)
        self.alpha = alpha
        self.lines = []
        self.roles = []

    def text(self, value, x, y, size, *, role, color=TEXT, opacity=1, width=520, bold=False, center=False):
        if not value or opacity <= 0:
            return
        font = self.drawer.fonts.get(size, bold)
        while self.pen.textlength(value, font) > width and size > 18:
            size -= 1
            font = self.drawer.fonts.get(size, bold)
        if self.pen.textlength(value, font) > width:
            raise ValueError(f"Visual test text exceeds its {width}-unit band: {value}")
        identifier = f"v102_caption_{len(self.lines)}"
        self.pen.text((x, y), value, font, rgba(color, self.alpha * opacity),
                      anchor="mt" if center else "lt", id=identifier, role=role)
        self.lines.append(value)
        self.roles.append({"id": identifier, "role": role, "size_logical": size,
                           "phone_size_px": round(size * 390 / 720, 2),
                           "alpha": round(self.alpha * opacity, 4)})

    def line(self, points, color=HAIRLINE, opacity=.62, width=1):
        self.pen.line(points, rgba(color, self.alpha * opacity), width)

    def node(self, x, y, *, active=True, opacity=1):
        radius = 4 if active else 2.6
        fill = TEXT if active else HAIRLINE
        alpha = self.alpha * opacity
        self.pen.ellipse((x-radius, y-radius, x+radius, y+radius), fill=rgba(fill, alpha))
        if active:
            self.pen.ellipse((x-7, y-7, x+7, y+7), outline=rgba(HAIRLINE, alpha * .74), width=.8)


def _alpha(cue, frame):
    timing = cue["text_cue"]
    enter, fully_visible, end = (timing[key] for key in ("in_frame", "full_alpha_from_frame", "out_frame_exclusive"))
    if not enter <= frame < end:
        return 0.0
    exit_window = cue.get("camera_story_clock", {}).get("exit_window")
    if exit_window is not None and frame >= exit_window[0]:
        return smooth((exit_window[1] - 1 - frame) / max(1, exit_window[1] - exit_window[0] - 1))
    if frame >= fully_visible:
        return 1.0
    return .12 + .88 * smooth((frame - enter) / max(1, fully_visible - enter))


def _variant(cue):
    story = cue.get("camera_story_clock", {})
    if cue["beat_id"] == "B01" and story.get("intro_reveal"):
        return "intro_hook"
    if story.get("visual_variant"):
        return story["visual_variant"]
    event = cue.get("event_clock") or {}
    event_id = event.get("event_id")
    if event_id == "E-SEP-ETF-01":
        return "etf"
    if event_id == "E-SEP-TURNOVER-01":
        return "turnover"
    if cue["beat_id"] == "B13" and cue["shot_id"].endswith("-02"):
        return "pmi_dual_timeline"
    if cue["primary_focus"] == "L2_EVENT":
        return "policy"
    if cue["beat_id"] == "B01" or cue["beat_id"] == "B16" or cue["link_geometry"]["close_endpoints"]:
        return "range_or_key_point"
    return "market"


def _policy(caption, cue):
    timing = cue["text_cue"]
    lines = timing["lines"]
    is_sequence = cue["shot_id"] in POLICY_SEQUENCE
    caption.text(lines[0], 69, 166, 22, role="policy_date", color=SECONDARY, width=420)
    caption.text(timing.get("source_line"), 69, 197, 18, role="policy_source", color=MUTED, width=420)
    bodies = lines[1:]
    for index, value in enumerate(bodies):
        # The center is below the independent market HUD and above the chart.
        top = (219 if len(bodies) > 1 else 238) + 38 * index
        caption.text(value, 360, top, 32, role="policy_primary", width=520, bold=True, center=True)
    if not is_sequence:
        caption.line((90, 310, 630, 310), opacity=.58)
        return None

    active = int(cue["shot_id"].rsplit("-", 1)[-1]) - 1
    history = []
    labels = POLICY_SEQUENCE[cue["shot_id"]]
    xs = (115, 360, 605)
    caption.line((xs[0], 312, xs[active], 312), opacity=.49)
    for index, (x, text) in enumerate(zip(xs, labels, strict=True)):
        if index > active:
            continue
        retired = index != active
        opacity = .50 if retired else .94
        caption.node(x, 312, active=not retired, opacity=opacity)
        caption.text(text, x, 322, 17, role="policy_retired" if retired else "policy_current_marker",
                     color=MUTED if retired else SECONDARY, opacity=opacity, width=160, center=True)
        history.append({"text": text, "role": "retired" if retired else "active", "opacity": opacity,
                        "displayed_alpha": round(caption.alpha * opacity, 4)})
    return {"entries": history, "active_index": active, "layers": len(history), "primary_count": 1}


def _pmi(caption, cue):
    event = cue.get("event_clock") or {}
    nodes = event.get("timeline_points", [
        {"time": "09:30", "label": "A股开盘", "role": "market_open"},
        {"time": "09:43:10", "label": "财新网页刊发", "role": "publisher_webpage_timestamp"},
    ])
    if [(point["time"], point["label"]) for point in nodes] != [("09:30", "A股开盘"), ("09:43:10", "财新网页刊发")]:
        raise ValueError("Dual PMI timeline differs from approved copy")
    context = cue["camera_story_clock"].get("context_label", "2015.08.21 · 同日时间线")
    caption.text(context, 69, 166, 22, role="timeline_date", color=SECONDARY, width=420)
    caption.text("财新8月制造业PMI初值", 69, 210, 28, role="pmi_label", width=345, bold=True)
    caption.text("47.1", 429, 199, 46, role="pmi_value", color=C["gold_light"], width=124, bold=True)
    caption.line((72, 264, 642, 264), opacity=.67)
    for x, point in zip((82, 385), nodes, strict=True):
        caption.node(x + 5, 264)
        caption.text(point["time"], x, 279, 26, role="timeline_time", width=190, bold=True)
        caption.text(point["label"], x, 314, 21, role="timeline_node_label", color=SECONDARY, width=230)
    return nodes


def _etf(caption):
    caption.text("易方达创业板ETF份额", 69, 164, 29, role="metric_title", width=495, bold=True)
    caption.text("观察区间 9/7—9/22", 69, 202, 22, role="etf_observation_window", color=TEXT, width=244)
    caption.text("报道 2015.09.25", 333, 202, 22, role="etf_report_date", color=TEXT, width=213)
    caption.line((318, 202, 318, 226), opacity=.48)
    caption.text("12.37亿份", 69, 240, 29, role="etf_start_shares", width=168, bold=True)
    caption.text("18.07亿份", 276, 240, 29, role="etf_end_shares", width=168, bold=True)
    caption.text("+46.08%", 452, 232, 37, role="etf_share_change", color=C["gold_light"], width=165, bold=True)
    full = 143
    bar_from_width = full * (12.37 / 18.07)
    caption.line((70, 289, 70 + full, 289), opacity=.24, width=4)
    caption.line((70, 289, 70 + bar_from_width, 289), opacity=.77, width=4)
    caption.line((277, 289, 277 + full, 289), opacity=.87, width=4)
    caption.text("据中国证券报援引深交所数据", 69, 308, 23, role="etf_source", color=SECONDARY, width=540)
    return {"metric_id": "E-SEP-ETF-01", "evidence_tier": "T2", "observation_window": ["2015-09-07", "2015-09-22"],
            "publication_date": "2015-09-25", "bar_width_logical": [bar_from_width, full]}


def _turnover(caption):
    caption.text("2015.09.28 · 收盘后", 69, 164, 25, role="turnover_calendar", color=TEXT, width=470)
    caption.text("沪深两市成交额", 69, 200, 29, role="metric_title", width=480, bold=True)
    caption.text("4,044", 68, 233, 58, role="turnover_value", color=C["gold_light"], width=230, bold=True)
    caption.text("亿元", 252, 266, 27, role="turnover_unit", color=SECONDARY, width=130)
    caption.text("同期报道：中国新闻网、21世纪经济报道", 69, 308, 23, role="turnover_source", color=SECONDARY, width=555)
    return {"metric_id": "E-SEP-TURNOVER-01", "evidence_tier": "T2", "date": "2015-09-28",
            "scope": "沪深两市成交额", "full_day_only": True}


def _intro_fade(frame, start, full):
    return 0.0 if frame < start else 1.0 if frame >= full else .12 + .88 * smooth((frame - start) / (full - start))


def _intro(caption, cue, frame):
    plan = cue["camera_story_clock"]["intro_reveal"]
    date_alpha = _intro_fade(frame, plan["date_in_frame"], plan["date_full_frame"])
    value_alpha = _intro_fade(frame, plan["value_in_frame"], plan["value_full_frame"])
    date_line, reading_line = cue["text_cue"]["lines"]
    match = VALUE.search(reading_line)
    if match is None:
        raise ValueError("Flash-forward requires its immutable close reading")
    caption.alpha = 1.0
    caption.text(date_line, 69, 165, 23, role="flash_forward", color=SECONDARY, width=470, opacity=date_alpha)
    caption.text(reading_line[:match.start()].rstrip(), 69, 201, 28, role="key_point_qualifier", color=TEXT,
                 width=485, opacity=date_alpha, bold=True)
    caption.text(match[0], 68, 239, 60, role="market_key_point", color=C["gold_light"], width=420,
                 opacity=value_alpha, bold=True)
    source_alpha = value_alpha if frame >= plan["source_in_frame"] else 0.0
    caption.text(cue["text_cue"].get("source_line"), 69, 315, 19, role="market_source", color=SECONDARY,
                 width=470, opacity=source_alpha)
    return {"date_alpha": round(date_alpha, 4), "value_alpha": round(value_alpha, 4),
            "source_alpha": round(source_alpha, 4), "qualifier_visible": date_alpha > 0,
            "value_visible": value_alpha > 0, "source_visible": source_alpha > 0,
            "value_in_frame": plan["value_in_frame"], "value_full_frame": plan["value_full_frame"]}


def _market(caption, cue, variant):
    timing = cue["text_cue"]
    lines = timing["lines"]
    if cue.get("copy_is_hud_only") or not lines:
        return
    if variant == "range_or_key_point":
        candidate = lines[1] if cue["beat_id"] == "B01" or len(lines) > 1 and lines[1].startswith("+") else lines[0]
        match = VALUE.search(candidate)
        if match is not None:
            prefix, suffix = candidate[:match.start()].strip(" ·"), candidate[match.end():].strip(" ·")
            others = [line for line in lines if line != candidate]
            qualifier = prefix or others.pop(0)
            if cue["beat_id"] == "B01":
                caption.text(others.pop(0), 69, 165, 22, role="flash_forward", color=SECONDARY, width=495)
            caption.text(qualifier, 69, 195 if cue["beat_id"] == "B01" else 166, 22,
                         role="key_point_qualifier", color=SECONDARY, width=485)
            caption.text(match[0], 68, 225 if cue["beat_id"] == "B01" else 201, 64,
                         role="market_key_point", color=C["gold_light"], width=420, bold=True)
            if suffix:
                caption.text(suffix, 376, 230, 26, role="key_point_suffix", color=C["gold_light"], width=160, bold=True)
            top = 314 if cue["beat_id"] == "B01" else 281
            for index, value in enumerate(others[:2]):
                caption.text(value, 69, top + 29 * index, 22, role="market_basis", color=SECONDARY, width=560)
            if not others:
                caption.text(timing.get("source_line"), 69, top, 18, role="market_source", color=MUTED, width=550)
            return

    if cue["shot_id"] == "V102-B02-01":
        caption.text(lines[0], 69, 166, 25, role="rewind_to", color=SECONDARY, width=455, bold=True)
        caption.text(lines[1], 69, 214, 36, role="market_context", width=492, bold=True)
        return
    for index, text in enumerate(lines[:3]):
        caption.text(text, 69, 172 + 42 * index, 28 if index == 0 else 22,
                     role="market_context" if index == 0 else "market_basis",
                     color=TEXT if index == 0 else SECONDARY, width=496, bold=index == 0)


def draw_visual_overlay(image, drawer, state, cue, global_frame, t2_state=None) -> dict:
    """Draw one cue at its exact global frame and report what actually appeared."""
    story = cue.get("camera_story_clock", {})
    mode = next((window["mode"] for window in story.get("focus_windows", [])
                 if window["start_frame"] <= global_frame < window["end_frame_exclusive"]), None)
    variant = _variant(cue)
    alpha = _alpha(cue, global_frame)
    layer = drawer._new()
    first_box = len(drawer.text_boxes)
    caption = Caption(drawer, layer, alpha)
    policy_sequence = timeline = market_structure = intro = orbit = None
    if variant == "intro_hook":
        intro = _intro(caption, cue, global_frame)
    elif alpha > 0:
        if variant == "policy":
            policy_sequence = _policy(caption, cue)
        elif variant == "pmi_dual_timeline":
            timeline = _pmi(caption, cue)
        elif variant == "etf":
            market_structure = _etf(caption)
        elif variant == "turnover":
            market_structure = _turnover(caption)
        else:
            _market(caption, cue, variant)
    caption_boxes = drawer.text_boxes[first_box:]
    if cue["link_geometry"]["event_line_has_arrowhead"] is not False:
        raise ValueError("Event-to-price arrows are prohibited")
    geometry = {}
    if intro is not None and intro["value_visible"]:
        geometry = _draw_links(drawer, drawer._pen(layer, True), state, cue, intro["value_alpha"], outgoing=False)
        orbit = _draw_orbit(image, layer, drawer, state, cue["earth_orbit"])
    elif variant not in {"intro_hook", "policy", "pmi_dual_timeline", "etf", "turnover"}:
        geometry = _draw_links(drawer, drawer._pen(layer, True), state, cue, alpha, outgoing=False)
    image.alpha_composite(layer)
    return {
        "visual_variant": variant, "presentation": variant, "mode": mode, "primary_focus": cue["primary_focus"],
        "caption_alpha": round(alpha, 4), "text_visible": bool(caption.lines), "caption_lines": caption.lines,
        "caption_boxes": caption_boxes, "text_roles": caption.roles, "policy_sequence": policy_sequence,
        "timeline_points": timeline, "market_structure": market_structure, "geometry": geometry,
        "asset_photo_visible": False, "intro_reveal": intro, "orbit": orbit,
    }
