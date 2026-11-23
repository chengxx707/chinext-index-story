"""Independent Decimal checks of the V1.0.2 director's frozen market inputs."""

from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from hashlib import sha256
from io import StringIO
from pathlib import Path
import csv


FIELDS = ("open", "high", "low", "close")
CENT = Decimal("0.01")
FROZEN_OHLC_SHA256 = "d832c794deaabaeda7b3803e5e93da471d6075f5d807b65714b9ab243d477205"
CONTRACT_ANCHORS = (
    ("B03 effective-date observation", "2015-04-13", "close", "2577.78"),
    ("B07 public regulatory answer", "2015-06-12", "close", "3899.71"),
    ("B07 June retrospective observation", "2015-06-18", "close", "3504.55"),
    ("B10 first session after weekend", "2015-07-06", "close", "2493.83"),
    ("B12 currency mechanism observation", "2015-08-11", "close", "2698.91"),
    ("B16 intraday period low", "2015-09-02", "low", "1779.18"),
    ("B16 Sept15 same-row intraday low", "2015-09-15", "low", "1794.29"),
)
CONTRACT_RETURNS = (
    ("July rebound", "2015-07-07", "close", "2015-07-23", "close", "26.19"),
    ("July 23–27 cumulative", "2015-07-23", "close", "2015-07-27", "close", "-9.59"),
    ("June to September close drawdown", "2015-06-03", "close", "2015-09-15", "close", "-54.86"),
    ("June to September intraday extremes", "2015-06-05", "high", "2015-09-02", "low", "-55.94"),
    ("September rebound through 28th", "2015-09-15", "close", "2015-09-28", "close", "18.06"),
    ("September to November chapter recovery", "2015-09-15", "close", "2015-11-25", "close", "61.19"),
    ("August 24–26 cumulative", "2015-08-21", "close", "2015-08-26", "close", "-19.30"),
    ("August 25 daily", "2015-08-24", "close", "2015-08-25", "close", "-7.52"),
    ("August 26 daily", "2015-08-25", "close", "2015-08-26", "close", "-5.06"),
)


def _number(value) -> Decimal:
    return Decimal(str(value))


