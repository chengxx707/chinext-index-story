"""Draw the released editorial cues over the existing OHLC compositor."""

from __future__ import annotations

import re

from PIL import Image, ImageChops, ImageOps

from .drawing import C, clamp, rgba, smooth

CHART_LEFT, CHART_RIGHT = 26, 704
CHART_TOP, CHART_BOTTOM = 252, 846
_HERO_SHOTS = {5, 6, 9, 15, 25, 26, 27}
_LEADING_QUALIFIER = {1, 2, 3, 4, 7, 8, 10, 11, 12, 14, 16, 17, 18, 19, 20, 22, 23}
_TRAILING_QUALIFIER = {8, 10, 23, 24}
_FONT_PX = {"hero_value": 112, "event_main": 54, "date_and_qualifier": 36, "short_source": 30}

EVENT_ROLES = {
    "effective_date": "生效",
    "publisher_timestamp": "刊发",
    "historical_observation": "历史观察",
    "public_statement": "公开表述",
    "retrospective_statistic": "事后回顾",
    "weekend_announcement": "周末公布",
    "macro_context": "同期背景",
    "documentary_scene": "同期现场",
    "official_website_timestamp": "官网公布",
}


def _event_label(clock: dict | None) -> str | None:
    if clock is None:
        return None
    if clock.get("date_is_market_observation_anchor"):
        # GPT2015-08's June 18 candle is an observation anchor, while
        # the source supports a June background label at month precision.
        return clock["observation_label"]
    day = clock["date"].replace("-", ".")
    time = f" {clock['time']}" if clock.get("time") else ""
    return f"{day}{time} · {EVENT_ROLES[clock['role']]}"


def _caption_alpha(frame: int, text: dict) -> float:
    if not text["in_frame"] <= frame < text["out_frame_exclusive"]:
        return 0.0
    ramp = text["full_alpha_from_frame"] - text["in_frame"]
    if ramp <= 0:
        return 1.0
    return .12 + .88 * smooth((frame - text["in_frame"]) / ramp)


def _shot(cue: dict) -> int:
    return int(cue["shot_id"].rsplit("-", 1)[-1])


def _style(cue: dict) -> str:
    fallback = "documentary_photo" if cue["photo_asset_id"] else (
        "extremum_or_interval" if _shot(cue) in _HERO_SHOTS else "policy_or_event"
    )
    return cue.get("visual_revision", {}).get("presentation", fallback)


def is_hero(cue: dict) -> bool:
    return _style(cue) == "extremum_or_interval"


def _exit_frames(cue: dict) -> int:
    return int(cue.get("visual_revision", {}).get("exit_frames", 6))


def outgoing_opacity(cue: dict, frame: int) -> float:
    """Continue the overlay across a join without reducing full-reading time."""
    elapsed = frame - cue["end_frame_exclusive"]
    duration = _exit_frames(cue)
    if cue["photo_asset_id"] or not 0 <= elapsed < duration:
        return 0.0
    return 1 - smooth((elapsed + 1) / (duration + 1))


def _fit_font(drawer, pen, text: str, nominal_size: int, height: int, *, width: int, bold: bool, minimum=13):
    for size in range(nominal_size, minimum - 1, -1):
        font = drawer.fonts.get(size, bold)
        if pen.textlength(text, font) <= width and font.getbbox(text, anchor="lt")[3] <= height * drawer.s:
            return font
    raise ValueError(f"Editorial text does not fit the reserved caption area: {text}")


def _caption_parts(cue: dict, label: str | None) -> tuple[list[str], list[str], list[str]]:
    lines = cue["text_cue"]["lines"]
    shot = _shot(cue)
    if is_hero(cue):
        qualifiers, main, supporting = [lines[0]], [lines[1]], list(lines[2:])
        if shot == 9:
            prefix, value = lines[1].rsplit(" ", 1)
            main, supporting = [value], [prefix, *supporting]
        return qualifiers, main, supporting

    qualifiers, main, supporting = [], list(lines), []
    if shot in _LEADING_QUALIFIER:
        qualifiers.append(main.pop(0))
    if shot in _TRAILING_QUALIFIER:
        supporting.append(main.pop())
    if label and (not qualifiers or shot in {3, 18}):
        qualifiers.insert(0, label)
        if cue["photo_asset_id"]:
            date = cue["event_clock"]["date"].replace("-", ".")
            main[0] = main[0].removeprefix(f"{date} · ")
    return qualifiers, main, supporting


