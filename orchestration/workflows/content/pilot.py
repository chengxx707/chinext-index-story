"""Editorial beat selection for the April–September 2015 pilot."""

from dataclasses import dataclass

from .market import Market, percent


PILOT_START = "2015-04-01"
PILOT_END = "2015-09-15"
STAGES = (
    ("P01", "4月参与背景与上涨", PILOT_START, "2015-06-03", "从4月交易活动推进到6月最高收盘。", "关注账户统计的口径，并分清上涨阶段的收盘与盘中价。"),
    ("P02", "高位反复与首轮回落", "2015-06-04", "2015-07-07", "6月中旬仍接近阶段高收，随后继续回落。", "同一段调整包含高位反复和加快回落，周末公告保留原日期。"),
    ("P03", "7月反弹与同期制度动态", "2015-07-08", "2015-07-23", "以7月7日收盘作比较，7月23日收盘回升。", "回升有自己的起止收盘，监管公告并列呈现。"),
    ("P04", "8月再跌与三个完整缺口", "2015-07-24", "2015-08-26", "以连续交易日的真实高低价显示整根K线之间的缺口。", "区分8月21、24、25日完整缺口、24—26日收益窗和盘后政策。"),
    ("P05", "9月低点与范围回看", "2015-08-27", PILOT_END, "推进到9月15日最低收盘，再同框回看6月最高收盘。", "区分9月2日盘中低点与9月15日收盘低点。"),
)


@dataclass(frozen=True)
class Beat:
    beat_id: str
    stage: str
    market_date: str
    purpose: str
    focus: str
    lines: tuple[str, ...]
    reading: int
    kind: str = "fact"
    camera: str = "medium"
    event_id: str | None = None
    link: tuple[str, str] | None = None
    source_line: str | None = None


@dataclass(frozen=True)
class EventBeat:
    event_id: str
    stage: str
    event_date: str
    anchor: str
    lines: tuple[str, ...]
    source_line: str
    purpose: str
    reading: int = 5
    quote: str | None = None


EVENT_BEATS = (
    EventBeat("april-multi-account", "P01", "2015-04-13", "2015-04-13", ("2015.04.13", "一人多户放开"), "中国结算", "交代市场参与制度背景。"),
    EventBeat("april-new-a-accounts", "P01", "2015-04-20/2015-04-24", "2015-04-24", ("2015.04.20—24", "单周新开A股账户", "413.03万户"), "中国结算｜统计周", "显示同期新开账户统计。", 6),
    EventBeat("may-letv-context", "P01", "2015-05", "2015-05-29", ("2015.05", "乐视网总市值一度超1,600亿元"), "企业同期背景｜总市值", "呈现同期企业报道，保留月度精度。", 6),
    EventBeat("june-pbc-faq", "P02", "2015-06-27", "2015-06-26", ("2015.06.27 · 周六", "央行定向降准", "并下调存贷款基准利率"), "中国人民银行｜答记者问", "并列周末政策与上一交易日行情。", 6),
    EventBeat("july-csrc-reduction", "P03", "2015-07-08", "2015-07-08", ("2015.07.08", "大股东及董监高减持限制"), "证监会公告〔2015〕18号", "交代7月初证券市场监管措施。"),
    EventBeat("july-csrc-voice", "P03", "2015-07-08", "2015-07-08", ("“非理性下跌”", "证监会公告中的描述"), "证监会公告〔2015〕18号｜2015.07.08", "保留同期机构的署名表述。", quote="非理性下跌"),
    EventBeat("july-csrc-cleanup", "P03", "2015-07-12", "2015-07-10", ("2015.07.12 · 周日", "清理整顿违法从事证券业务活动"), "证监会公告〔2015〕19号", "保留原公告日期与前一交易日。", 6),
    EventBeat("august-pbc-announcement", "P04", "2015-08-25", "2015-08-25", ("2015.08.25 18:15 · 盘后", "央行公布降息降准安排", "8月26日起降息 · 9月6日起降准"), "中国人民银行｜北京时间", "在8月25日行情之后显示公告及实施日期。", 7),
    EventBeat("september-cffex-rules", "P05", "2015-09-02", "2015-09-02", ("2015.09.02 公布", "股指期货管控措施", "9月7日起实施"), "中国金融期货交易所", "交代同期股指期货措施的市场范围。", 6),
    EventBeat("september-dividend-tax", "P05", "2015-09-07", "2015-09-07", ("2015.09.07 成文 · 9月8日施行", "持股超过一年", "股息红利暂免个人所得税"), "财政部等｜财税〔2015〕101号", "按时间并列税收政策与行情。", 7),
)


def _event_beats(mappings: list[dict], events: list[dict]) -> list[Beat]:
    event_map = {event["event_id"]: event for event in events}
    mapped = {item["event_id"]: item for item in mappings}
    beats = []
    for spec in EVENT_BEATS:
        decision = mapped.get(spec.event_id)
        if not decision or not decision["on_screen_eligible"]:
            continue
        event = event_map[spec.event_id]
        if decision["event_date"] != spec.event_date or decision["market_anchor"] != spec.anchor:
            continue
        if spec.quote:
            if not (event.get("attribution", "").startswith("中国证监会") and any(
                item["source_id"] == "csrc-18" and item["status"] == "matched" and spec.quote in item["excerpt"]
                for item in event["verification_notes"]["excerpts"]
            )):
                continue
        if spec.event_id == "august-pbc-announcement":
            dates = {item["measure"]: item["date"] for item in decision["implementation_dates"] if isinstance(item, dict)}
            if decision["announcement_at"] != "2015-08-25T18:15:34+08:00" or dates != {"降息": "2015-08-26", "降准": "2015-09-06"}:
                continue
        beats.append(Beat(
            spec.event_id, spec.stage, spec.anchor, spec.purpose, "attributed_voice" if spec.quote else "event",
            spec.lines, spec.reading, "opinion" if spec.quote else "fact", "medium", spec.event_id,
            source_line=spec.source_line,
        ))
    return beats


