"""Draw the released editorial cues over the existing OHLC compositor."""

from __future__ import annotations

from PIL import Image, ImageChops, ImageOps

from .drawing import C, clamp, rgba, smooth

CHART_LEFT, CHART_RIGHT = 26, 704
CHART_TOP, CHART_BOTTOM = 252, 846

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


def _fit_font(drawer, pen, text: str, nominal_size: int, height: int, *, bold: bool = False):
    for size in range(nominal_size, 8, -1):
        font = drawer.fonts.get(size, bold)
        if pen.textlength(text, font) <= 435 and font.getbbox(text, anchor="lt")[3] <= height * drawer.s:
            return font
    raise ValueError(f"Editorial text does not fit the caption band: {text}")


def _caption(drawer, pen, text: dict, label: str | None, alpha: float):
    x = 70
    if label:
        font = _fit_font(drawer, pen, label, 11, 13, bold=True)
        pen.text((x, 161), label, font, rgba(C["gold"], alpha),
                 anchor="lt", id="editorial_event_clock", role="event_clock")
    lines = text["lines"]
    top, interval, nominal = (176, 21, 19) if len(lines) >= 3 else (177, 27, 23)
    for i, line in enumerate(lines):
        font = _fit_font(drawer, pen, line, nominal, interval - 2, bold=i == 0)
        pen.text((x, top + i * interval), line, font, rgba(C["text"], alpha),
                 anchor="lt", id=f"editorial_copy_{i}", role="editorial_copy")
    source = text.get("source_line")
    if source:
        font = _fit_font(drawer, pen, source, 11, 13)
        pen.text((x, 238), source, font, rgba((164, 181, 194), alpha),
                 anchor="lt", id="editorial_source", role="source")


def _point(drawer, state, day: str, price: float) -> tuple[float, float] | None:
    index = drawer.model.market.index_for_date(day)
    if index > state.current_index:
        return None
    x, y = drawer._coords(state)
    return x(index), y(price)


def _visible(point: tuple[float, float] | None) -> bool:
    return point is not None and (
        CHART_LEFT <= point[0] <= CHART_RIGHT and CHART_TOP <= point[1] <= CHART_BOTTOM
    )


def _dot(pen, point: tuple[float, float], alpha: float, *, radius: float = 3) -> None:
    x, y = point
    pen.ellipse((x-radius, y-radius, x+radius, y+radius),
                fill=rgba(C["gold_light"], alpha), outline=rgba(C["gold"], alpha), width=.8)