def _break_main(drawer, pen, line: str, nominal: int) -> list[str]:
    font = drawer.fonts.get(nominal, True)
    if pen.textlength(line, font) <= 435:
        return [line]
    pieces = re.findall(r"[A-Za-z0-9.,+−%≥/]+|.", line)
    if len(pieces) < 2:
        return [line]
    # Keep decimal values and their suffixes intact while adjusting the layout.
    point = min(range(1, len(pieces)), key=lambda i:
        abs(pen.textlength("".join(pieces[:i]), font) - pen.textlength("".join(pieces[i:]), font)))
    return ["".join(pieces[:point]).rstrip(), "".join(pieces[point:]).lstrip()]


def _caption(drawer, pen, cue: dict, label: str | None, alpha: float) -> list[str]:
    font_px = {**_FONT_PX, **cue.get("visual_revision", {}).get("target_font_px_at_1080", {})}
    logical = {kind: round(target * 720 / 1080) for kind, target in font_px.items()}
    qualifiers, main, supporting = _caption_parts(cue, label)
    hero = is_hero(cue)
    major = "hero_value" if hero else "event_main"
    if len(main) == 1 and not hero:
        if _shot(cue) == 24 and "流动性" in main[0]:
            leading, following = main[0].split("流动性", 1)
            main = [leading + "流动性", following]
        else:
            main = _break_main(drawer, pen, main[0], logical[major])
    actual = []

    def line(text: str, y: int, kind: str, height: int, color, *, bold=False, width=435):
        font = _fit_font(drawer, pen, text, logical[kind], height, width=width, bold=bold)
        pen.text((70, y), text, font, rgba(color, alpha), anchor="lt",
                 id=f"editorial_{kind}_{len(actual)}", role=kind)
        actual.append(text)

    y = 161
    for text in qualifiers:
        line(text, y, "date_and_qualifier", 25, C["gold"], bold=hero)
        y += 28
    y += 3
    for text in main:
        line(text, y, major, 78 if hero else 41, C["gold_light"] if hero else C["text"], bold=True)
        y += 80 if hero else 44
    if supporting:
        line(" · ".join(supporting), y, "date_and_qualifier", 26, C["text"], width=605)
        y += 28
    source = cue.get("visual_revision", {}).get("source_short") or cue["text_cue"].get("source_line")
    if source:
        if _shot(cue) == 24:
            source = "央广网｜受访者观点"
        line(source, max(y+1, 299), "short_source", 26, (183, 199, 209), width=605)
    return actual


def _baseline_caption(drawer, pen, text: dict, label: str | None, alpha: float) -> list[str]:
    """Keep the accepted prior version reproducible for same-frame comparisons."""
    actual = []

    def line(value, y, nominal, height, color, identifier, role, bold=False):
        font = _fit_font(drawer, pen, value, nominal, height, width=435, bold=bold, minimum=9)
        pen.text((70, y), value, font, rgba(color, alpha), anchor="lt", id=identifier, role=role)
        actual.append(value)

    if label:
        line(label, 161, 11, 13, C["gold"], "editorial_event_clock", "event_clock", True)
    lines = text["lines"]
    top, interval, nominal = (176, 21, 19) if len(lines) >= 3 else (177, 27, 23)
    for i, value in enumerate(lines):
        line(value, top + i * interval, nominal, interval - 2, C["text"],
             f"editorial_copy_{i}", "editorial_copy", i == 0)
    if source := text.get("source_line"):
        line(source, 238, 11, 13, (164, 181, 194), "editorial_source", "source")
    return actual


