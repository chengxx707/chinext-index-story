"""Frozen trading-day state and continuous camera for the S04–S09 phone test."""

from __future__ import annotations

from bisect import bisect_right
from math import floor

from chinext_v6.model import FrameState, MarketData


FPS = 30
FRAME_COUNT = 600
LOW_DATE = "2012-12-03"
PEAK_DATE = "2015-06-03"
LOW_HOLD_THROUGH = 45
PEAK_HOLD_FROM = 540

# The start of each second in the approved 20-second storyboard (a65de02).
ANCHOR_DATES = (
    LOW_DATE, LOW_DATE, "2012-12-21", "2013-03-29", "2013-07-24", "2013-07-31",
    "2013-10-18", "2014-01-08", "2014-01-24", "2014-04-30", "2014-12-31",
    "2015-04-13", "2015-04-24", "2015-04-29", "2015-05-05", "2015-05-18",
    "2015-05-22", "2015-05-29", PEAK_DATE, PEAK_DATE,
)

# The approved stills fix the opening, dense advance, and final camera (9bfc303).
# Intermediate chart price domains leave room for all visible frozen highs/lows.
_LOOKBACK = ((0, 79), (LOW_HOLD_THROUGH, 79), (420, 174), (PEAK_HOLD_FROM, 187))
_RIGHT_FILL = ((0, .79), (LOW_HOLD_THROUGH, .79), (420, .86), (PEAK_HOLD_FROM, .86))
_PRICE_FLOORS = (
    (0, 520), (90, 520), (105, 540), (120, 665), (150, 685), (180, 745),
    (210, 805), (240, 900), (270, 1020), (300, 1100), (330, 1150),
    (420, 1190), (PEAK_HOLD_FROM, 1230),
)
_PRICE_CEILINGS = (
    (0, 830), (LOW_HOLD_THROUGH, 830), (60, 850), (78, 920), (90, 995), (105, 1170),
    (120, 1305), (150, 1360), (180, 1530), (210, 1540), (240, 1600), (270, 1700),
    (285, 1750), (300, 1840), (315, 2290), (330, 2790), (360, 2980), (390, 3200),
    (420, 3520), (450, 3650), (480, 4020), (510, 4180), (PEAK_HOLD_FROM, 4590),
)


def _sample_curve(keys: tuple[tuple[int, float], ...]) -> list[float]:
    """Sample a monotone cubic curve with stationary holds and no overshoot."""
    frames, values = zip(*keys, strict=True)
    lengths = [right - left for left, right in zip(frames, frames[1:])]
    speeds = [(right - left) / length for left, right, length in zip(values, values[1:], lengths)]
    tangents = [0.0]
    for left, right, before, after in zip(lengths, lengths[1:], speeds, speeds[1:]):
        slope = 0.0
        if before * after > 0:
            weight_left = 2 * right + left
            weight_right = right + 2 * left
            slope = (weight_left + weight_right) / (weight_left / before + weight_right / after)
        tangents.append(slope)
    tangents.append(0.0)

    result = []
    for frame in range(FRAME_COUNT):
        interval = bisect_right(frames, frame) - 1
        if interval == len(lengths):
            result.append(float(values[-1]))
            continue
        length = lengths[interval]
        start, end = values[interval:interval + 2]
        start_slope, end_slope = tangents[interval:interval + 2]
        progress = (frame - frames[interval]) / length
        eased = progress * progress * (3 - 2 * progress)
        value = (start + eased * (end - start)
                 + length * progress * (1 - progress) * ((1 - progress) * start_slope - progress * end_slope))
        result.append(float(value))
    return result


def build_clock(market: MarketData) -> list[tuple[FrameState, dict[str, float]]]:
    """Return 600 frame states and projections from the frozen market data."""
    indices = [market.index_for_date(date) for date in ANCHOR_DATES]
    low, peak = indices[0], indices[-1]
    base, top = float(market.close[low]), float(market.close[peak])
    if (base, top, peak - low + 1) != (593.66, 3982.25, 605):
        raise ValueError("S04–S09 requires the approved 605-row frozen range and both endpoint closes")
    anchors = list(enumerate(indices))
    clock_keys = [(second * FPS, index) for second, index in anchors]
    clock_keys.insert(2, (LOW_HOLD_THROUGH, low))
    positions = _sample_curve(tuple(clock_keys))

    output = []
    previous = low - 1
    for frame, (playhead, lookback, right_fill, lower, upper) in enumerate(zip(
            positions, _sample_curve(_LOOKBACK), _sample_curve(_RIGHT_FILL),
            _sample_curve(_PRICE_FLOORS), _sample_curve(_PRICE_CEILINGS), strict=True)):
        index = floor(playhead)
        start = playhead - lookback
        span = lookback / right_fill
        first = max(0, floor(start))
        if not first <= index or not previous <= index <= peak:
            raise ValueError(f"Invalid S04–S09 market progression at frame {frame}")
        if not (lower <= min(market.low[first:index + 1]) <= max(market.high[first:index + 1]) <= upper):
            raise ValueError(f"Camera cuts off a visible frozen wick at frame {frame}")
        if index > previous and not start <= previous + 1 <= index <= start + span:
            raise ValueError(f"A newly released frozen candle is outside the camera at frame {frame}")
        close = float(market.close[index])
        stage_value = close / base - 1.0
        state = FrameState(
            t=frame / FPS, frame_number=frame, playhead_index=playhead, current_index=index,
            current_date=market.dates[index], current_close=close, visible_days=round(lookback),
            current_x_frac=(index - start) / span, window_start=first, window_end=index,
            y_min=lower, y_max=upper, shot_id="s04-s09-montage", stage_mode="rise_from_low",
            stage_label="较2012.12.03收盘", stage_value=stage_value, stage_progress=min(1.0, stage_value / 6),
            active_event_ids=(), completed_milestones=(),
        )
        output.append((state, {"window_start": start, "window_span": span, "y_min": lower, "y_max": upper}))
        previous = index
    return output
