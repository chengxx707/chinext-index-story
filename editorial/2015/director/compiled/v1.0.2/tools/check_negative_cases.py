"""Exercise known failure modes against the V1.0.2 audit gates."""

import argparse
from copy import deepcopy
import json
from pathlib import Path

from jsonschema import Draft202012Validator

from compile_candidate import audit_compiled_events, audit_focus, load_inputs, read, write
from event_audit import audit_events
from market_audit import audit_market
from runtime_audit import audit_runtime


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-root", required=True, type=Path)
    parser.add_argument("--result", required=True, type=Path)
    args = parser.parse_args()
    repo = Path.cwd()
    runtime, result = args.runtime_root.resolve(), args.result.resolve()
    sheet, register, _ = load_inputs(repo, runtime)
    beats = sheet["beats"]

    wrong_anchor = deepcopy(beats)
    wrong_anchor[5]["anchor"]["date"] = "2015-06-10"
    missing_july6 = deepcopy(beats)
    missing_july6[9]["market_keyframes"] = [key for key in beats[9]["market_keyframes"] if key["date"] != "2015-07-06"]
    forged_weekend = deepcopy(beats)
    key = next(row for row in forged_weekend[7]["market_keyframes"] if row["date"] == "2015-06-27")
    key.update(field="close", value=2920.70)

    candidate = read(result/"director_candidate.json")
    candidate_schema = read(result/"candidate.schema.json")
    shadow = deepcopy(candidate)
    del shadow["cues"][0]["primary_focus"]
    bad_focus = deepcopy(candidate)
    bad_focus["cues"][0]["camera_story_clock"]["focus_windows"] *= 2
    short_caption = deepcopy(candidate)
    short_caption["cues"][0]["text_cue"]["stable_reading_seconds"] = 0.1
    font = Path("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc")

    bad_event = deepcopy(register)
    next(e for e in bad_event["events"] if e.get("event_id") == "E-AUG-02-05")["time"] = "14:00:00"
    bad_copy = deepcopy(candidate["cues"])
    pmi_cue = next(c for c in bad_copy if (c["event_clock"] or {}).get("event_id") == "E-AUG-01-03")
    pmi_cue["event_clock"]["first_release_time"] = "09:43:10"
    event_report = read(result/"event_asset_audit.json")

    projections = read(result/"legacy/segments.json")
    for segment in projections:
        segment["timeline"] = read(result/"legacy"/f'{segment["id"]}.json')
    first_cue = projections[-1]["timeline"]["cues"][0]
    first_cue["camera"]["target_y_domain"] = [1200, 4600]
    broken_clock = audit_runtime(candidate, projections, repo, runtime)

    cases = {
        "wrong_B06_date_rejected": not audit_market(wrong_anchor, register, repo/"data/cyb_daily.csv")["passed"],
        "missing_July6_resume_checkpoint_rejected": not audit_market(missing_july6, register, repo/"data/cyb_daily.csv")["passed"],
        "priced_June27_weekend_candle_rejected": not audit_market(forged_weekend, register, repo/"data/cyb_daily.csv")["passed"],
        "missing_primary_focus_field_rejected": not Draft202012Validator(candidate_schema).is_valid(shadow),
        "duplicate_focus_window_rejected": not audit_focus(bad_focus, font)["passed"],
        "insufficient_reading_window_rejected": not audit_focus(short_caption, font)["passed"],
        "incorrect_pbc_timestamp_rejected": not audit_events(beats, bad_event, repo, None)["passed"],
        "pmi_first_release_claim_rejected": not audit_compiled_events(bad_copy, event_report)["passed"],
        "actual_clock_camera_discontinuity_rejected": (
            not broken_clock["passed"] and any("same camera scale/domain" in error
                                              for error in broken_clock["runtime"]["errors"])
        ),
    }
    write(result/"negative_cases.json", {"passed": all(cases.values()), "cases": cases})
    print(json.dumps(cases, indent=2))
    return 0 if all(cases.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