def _point(drawer, state, day: str, price: float) -> tuple[float, float] | None:
    index = drawer.model.market.index_for_date(day)
    if index > state.current_index:
        return None
    x, y = drawer._coords(state)
    return x(index), y(price)


def _chart_top(drawer):
    return getattr(drawer, "editorial_chart_top", CHART_TOP)


def _visible(drawer, point: tuple[float, float] | None) -> bool:
    return point is not None and (
        CHART_LEFT <= point[0] <= CHART_RIGHT and _chart_top(drawer) <= point[1] <= CHART_BOTTOM
    )


def _dot(pen, point: tuple[float, float], alpha: float, *, radius: float = 3) -> None:
    x, y = point
    pen.ellipse((x-radius, y-radius, x+radius, y+radius),
                fill=rgba(C["gold_light"], alpha), outline=rgba(C["gold"], alpha), width=.8)


def _endpoint_date(drawer, pen, point: tuple[float, float], day: str, alpha: float, ordinal: int) -> str:
    x, y = point
    text = day[5:].replace("-", ".")
    font = drawer.fonts.get(17)
    half_width = pen.textlength(text, font) / 2
    x = clamp(x, CHART_LEFT + half_width, CHART_RIGHT - half_width)
    y = y - 28 if y - 28 >= _chart_top(drawer) else y + 10
    pen.text((x, y), text, font, rgba(C["gold_light"], alpha), anchor="mt",
             id=f"editorial_endpoint_{ordinal}", role="endpoint_date")
    return text


def _draw_links(drawer, pen, state, cue: dict, alpha: float, *, outgoing: bool) -> dict:
    link = cue["link_geometry"]
    anchor = cue["primary_anchor"]
    hit = state.frame_number >= anchor["hit_frame"]
    anchor_xy = _point(drawer, state, anchor["date"], anchor["value"]) if hit else None
    diag = {"anchor": anchor_xy, "anchor_visible": _visible(drawer, anchor_xy),
            "close_endpoints": [], "close_endpoints_visible": False, "close_endpoint_markers": 0,
            "close_link_progress": 0.0, "close_link_complete": False,
            "endpoint_labels": [],
            "wick_anchor": None, "wick_visible": False,
            "gap": None, "statistics_bracket": None, "event_leader_visible": False}
    if not hit:
        return diag
    line_alpha = alpha if outgoing else max(.40, alpha)
    for endpoint in link["close_endpoints"]:
        diag["close_endpoints"].append(_point(drawer, state, endpoint["date"], endpoint["value"]))
    diag["close_endpoints_visible"] = (
        len(diag["close_endpoints"]) == 2 and all(_visible(drawer, point) for point in diag["close_endpoints"])
    )
    if diag["close_endpoints_visible"]:
        first, last = diag["close_endpoints"]
        elapsed = (state.frame_number - anchor["hit_frame"]) / drawer.model.fps
        end_visible = elapsed >= 1 / 6
        reveal = smooth((elapsed - .30) / .60)
        if reveal:
            reached = tuple(a+(b-a)*reveal for a, b in zip(first, last))
            pen.line((first, reached), rgba(C["gold"], line_alpha * .76), 1.3)
        _dot(pen, first, line_alpha)
        if end_visible:
            _dot(pen, last, line_alpha)
        if reveal == 1.0 and hasattr(drawer, "editorial_chart_top"):
            diag["endpoint_labels"] = [
                _endpoint_date(drawer, pen, point, endpoint["date"], line_alpha, index)
                for index, (point, endpoint) in enumerate(zip((first, last), link["close_endpoints"]))
            ]
        diag.update(close_endpoint_markers=2 if end_visible else 1,
                    close_link_progress=reveal, close_link_complete=reveal == 1.0)

    wick = link.get("intraday_anchor")
    if wick:
        xy = _point(drawer, state, wick["date"], wick["value"])
        diag.update(wick_anchor=xy, wick_visible=_visible(drawer, xy))
        if _visible(drawer, xy):
            x, y = xy
            pen.line((x-9, y, x+9, y), rgba(C["gold"], line_alpha), 1)
            _dot(pen, xy, line_alpha)

    if gap := link.get("gap"):
        previous = _point(drawer, state, gap["previous_date"], gap["previous_low"])
        current = _point(drawer, state, gap["current_date"], gap["current_high"])
        visible = (
            _visible(drawer, previous) and _visible(drawer, current)
            and previous[0] < current[0] and previous[1] < current[1]
        )
        diag["gap"] = {"previous_low": previous, "current_high": current, "visible": visible}
        if visible:
            x0, y0 = previous
            x1, y1 = current
            pen.rectangle((x0, y0, x1, y1), fill=rgba(C["gold"], line_alpha * .14),
                          outline=rgba(C["gold"], line_alpha * .8), width=.8)
            _dot(pen, previous, line_alpha, radius=2)
            _dot(pen, current, line_alpha, radius=2)

    if span := link.get("statistics_range"):
        x, _ = drawer._coords(state)
        first, last = (drawer.model.market.index_for_date(day) for day in span)
        x0, x1 = x(first), x(last)
        visible = CHART_LEFT <= x0 < x1 <= CHART_RIGHT and last <= state.current_index
        y = CHART_BOTTOM - 21 if hasattr(drawer, "editorial_chart_top") else CHART_BOTTOM + 8
        diag["statistics_bracket"] = {"from": span[0], "to": span[1], "x": (x0, x1), "y": y, "visible": visible}
        if visible:
            color = rgba(C["gold"], line_alpha * .86)
            pen.line(((x0, y-6), (x0, y), (x1, y), (x1, y-6)), color, 1.1)

    if cue.get("event_clock") and _visible(drawer, anchor_xy) and not span and not cue["photo_asset_id"]:
        # A vertical hairline locates the observation without suggesting direction or cause.
        x, y = anchor_xy
        pen.line((x, _chart_top(drawer) + 6, x, y), rgba(C["muted"], line_alpha * .5), .8)
        _dot(pen, anchor_xy, line_alpha, radius=2.5)
        diag["event_leader_visible"] = True
    elif _visible(drawer, anchor_xy) and not wick and not diag["close_endpoints_visible"] and not cue["photo_asset_id"]:
        _dot(pen, anchor_xy, line_alpha, radius=2.6)
    return diag


