"""Derive period observations from the frozen trading calendar and OHLC."""

from bisect import bisect_left, bisect_right
import csv
from dataclasses import dataclass
from datetime import date
from math import isfinite
from pathlib import Path
from statistics import stdev

from tools.validate_project import Report, validate_market_rows


MARKET_SOURCE = "data/cyb_daily.csv"


def percent(value: float, basis: float) -> float:
    return round((value / basis - 1) * 100, 6)


@dataclass(frozen=True)
class TradingDay:
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: float | None = None

    def close_point(self) -> dict:
        return {"date": self.date, "value": self.close}


class Market:
    def __init__(self, path: Path):
        with path.open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        report = Report()
        validate_market_rows(rows, report)
        errors = report.as_dict()["problems"]
        if errors:
            raise ValueError(f"Invalid frozen market rows: {errors}")
        self.days = tuple(self._day(row) for row in rows)
        self.dates = tuple(day.date for day in self.days)
        self.by_date = dict(zip(self.dates, self.days, strict=True))

    @staticmethod
    def _day(row: dict) -> TradingDay:
        value = row.get("volume")
        volume = None if value is None or not value.strip() else float(value)
        if volume is not None and (not isfinite(volume) or volume < 0):
            raise ValueError(f"Invalid volume at {row['date']}")
        return TradingDay(row["date"], *(float(row[key]) for key in ("open", "high", "low", "close")), volume)

    def interval(self, start: str, end: str) -> tuple[int, tuple[TradingDay, ...]]:
        start_day, end_day = date.fromisoformat(start), date.fromisoformat(end)
        if start_day > end_day or start < self.dates[0] or end > self.dates[-1]:
            raise ValueError(f"Market interval outside frozen trading calendar: {start}–{end}")
        index = bisect_left(self.dates, start)
        rows = self.days[index:bisect_right(self.dates, end)]
        if not rows:
            raise ValueError(f"Market interval contains no trading date: {start}–{end}")
        return index, rows

    def observations(self, start: str, end: str) -> list[dict]:
        index, rows = self.interval(start, end)
        observations = []
        for offset, day in enumerate(rows, index):
            previous = self.days[offset - 1] if offset else None
            observations.append({
                "date": day.date, "open": day.open, "high": day.high, "low": day.low, "close": day.close,
                "previous_trading_date": previous.date if previous else None,
                "previous_close": previous.close if previous else None,
                "previous_low": previous.low if previous else None,
                "daily_return_percent": percent(day.close, previous.close) if previous else None,
                "opened_below_previous_close": day.open < previous.close if previous else None,
                "full_down_gap": day.high < previous.low if previous else None,
            })
        return observations

    def analytics(self, period_id: str, title: str, start: str, end: str) -> dict:
        index, rows = self.interval(start, end)
        first, last = rows[0], rows[-1]
        baseline = self.days[index - 1] if index else None
        directions = (max(rows, key=lambda row: row.high), min(rows, key=lambda row: row.low))
        closes = (max(rows, key=lambda row: row.close), min(rows, key=lambda row: row.close))
        peak = first
        drawdown = {"peak": first.close_point(), "trough": first.close_point(), "percent": 0.0}
        for current in rows:
            if current.close > peak.close:
                peak = current
            value = percent(current.close, peak.close)
            if value < drawdown["percent"]:
                drawdown = {"peak": peak.close_point(), "trough": current.close_point(), "percent": value}
        daily = self.observations(start, end)
        returns = [item["daily_return_percent"] for item in daily if item["daily_return_percent"] is not None]
        volumes = [row.volume for row in rows if row.volume is not None]
        return {
            "period_id": period_id, "title": title, "market_source": MARKET_SOURCE,
            "start_date": start, "end_date": end,
            "first_trading_day": first.date, "last_trading_day": last.date,
            "calendar_days_inclusive": (date.fromisoformat(end) - date.fromisoformat(start)).days + 1,
            "trading_days": len(rows),
            "highest_close": closes[0].close_point(), "lowest_close": closes[1].close_point(),
            "intraday_high": {"date": directions[0].date, "value": directions[0].high},
            "intraday_low": {"date": directions[1].date, "value": directions[1].low},
            "start_close": first.close_point(), "end_close": last.close_point(),
            "return_basis": baseline.close_point() if baseline else None,
            "period_return_percent": percent(last.close, baseline.close) if baseline else None,
            "close_to_close_return_percent": percent(last.close, first.close),
            "max_drawdown": drawdown,
            "daily_volatility_percent": round(stdev(returns), 6) if len(returns) > 1 else None,
            "range_amplitude_percent": round((directions[0].high - directions[1].low) / baseline.close * 100, 6)
            if baseline else None,
            "full_down_gap_dates": [item["date"] for item in daily if item["full_down_gap"]],
            "volume": {
                "source_column": "volume", "unit": "CSV原始单位（未换算）",
                "observed_trading_days": len(volumes),
                "total": sum(volumes) if len(volumes) == len(rows) else None,
                "average_per_trading_day": round(sum(volumes) / len(rows), 6) if len(volumes) == len(rows) else None,
            } if volumes else None,
        }


METRIC_RULES = {
    "period_return_percent": "期末收盘÷期首前一个交易日收盘−1，百分数",
    "close_to_close_return_percent": "期末收盘÷窗口首个交易日收盘−1，百分数",
    "max_drawdown": "窗口内每日收盘相对之前窗口内运行最高收盘的最大跌幅，百分数",
    "daily_volatility_percent": "窗口内日收盘收益率的样本标准差，百分数，未年化",
    "range_amplitude_percent": "(窗口内盘中最高−盘中最低)÷期首前一个交易日收盘，百分数",
    "full_down_gap": "当日最高严格低于前一交易日最低",
    "volume": "仅使用源 CSV volume 列。缺行时不估算该窗口总量与日均量",
}