def _signed(value: float) -> str:
    return f"{value:+.2f}%".replace("-", "−")


def build_beats(market: Market, mappings: list[dict], events: list[dict], metrics: dict) -> list[Beat]:
    day = market.by_date
    april_end = day["2015-04-24"]
    april_open = day["2015-04-17"]
    high = day[metrics["highest_close"]["date"]]
    low = day[metrics["lowest_close"]["date"]]
    if high.date != "2015-06-03" or low.date != PILOT_END:
        raise ValueError("Pilot high/low dates do not match the frozen-market storyboard")
    before_peak = day["2015-04-01"]
    june_consolidation, june_selloff, july_trough, july_rebound = (
        day[d] for d in ("2015-06-12", "2015-06-19", "2015-07-07", "2015-07-23")
    )
    intraday_high = metrics["intraday_high"]
    intraday_low = metrics["intraday_low"]
    beats = [
        Beat("april-opening", "P01", PILOT_START, "建立创业板指与段落的观察起点。", "market", ("2015年4月", "创业板指 · 399006"), 3, camera="wide"),
        Beat("april-week", "P01", april_end.date, "在交易周末标出指数的收盘移动。", "market", ("4月20—24日", "创业板指周涨跌 " + _signed(percent(april_end.close, april_open.close))), 5),
        Beat("june-high-close", "P01", high.date, "用区间真实收盘端点建立峰值记忆。", "close_extremum", ("2015.06.03 · 阶段最高收盘", f"{high.close:,.2f}"), 6, camera="wide", link=(before_peak.date, high.date)),
        Beat("june-high-intraday", "P02", intraday_high["date"], "提示盘中高点和最高收盘是不同口径。", "intraday_extremum", (intraday_high["date"].replace("-", ".") + " · 盘中高点", f"{intraday_high['value']:,.2f}"), 4, camera="close"),
        Beat("june-consolidation", "P02", june_consolidation.date, "给高点后的高位反复留出阅读空间。", "market", ("2015.06.12 · 收盘", f"{june_consolidation.close:,.2f}", "较6月3日 " + _signed(percent(june_consolidation.close, high.close))), 5),
        Beat("june-selloff", "P02", june_selloff.date, "表现此前高位与本周收盘的真实距离。", "market", ("2015.06.19 · 收盘", f"{june_selloff.close:,.2f}", "较6月3日 " + _signed(percent(june_selloff.close, high.close))), 5),
        Beat("july-low-reference", "P02", july_trough.date, "为下一段收盘反弹给出可复核的比较基准。", "market", ("2015.07.07 · 收盘", f"{july_trough.close:,.2f}"), 4),
        Beat("july-rebound", "P03", july_rebound.date, "连起7月7日和23日两个真实收盘。", "market", ("7月7日至23日 · 收盘比较", _signed(percent(july_rebound.close, july_trough.close))), 6, link=(july_trough.date, july_rebound.date)),
    ]
    for number, row in enumerate(metrics["august_observations"], start=1):
        if not row["full_down_gap"]:
            continue
        beats.append(Beat(
            f"august-gap-{number}", "P04", row["date"], "留出空白显示整根日K之间真实的价格断层。", "gap",
            (row["date"].replace("-", "."), f"完整向下缺口  {number}/3", f"单日 {_signed(row['daily_return_percent'])}"),
            4, camera="close",
        ))
    august = metrics["august_24_26_return"]
    beats.extend([
        Beat("august-26", "P04", august["end_date"], "显示8月26日K线的实际覆盖，并单列收益统计窗口。", "market", ("2015.08.26 · 低开、日K区间重叠", "8月24—26日累计 " + _signed(august["percent"])), 6, camera="close"),
        Beat("september-intraday", "P05", intraday_low["date"], "提示盘中低点与阶段最低收盘的口径差异。", "intraday_extremum", (intraday_low["date"].replace("-", ".") + " · 盘中低点", f"{intraday_low['value']:,.2f}"), 4, camera="close"),
        Beat("september-low-close", "P05", low.date, "在同一真实价格投影中收束六月到九月的回撤。", "close_extremum", ("2015.09.15 · 阶段最低收盘", f"{low.close:,.2f}", "较6月3日最高收盘 " + _signed(metrics["peak_to_low_drawdown_percent"])), 7, camera="wide", link=(high.date, low.date)),
    ])
    april_volume = metrics["april_volume_week_on_week_percent"]
    if april_volume is not None:
        beats.append(Beat("april-volume", "P01", april_end.date, "用真实成交量补充4月交易参与。", "market",
                          ("4月20—24日 · 创业板指成交量", "较4月13—17日 " + _signed(april_volume)), 5))
    # Same-session close facts precede post-close events. For all other peers
    # authored events come first, continuing from the previous shot's projection.
    return sorted(_event_beats(mappings, events) + beats, key=lambda beat: (
        beat.market_date, beat.event_id == "august-pbc-announcement",
    ))