def _draw_orbit(image, layer, drawer, state, orbit: dict, *, opacity: float = 1.0) -> dict:
    elapsed = state.frame_number - orbit["hit_frame"]
    duration = float(orbit["reflection_pulse_seconds"]) * drawer.model.fps
    if elapsed < 0:
        return {"visible": False, "pulse": False}
    (x, y), _ = drawer._timeline_point(orbit["node_date"])
    visible = 0 < x < 720 and 0 < y < 1280
    if not visible:
        return {"visible": False, "pulse": False, "point": (x, y)}
    d = drawer._pen(layer)
    d.ellipse((x-2.5, y-2.5, x+2.5, y+2.5), fill=rgba((255, 188, 149), .78 * opacity))
    pulse = 0 <= elapsed < duration
    if pulse:
        strength = (1 - elapsed / duration) ** 2 * opacity
        radius = 6 + 5 * elapsed / duration
        d.ellipse((x-radius, y-radius, x+radius, y+radius),
                  outline=rgba((255, 118, 81), strength * .88), width=1.3)
        reflection = drawer._new()
        drawer._pen(reflection).ellipse((x-27, y+18, x+27, y+90),
                                      fill=rgba((255, 75, 53), .16 * strength))
        reflection.putalpha(ImageChops.multiply(reflection.getchannel("A"), drawer.earth_mask))
        image.alpha_composite(reflection)
    return {"visible": visible, "pulse": pulse, "point": (x, y),
            "node_date": orbit["node_date"], "hit_frame": orbit["hit_frame"]}


