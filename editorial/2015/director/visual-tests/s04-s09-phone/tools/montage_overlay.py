"""Editorial foreground for the 600-frame S04–S09 phone montage."""

from __future__ import annotations

from chinext_v6.drawing import C


LOW_DAY = "2012.12.03"
PEAK_DAY = "2015.06.03"
LOW_END = 46
AFTER_HUAYI = (174, 234)
AFTER_IPO = (270, 450)
AFTER_ACCOUNT_POLICY = (387, 450)
HISTORY_CLEAR = (512, 540)

# Frame ranges are end-exclusive at 30 fps. Earliest market dates are guards
# for the displayed anchors, not the historical dates of all these facts.
EVENTS = (
    {
        "id": "huayi",
        "frames": (120, 174),
        "earliest_market_date": "2013.07.24",
        "precision": "month",
        "lines": ("2013.07", "华谊兄弟并购", "手游公司银汉科技"),
        "source": "据中证网、人民网同期报道",
    },
    {
        "id": "ipo",
        "frames": (210, 270),
        "earliest_market_date": "2014.01.08",
        "precision": "month",
        "lines": ("2014.01", "IPO 重启"),
        "source": "据新股发行重启报道",
    },
    {
        "id": "accounts_policy",
        "frames": (330, 387),
        "earliest_market_date": "2015.04.13",
        "precision": "effective_day",
        "lines": ("2015.04.13 起", "一人多户放开"),
        "source": "中国结算 · A股自然人账户",
    },
    {
        "id": "accounts",
        "frames": (390, 450),
        "earliest_market_date": "2015.04.29",
        "precision": "statistics_week",
        "lines": ("2015.04.20—24  ·  统计周", "新增 A 股账户", "413.03 万户"),
        "source": "中国结算数据  ·  4/28 盘后报道",
    },
    {
        "id": "letv",
        "frames": (450, 512),
        "earliest_market_date": "2015.05.18",
        "precision": "historical_close",
        "lines": ("回看 2015.05.13 收盘", "乐视网总市值", "超过 1,500 亿元"),
        "source": "据北京青年报、大众证券报同期报道",
    },
)


def _header(pen, fonts):
    pen.text((66, 57), "CHINEXT INDEX", fonts.get(11), (190, 203, 215, 240),
             id="index_en", role="heading")
    pen.line((54, 93, 54, 143), (226, 64, 58, 255), 2.4)
    pen.text((66, 85), "创业板指", fonts.get(31, True), C["text"], id="index_name", role="heading")
    pen.text((195, 98), "399006", fonts.get(18), (176, 192, 206, 245), id="index_code", role="heading")


def _market_hud(pen, fonts, state):
    day = state.current_date.strftime("%Y.%m.%d")
    close = f"{state.current_close:,.2f}"
    pen.text((663, 176), day, fonts.get(15), (165, 184, 201, 245),
             anchor="ra", id="market_date", role="market")
    pen.text((663, 198), close, fonts.get(25, True), C["text"],
             anchor="ra", id="market_close", role="market")
    pen.text((663, 233), "当日收盘", fonts.get(11), (145, 168, 183, 245),
             anchor="ra", id="market_label", role="market")
    return {"date": day, "close": close, "label": "当日收盘"}


