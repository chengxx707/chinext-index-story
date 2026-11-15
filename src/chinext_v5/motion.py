from __future__ import annotations

import math


def clamp(v: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


def smoothstep(v: float) -> float:
    v = clamp(v)
    return v * v * (3.0 - 2.0 * v)


def smootherstep(v: float) -> float:
    v = clamp(v)
    return v * v * v * (v * (v * 6.0 - 15.0) + 10.0)


def ease_out_cubic(v: float) -> float:
    v = clamp(v)
    return 1.0 - (1.0 - v) ** 3


def ease_in_out_sine(v: float) -> float:
    v = clamp(v)
    return -(math.cos(math.pi * v) - 1.0) / 2.0


def pulse(t: float, center: float, width: float) -> float:
    if width <= 0:
        return 0.0
    x = abs(t - center) / width
    return math.exp(-4.2 * x * x)


def envelope(t: float, center: float, pre: float, post: float) -> float:
    if t < center - pre or t > center + post:
        return 0.0
    if t <= center:
        return smoothstep((t - (center - pre)) / max(pre, 1e-6))
    return 1.0 - smoothstep((t - center) / max(post, 1e-6))
