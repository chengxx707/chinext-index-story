"""Apply the approved B01-B horizontal camera push to the pinned visual scene."""

from __future__ import annotations

from math import isclose


def apply_approved_intro_push(scene) -> None:
    """Consume the B01 cue setting after scene construction and before drawing."""
    cue = scene.cue_at(0)
    push = cue["camera_story_clock"]["approved_intro_push"]
    start, stop = push["start_frame"], push["end_frame_exclusive"]
    open_span, settled_span = push["start_span"], push["end_span"]
    if (start, stop, open_span, settled_span) != (0, 45, 56, 50):
        raise ValueError("B01-B must keep the approved frame and window-span settings")
    if (cue["beat_id"], cue["start_frame"], cue["end_frame_exclusive"]) != ("B01", 0, 240):
        raise ValueError("B01-B requires the approved eight-second flash-forward")
    text = cue["text_cue"]
    if ((text["in_frame"], text["full_alpha_from_frame"], text["out_frame_exclusive"]) != (0, 6, 240)
            or text["lines"] != ["闪前 · 2015.06.03", "阶段最高收盘 3,982.25"]):
        raise ValueError("B01-B requires the approved title, value and visibility timing")
    april = scene.states[240]
    if (scene.cue_at(240)["beat_id"], april.current_date.date().isoformat(), april.current_close) != (
            "B02", "2015-04-01", 2404.91):
        raise ValueError("B01-B requires the approved April 1 hard cut")

    updated = []
    for frame in range(cue["end_frame_exclusive"]):
        state = scene.states[frame]
        projection = scene.projections[frame]
        if ((state.current_date.date().isoformat(), state.current_close) != ("2015-06-03", 3982.25)
                or (projection["y_min"], projection["y_max"]) != (1300, 4550)
                or not isclose(projection["window_span"], settled_span)):
            raise ValueError(f"Unexpected B01-B market or baseline projection at frame {frame}")
        if not start <= frame < stop:
            continue
        progress = (frame - start) / (stop - start)
        eased = progress * progress * (3 - 2 * progress)
        span = open_span + (settled_span - open_span) * eased
        anchor = (state.current_index - projection["window_start"]) / projection["window_span"]
        updated.append(dict(projection, window_span=span, window_start=state.current_index - span * anchor))

    scene.projections[start:stop] = updated