def _landmark(image, drawer, state, start):
    pen = drawer._pen(image, True)
    fonts = drawer.fonts
    xp, yp = drawer._coords(state)
    x, y = xp(state.current_index), yp(state.current_close)
    day, close, label = (
        (LOW_DAY, "593.66", "样本内最低收盘") if start else
        (PEAK_DAY, "3,982.25", "2015 阶段最高收盘")
    )
    if (state.current_date.strftime("%Y.%m.%d"), f"{state.current_close:,.2f}") != (day, close):
        raise ValueError(f"Landmark {day} does not match the market playhead")
    x_text, side = (67, "la") if start else (657, "ra")
    pen.text((x_text, 165), day, fonts.get(23), (227, 216, 202, 250),
             anchor=side, id="key_date", role="landmark")
    pen.text((x_text, 202), close, fonts.get(79, True), C["gold_light"],
             anchor=side, id="key_close", role="landmark")
    pen.text((x_text, 305), label, fonts.get(24, True), (226, 191, 140, 255),
             anchor=side, id="key_label", role="landmark")
    if start:
        pen.line((68, 350, 276, 350), (238, 174, 104, 155), .9)
        orbit_point, _ = drawer._timeline_point(state.current_date)
        pen.text((orbit_point[0], orbit_point[1] - 29), "2012", fonts.get(18, numeric=True),
                 (217, 221, 226, 245), anchor="mm", id="timeline_2012_anchor", role="timeline")
    else:
        pen.line(((433, 351), (x - 26, 351), (x, y)), (245, 187, 112, 180), 1.0)
    drawer._sprite(image, drawer.gold_glow, x, y, .63)
    pen.ellipse((x - 4, y - 4, x + 4, y + 4),
                fill=(255, 241, 206, 255), outline=(255, 205, 143, 255), width=1)
    return {
        "id": "low" if start else "peak", "lines": [day, close, label],
        "visual_role": "landmark", "opacity": 1.0, "price_anchor_logical": [x, y],
    }


def _opacity(frame, interval, enter=4, leave=4):
    start, end = interval
    if not start <= frame < end:
        return 0.0
    return min(1.0, (frame - start + 1) / (enter + 1), (end - frame) / (leave + 1))


def _paint(image, drawer, opacity, draw):
    canvas = image if opacity == 1 else drawer._new()
    draw(drawer._pen(canvas, True), drawer.fonts)
    if canvas is not image:
        canvas.putalpha(canvas.getchannel("A").point(lambda value: round(value * opacity)))
        image.alpha_composite(canvas)


def _event_period(pen, fonts, identifier, line):
    pen.text((68, 180), line, fonts.get(17, True), (238, 210, 201, 255),
             id=f"{identifier}_period", role="event")
    pen.line((68, 211, 322, 211), (228, 85, 69, 140), .85)


def _event_copy(pen, fonts, cue):
    identifier = cue["id"]
    period, *lines = cue["lines"]
    _event_period(pen, fonts, "account" if identifier == "accounts" else identifier, period)
    if identifier == "accounts":
        pen.text((68, 225), "新增 A 股账户", fonts.get(28, True), C["text"],
                 id="account_name", role="event")
        pen.text((68, 258), "413.03", fonts.get(75, True), C["text"], id="account_value", role="event")
        number_width = pen.textlength("413.03", fonts.get(75, True))
        pen.text((78 + number_width, 305), "万户", fonts.get(25, True), (232, 238, 240, 255),
                 id="account_unit", role="event")
        source_y = 359
        source_id = "account_source"
    elif identifier == "letv":
        pen.text((68, 225), lines[0], fonts.get(28, True), C["text"], id="letv_name", role="event")
        pen.text((68, 269), "超过", fonts.get(26, True), (232, 238, 240, 255),
                 id="letv_qualifier", role="event")
        pen.text((129, 251), "1,500", fonts.get(64, True), C["text"],
                 id="letv_value", role="event")
        number_width = pen.textlength("1,500", fonts.get(64, True))
        pen.text((139 + number_width, 279), "亿元", fonts.get(25, True), (232, 238, 240, 255),
                 id="letv_unit", role="event")
        source_y = 348
        source_id = "letv_source"
    else:
        title_size = 38 if len(lines) == 1 else 31
        for i, line in enumerate(lines):
            pen.text((68, 227 + 49 * i), line, fonts.get(title_size, True), C["text"],
                     id=f"{identifier}_title_{i}", role="event")
        source_y = 298 if len(lines) == 1 else 330
        source_id = f"{identifier}_source"
    pen.text((69, source_y), cue["source"], fonts.get(15), (161, 182, 195, 250),
             id=source_id, role="source")