def _draw_photo(layer, drawer, photo: Image.Image, alpha: float) -> tuple[int, int, int, int]:
    revised = hasattr(drawer, "editorial_chart_top")
    cache = getattr(drawer, "_editorial_photo_overlay", None)
    if cache is None or cache[0] is not photo:
        height = min(470, CHART_BOTTOM - _chart_top(drawer) - 22)
        # The chart beside the original photo is the same projection already
        # used for the preceding shot. Keep the current wick and the HUD clear.
        width = 497 if revised else 638
        fitted = ImageOps.contain(photo.convert("RGBA"), (round(width * drawer.s), round(height * drawer.s)),
                                  method=Image.Resampling.LANCZOS)
        drawer._editorial_photo_overlay = (photo, fitted)
    else:
        fitted = cache[1]
    x = round(42 * drawer.s) if revised else (drawer.w - fitted.width) // 2
    y_mid = (_chart_top(drawer) + CHART_BOTTOM) / 2 if revised else 557
    xy = (x, round(y_mid * drawer.s - fitted.height / 2))
    if alpha < 1:
        fitted = fitted.copy()
        fitted.putalpha(round(255 * clamp(alpha)))
    layer.alpha_composite(fitted, xy)
    return (*xy, xy[0] + fitted.width, xy[1] + fitted.height)


def draw_cue(image, drawer, state, cue: dict, photo: Image.Image | None = None,
             *, opacity: float | None = None, show_text: bool = True) -> dict:
    """Apply source text, real geometric anchors and timed orbit highlights."""

    if cue["link_geometry"]["event_line_has_arrowhead"] is not False:
        raise ValueError("Editorial connecting lines cannot have arrowheads")
    frame = state.frame_number
    outgoing = opacity is not None and frame >= cue["end_frame_exclusive"]
    if not outgoing and not cue["start_frame"] <= frame < cue["end_frame_exclusive"]:
        raise ValueError(f"Frame {frame} is outside the active editorial cue")
    text = cue["text_cue"]
    style = _style(cue)
    missing_photo = bool(cue["photo_asset_id"]) and photo is None
    alpha = _caption_alpha(frame, text) if opacity is None else clamp(opacity)
    if missing_photo:
        return {"text_visible": False, "event_label": None, "photo_visible": False, "missing_photo": True,
                "orbit": {"visible": False, "pulse": False}, "geometry": {},
                "photo_alpha": 0.0, "photo_bbox": None, "style": style, "caption_lines": [],
                "caption_boxes": [], "caption_alpha": 0.0, "outgoing": outgoing}

    layer = drawer._new()
    pen = drawer._pen(layer, True)
    label = _event_label(cue.get("event_clock"))
    photo_alpha = 0.0
    photo_bbox = None
    if cue["photo_asset_id"] and not outgoing:
        remaining = cue["end_frame_exclusive"] - 1 - frame
        photo_alpha = min(alpha, smooth(remaining / max(1, _exit_frames(cue)))) if hasattr(
            drawer, "editorial_chart_top"
        ) else alpha
        alpha = photo_alpha
    photo_visible = photo_alpha > 0
    if photo_visible:
        photo_bbox = _draw_photo(layer, drawer, photo, photo_alpha)
    geometry = _draw_links(drawer, pen, state, cue, alpha, outgoing=outgoing)
    first_box = len(drawer.text_boxes)
    caption = []
    if alpha > 0 and show_text:
        if hasattr(drawer, "editorial_chart_top"):
            caption = _caption(drawer, pen, cue, label, alpha)
        else:
            caption = _baseline_caption(drawer, pen, text, label, alpha)
    orbit = _draw_orbit(image, layer, drawer, state, cue["earth_orbit"], opacity=alpha if outgoing else 1.0)
    image.alpha_composite(layer)
    return {"text_visible": bool(caption), "caption_alpha": alpha, "caption_lines": caption,
            "caption_boxes": drawer.text_boxes[first_box:], "event_label": label if caption else None,
            "photo_visible": photo_visible, "photo_alpha": photo_alpha, "photo_bbox": photo_bbox,
            "missing_photo": False, "geometry": geometry, "orbit": orbit, "style": style, "outgoing": outgoing}