def _display(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def _record(checks, label, actual, expected):
    def serializable(value):
        return str(value) if isinstance(value, Decimal) else value

    checks.append({"id": label, "actual": serializable(actual), "expected": serializable(expected),
                   "passed": actual == expected})


class _Market:
    def __init__(self, csv_path: Path):
        payload = csv_path.read_bytes()
        self.sha256 = sha256(payload).hexdigest()
        self.rows = {}
        prior = None
        for entry in csv.DictReader(StringIO(payload.decode("utf-8-sig"), newline="")):
            day = entry["date"]
            values = {field: _number(entry[field]) for field in FIELDS}
            if (day != date.fromisoformat(day).isoformat() or prior is not None and day <= prior
                    or not all(v.is_finite() and v > 0 for v in values.values())
                    or not values["low"] <= min(values["open"], values["close"])
                    <= max(values["open"], values["close"]) <= values["high"]):
                raise ValueError(f"Frozen OHLC calendar or price ordering failed at {day}")
            self.rows[day] = values
            prior = day
        if not self.rows:
            raise ValueError("Frozen OHLC data is empty")
        self.days = list(self.rows)
        self.index = {day: i for i, day in enumerate(self.days)}

    def price(self, day, field="close"):
        return self.rows[day][field]

    def previous(self, day):
        position = self.index[day]
        if position == 0:
            raise ValueError(f"No previous trading row for {day}")
        return self.days[position - 1]

    def previous_calendar(self, day):
        return max(trade for trade in self.days if trade < day)

    def next_calendar(self, day):
        return next(trade for trade in self.days if trade > day)

    def window(self, start, end):
        return self.days[self.index[start]:self.index[end]+1]

    def ohlc(self, day):
        return {field: str(value) for field, value in self.rows[day].items()}


def _price_check(results, market, label, anchor):
    day, field = anchor["date"], anchor["field"]
    value = anchor.get("value")
    expected = None if value is None else _number(value)
    actual = market.rows.get(day, {}).get(field)
    results.append({"id": label, "date": day, "field": field,
                    "claimed": str(expected) if expected is not None else None,
                    "actual": str(actual) if actual is not None else None,
                    "derived_only": expected is None,
                    "actual_ohlc": market.ohlc(day) if day in market.rows else None,
                    "passed": actual is not None and (expected is None or actual == expected)})


def _return_check(results, market, label, start, start_field, end, end_field, expected):
    before = market.price(start, start_field)
    after = market.price(end, end_field)
    pct = (after / before - 1) * 100
    expected = _number(expected)
    results.append({"id": label, "start_date": start, "start_field": start_field, "start_value": str(before),
                    "end_date": end, "end_field": end_field, "end_value": str(after),
                    "computed_percent": str(pct), "rounded_percent": str(_display(pct)),
                    "claimed_percent": str(expected), "passed": _display(pct) == expected})


def _check_keyframe(market, price_checks, return_checks, checks, marker):
    label, record = marker
    day = record["date"]
    if "field" in record:
        _price_check(price_checks, market, label, record)
    if "daily_return_pct" in record:
        previous = market.previous(day)
        if "base_date" in record:
            _record(checks, label+" exact previous trading day", record["base_date"], previous)
        if "base_close" in record:
            _record(checks, label+" exact previous trading close", _number(record["base_close"]), market.price(previous))
        _return_check(return_checks, market, label+" daily", previous, "close", day, "close", record["daily_return_pct"])
    if "range_return_pct" in record:
        base = record["range_base_date"]
        _record(checks, label+" range base close", _number(record["range_base_close"]), market.price(base))
        _return_check(return_checks, market, label+" range", base, "close", day, "close", record["range_return_pct"])


def audit_market(beats: list[dict], event_register: dict, csv_path: Path) -> dict:
    """Audit authored facts and window coverage without touching candidate or CSV files."""
    market = _Market(csv_path)
    checks, price_checks, return_checks, joins, windows, calendar_only = [], [], [], [], [], []
    _record(checks, "frozen OHLC source SHA-256", market.sha256, FROZEN_OHLC_SHA256)
    _record(checks, "frozen OHLC row count", len(market.rows), 3992)
    expected_ids = [f"B{n:02d}" for n in range(1, 19)]
    _record(checks, "ordered beat IDs", [beat["id"] for beat in beats], expected_ids)
    cursor = 0
    covered = set()
    prior_end = None
    for beat in beats:
        bid = beat["id"]
        start, end = beat["market_window"]
        valid_window = start in market.index and end in market.index and start <= end
        _record(checks, bid+" chronological trading window", valid_window, True)
        if not valid_window:
            continue
        duration = beat["duration_seconds"]
        _record(checks, bid+" positive integral budget", type(duration) is int and duration > 0, True)
        days = market.window(start, end)
        if bid != "B01":
            covered.update(days)
        if prior_end is not None:
            step = market.index[start] - market.index[prior_end]
            allowed = ((prior_end, start) == ("2015-06-03", "2015-04-01")) if bid == "B02" else step in (0, 1)
            joins.append({"next_beat": bid, "previous_end": prior_end, "current_start": start,
                          "trading_row_step": step, "intentional_hook_reset": bid == "B02", "passed": allowed})
        prior_end = end
        windows.append({"beat_id": bid, "start_date": start, "end_date": end,
                        "trading_dates": days, "start_seconds": cursor, "end_seconds_exclusive": cursor+duration})
        cursor += duration
        for index, anchor in enumerate([beat["anchor"], *beat.get("secondary_anchors", [])]):
            label = bid+" primary" if index == 0 else f"{bid} secondary {index}"
            _record(checks, label+" lies in beat", anchor["date"] in days, True)
            _price_check(price_checks, market, label, anchor)
        records = beat.get("market_keyframes", [])
        key_dates = [record["date"] for record in records]
        _record(checks, bid+" keyframe dates monotone", key_dates, sorted(key_dates))
        for index, record in enumerate(records, 1):
            label = f"{bid} keyframe {index}"
            day = record["date"]
            _record(checks, label+" calendar bounds", start <= day <= end, True)
            if record["role"].endswith("_no_market_candle"):
                _record(checks, label+" is event only", day not in market.rows and "field" not in record and
                        "value" not in record, True)
                calendar_only.append({"beat_id": bid, "date": day, "role": record["role"],
                                      "market_candle": False, "preceding_trade": market.previous_calendar(day),
                                      "following_trade": market.next_calendar(day)})
                continue
            _record(checks, label+" is actual trading row", day in days, True)
            if day in market.rows:
                _check_keyframe(market, price_checks, return_checks, checks, (label, record))
        for event in beat.get("event_clock", []):
            if anchor := event.get("market_anchor"):
                label = f"{bid} event {event['event_id']}"
                _record(checks, label+" anchor lies in beat", anchor["date"] in days, True)
                _price_check(price_checks, market, label, anchor)
    _record(checks, "V1.0.2 total candidate budget in seconds", cursor, 240)
    _record(checks, "main market coverage without any skipped session", sorted(covered),
            market.window("2015-04-01", "2015-11-25"))
    _record(checks, "June implementation and announcement are nontrading checkpoints",
            [item["date"] for item in calendar_only], ["2015-06-27", "2015-06-28"])
    by_id = {row["beat_id"]: row for row in windows}
    for bid, start, end in (
        ("B01", "2015-06-03", "2015-06-03"), ("B08", "2015-06-19", "2015-07-03"),
        ("B09", "2015-07-03", "2015-07-03"), ("B10", "2015-07-03", "2015-07-23"),
        ("B11", "2015-07-23", "2015-07-27"), ("B12", "2015-07-28", "2015-08-20"),
        ("B16", "2015-08-26", "2015-09-15"), ("B17", "2015-09-15", "2015-09-29"),
        ("B18", "2015-09-29", "2015-11-25"),
    ):
        actual = by_id.get(bid, {})
        _record(checks, bid+" exact contract window", [actual.get("start_date"), actual.get("end_date")], [start, end])
    authored_beats = {beat["id"]: beat for beat in beats}
    for bid, required_days in (
        ("B08", "06-19 06-26 06-27 06-28 06-29 07-03"),
        ("B10", "07-03 07-06 07-07 07-23"), ("B11", "07-23 07-24 07-27"),
        ("B12", "07-28 08-11 08-18 08-20"), ("B13", "08-20 08-21 08-24"),
        ("B17", "09-15 09-16 09-21 09-25 09-28 09-29"),
        ("B18", "09-29 09-30 10-08 10-09 10-12 11-25"),
    ):
        expected = ["2015-"+day for day in required_days.split()]
        present = {item["date"] for item in authored_beats.get(bid, {}).get("market_keyframes", [])}
        _record(checks, bid+" assigned checkpoints present", [day for day in expected if day in present], expected)
    for label, day, field, value in CONTRACT_ANCHORS:
        _price_check(price_checks, market, label, {"date": day, "field": field, "value": value})
    for expected in CONTRACT_RETURNS:
        _return_check(return_checks, market, *expected)

    event_anchors = []
    for item in event_register["events"]:
        if anchor := item.get("market_anchor"):
            eid, day = item["event_id"], item["date"]
            _price_check(price_checks, market, "event register "+eid, anchor)
            if item["role"].startswith("weekend_"):
                _record(checks, eid+" weekend date has no OHLC", day in market.rows, False)
                _record(checks, eid+" frozen previous trading close", anchor["date"], market.previous_calendar(day))
            elif item["role"] == "official_pbc_webpage_timestamp":
                _record(checks, eid+" freezes Aug25 close", anchor["date"], "2015-08-25")
            event_anchors.append({"event_id": eid, "event_date": day, "date_is_trading_day": day in market.rows,
                                  "anchor_date": anchor["date"], "next_real_trade": market.next_calendar(day)})
    metrics = {item["metric_id"]: item for item in event_register["events"] if "metric_id" in item}
    etf = metrics["E-SEP-ETF-01"]
    before = _number(etf["start_shares"].removesuffix("亿份"))
    after = _number(etf["end_shares"].removesuffix("亿份"))
    change = (after / before - 1) * 100
    _record(checks, "ETF percentage arithmetic from cited endpoints", _display(change), _number(etf["change_pct"]))
    _record(checks, "ETF source remains T2 with original not imported",
            etf["tier"].startswith("T2_") and not etf["first_party_original_imported"], True)
    beat_etf = next((item for item in authored_beats.get("B17", {}).get("event_clock", [])
                     if item.get("event_id") == etf["metric_id"]), {})
    etf_fields = {"date": "observation_start", "observation_end": "observation_end",
                  "source_publication_date": "publication_date", "value_from": "start_shares", "value_to": "end_shares",
                  "change_pct": "change_pct", "source_tier": "tier"}
    for cue_key, registry_key in etf_fields.items():
        _record(checks, "B17 ETF cue/register agrees on "+cue_key, beat_etf.get(cue_key), etf[registry_key])

    gaps = []
    for day, expected in (("2015-08-21", "27.67"), ("2015-08-24", "94.37"),
                          ("2015-08-25", "104.58"), ("2015-08-26", "-57.54")):
        previous = market.previous(day)
        previous_low, current_high = market.price(previous, "low"), market.price(day, "high")
        points = previous_low - current_high
        gaps.append({"date": day, "previous_trading_day": previous, "previous_low": str(previous_low),
                     "current_high": str(current_high), "points": str(points), "full_down_gap": points > 0,
                     "passed": points == _number(expected)})
    extrema = []
    pilot_window = market.window("2015-04-01", "2015-11-25")
    for title, field, select, expected_date, expected_price in (
        ("highest_close", "close", max, "2015-06-03", "3982.25"),
        ("highest_high", "high", max, "2015-06-05", "4037.96"),
        ("lowest_close", "close", min, "2015-09-15", "1797.56"),
        ("lowest_low", "low", min, "2015-09-02", "1779.18"),
    ):
        day = select(pilot_window, key=lambda d: market.price(d, field))
        value = market.price(day, field)
        extrema.append({"id": title, "date": day, "field": field, "value": str(value),
                        "passed": (day, value) == (expected_date, _number(expected_price))})
    failures = [item for group in (checks, price_checks, return_checks, joins, gaps, extrema)
                for item in group if not item["passed"]]
    return {
        "passed": not failures, "failures": failures, "csv_sha256": market.sha256, "csv_row_count": len(market.rows),
        "duration_seconds": cursor, "nominal_frames_30fps": cursor*30, "market_windows": windows,
        "chronological_trade_count": len(covered),
        "market_joins": joins, "calendar_only_checkpoints": calendar_only, "event_market_anchors": event_anchors,
        "price_checks": price_checks, "return_checks": return_checks, "checks": checks,
        "stage_extrema": extrema, "august_gap_checks": gaps,
        "reported_t2_metrics": {
            "etf_share_change": {"source_basis": "reported endpoints, original exchange file not imported",
                                 "observation_start": etf["observation_start"], "observation_end": etf["observation_end"],
                                 "publication_date": etf["publication_date"], "computed_percent": str(change),
                                 "expected_display": str(etf["change_pct"]), "value_unit": "亿份"},
            "two_exchange_turnover": {"reported_value": metrics["E-SEP-TURNOVER-01"]["value"],
                                      "scope": "沪深两市合计", "verified_from_index_csv": False},
        },
    }