def _history(image, drawer, frame):
    shown = []
    hua = .78 * _opacity(frame, AFTER_HUAYI, 5, 7)
    if hua:
        def huayi(pen, fonts):
            pen.line((394, 282, 394, 330), (167, 125, 102, 190), 1)
            pen.text((407, 275), "2013.07", fonts.get(15), (185, 163, 141, 225),
                     id="history_huayi_date", role="past_event")
            pen.text((407, 296), "华谊兄弟并购", fonts.get(19, True), (168, 167, 164, 238),
                     id="history_huayi_title", role="past_event")

        _paint(image, drawer, hua, huayi)
        shown.append({"id": "huayi", "lines": ["2013.07", "华谊兄弟并购"],
                      "visual_role": "past_event", "opacity": round(hua, 4)})
    ipo_weight = 1 if 390 <= frame < 445 else .65
    ipo = ipo_weight * _opacity(frame, AFTER_IPO, 5, 4)
    policy = _opacity(frame, AFTER_ACCOUNT_POLICY, 5, 4)
    if policy:
        def april_policy(pen, fonts):
            pen.line((394, 282, 394, 347), (177, 112, 106, 190), 1)
            pen.text((407, 275), "4/13", fonts.get(15), (170, 184, 192, 225),
                     id="policy_date", role="past_event")
            pen.text((407, 296), "一人多户放开", fonts.get(21, True), (171, 192, 205, 245),
                     id="policy_title", role="past_event")

        _paint(image, drawer, policy, april_policy)
        shown.append({"id": "accounts_policy", "lines": ["4/13", "一人多户放开"],
                      "visual_role": "past_event", "opacity": round(policy, 4)})
    if ipo:
        def ipo_memory(pen, fonts):
            pen.text((407, 333), "2014.01  IPO重启", fonts.get(16), (144, 163, 183, 220),
                     id="ipo_memory", role="past_event")

        _paint(image, drawer, ipo, ipo_memory)
        shown.append({"id": "ipo", "lines": ["2014.01  IPO重启"],
                      "visual_role": "past_event", "opacity": round(ipo, 4)})
    return shown


def draw_copy(image, drawer, state, moment=None, highlights=None):
    """Draw copy over the market scene and return its frame-level editorial roles."""
    frame = state.frame_number
    start_boxes = len(drawer.text_boxes)
    pen = drawer._pen(image, True)
    fonts = drawer.fonts
    _header(pen, fonts)

    primary = None
    secondary = []
    hud = None
    if 0 <= frame < LOW_END:
        opacity = min(1.0, (LOW_END - frame) / 8)
        layer = image if opacity == 1 else drawer._new()
        primary = _landmark(layer, drawer, state, start=True)
        if layer is not image:
            layer.putalpha(layer.getchannel("A").point(lambda value: round(value * opacity)))
            image.alpha_composite(layer)
        primary["opacity"] = opacity
    elif 540 <= frame < 600:
        primary = _landmark(image, drawer, state, start=False)
    else:
        market_date = state.current_date.strftime("%Y.%m.%d")
        cue = next((event for event in EVENTS if event["frames"][0] <= frame < event["frames"][1]), None)
        if cue is not None:
            if market_date < cue["earliest_market_date"]:
                raise ValueError(f"{cue['id']} appeared before its market anchor at frame {frame}: {market_date}")
            opacity = _opacity(frame, cue["frames"], 3, 4)
            _paint(image, drawer, opacity, lambda pen, fonts: _event_copy(pen, fonts, cue))
            primary = {**cue, "visual_role": "primary_event", "opacity": round(opacity, 4)}
        hud = _market_hud(pen, fonts, state)
        secondary = _history(image, drawer, frame)

    return {
        "frame": frame, "primary": primary, "secondary": secondary, "market_hud": hud,
        "layout_box_ids": [box["id"] for box in drawer.text_boxes[start_boxes:]],
    }