def _draw_links(drawer, pen, state, cue: dict, alpha: float) -> dict:
    link = cue["link_geometry"]
    anchor = cue["primary_anchor"]
    hit = state.frame_number >= anchor["hit_frame"]
    anchor_xy = _point(drawer, state, anchor["date"], anchor["value"]) if hit else None
    diag = {"anchor": anchor_xy, "anchor_visible": _visible(anchor_xy),
            "close_endpoints": [], "close_endpoints_visible": False, "close_endpoint_markers": 0,
            "close_link_progress": 0.0, "close_link_complete": False,
            "wick_anchor": None, "wick_visible": False,
            "gap": None, "statistics_bracket": None, "event_leader_visible": False}
    if not hit:
        return diag
    line_alpha = max(.40, alpha)
    for endpoint in link["close_endpoints"]:
        diag["close_endpoints"].append(_point(drawer, state, endpoint["date"], endpoint["value"]))
    diag["close_endpoints_visible"] = (
        len(diag["close_endpoints"]) == 2 and all(_visible(point) for point in diag["close_endpoints"])
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
        diag.update(close_endpoint_markers=2 if end_visible else 1,
                    close_link_progress=reveal, close_link_complete=reveal == 1.0)

    wick = link.get("intraday_anchor")
    if wick:
        xy = _point(drawer, state, wick["date"], wick["value"])
        diag.update(wick_anchor=xy, wick_visible=_visible(xy))
        if _visible(xy):
            x, y = xy
            pen.line((x-9, y, x+9, y), rgba(C["gold"], line_alpha), 1)
            _dot(pen, xy, line_alpha)

    if gap := link.get("gap"):
        previous = _point(drawer, state, gap["previous_date"], gap["previous_low"])
        current = _point(drawer, state, gap["current_date"], gap["current_high"])
        visible = _visible(previous) and _visible(current) and previous[0] < current[0] and previous[1] < current[1]
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
        y = CHART_BOTTOM + 8
        diag["statistics_bracket"] = {"from": span[0], "to": span[1], "x": (x0, x1), "y": y, "visible": visible}
        if visible:
            color = rgba(C["gold"], line_alpha * .86)
            pen.line(((x0, y-6), (x0, y), (x1, y), (x1, y-6)), color, 1.1)

    if cue.get("event_clock") and anchor_xy is not None and _visible(anchor_xy) and not span and not cue["photo_asset_id"]:
        # A vertical hairline locates the observation without suggesting direction or cause.
        x, y = anchor_xy
        pen.line((x, CHART_TOP + 6, x, y), rgba(C["muted"], line_alpha * .5), .8)
        _dot(pen, anchor_xy, line_alpha, radius=2.5)
        diag["event_leader_visible"] = True
    elif _visible(anchor_xy) and not wick and not diag["close_endpoints_visible"] and not cue["photo_asset_id"]:
        _dot(pen, anchor_xy, line_alpha, radius=2.6)
    return diag


def _draw_orbit(image, layer, drawer, state, orbit: dict) -> dict:
    elapsed = state.frame_number - orbit["hit_frame"]
    duration = float(orbit["reflection_pulse_seconds"]) * drawer.model.fps
    if elapsed < 0:
        return {"visible": False, "pulse": False}
    (x, y), _ = drawer._timeline_point(orbit["node_date"])
    visible = 0 < x < 720 and 0 < y < 1280
    if not visible:
        return {"visible": False, "pulse": False, "point": (x, y)}
    d = drawer._pen(layer)
    d.ellipse((x-2.5, y-2.5, x+2.5, y+2.5), fill=(255, 188, 149, 200))
    pulse = 0 <= elapsed < duration
    if pulse:
        strength = (1 - elapsed / duration) ** 2
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


def _draw_photo(layer, drawer, photo: Image.Image, alpha: float) -> None:
    cache = getattr(drawer, "_editorial_photo_overlay", None)
    if cache is None or cache[0] is not photo:
        fitted = ImageOps.contain(photo.convert("RGBA"), (round(638 * drawer.s), round(470 * drawer.s)),
                                  method=Image.Resampling.LANCZOS)
        drawer._editorial_photo_overlay = (photo, fitted)
    else:
        fitted = cache[1]
    xy = ((drawer.w - fitted.width) // 2, round(557 * drawer.s - fitted.height / 2))
    if alpha < 1:
        fitted = fitted.copy()
        fitted.putalpha(round(255 * clamp(alpha)))
    layer.alpha_composite(fitted, xy)


def draw_cue(image, drawer, state, cue: dict, photo: Image.Image | None = None) -> dict:
    """Apply source text, real geometric anchors and timed orbit highlights."""

    if cue["link_geometry"]["event_line_has_arrowhead"] is not False:
        raise ValueError("Editorial connecting lines cannot have arrowheads")
    frame = state.frame_number
    if not cue["start_frame"] <= frame < cue["end_frame_exclusive"]:
        raise ValueError(f"Frame {frame} is outside the active editorial cue")
    text = cue["text_cue"]
    missing_photo = bool(cue["photo_asset_id"]) and photo is None
    alpha = _caption_alpha(frame, text)
    if missing_photo:
        return {"text_visible": False, "event_label": None, "photo_visible": False, "missing_photo": True,
                "orbit": {"visible": False, "pulse": False}, "geometry": {}}

    layer = drawer._new()
    pen = drawer._pen(layer, True)
    label = _event_label(cue.get("event_clock"))
    photo_visible = bool(cue["photo_asset_id"]) and alpha > 0
    if photo_visible:
        _draw_photo(layer, drawer, photo, alpha)
    geometry = _draw_links(drawer, pen, state, cue, alpha)
    if alpha > 0:
        _caption(drawer, pen, text, label, alpha)
    orbit = _draw_orbit(image, layer, drawer, state, cue["earth_orbit"])
    image.alpha_composite(layer)
    return {"text_visible": alpha > 0, "caption_alpha": alpha,
            "event_label": label if alpha > 0 else None, "photo_visible": photo_visible,
            "missing_photo": False, "geometry": geometry, "orbit": orbit}
