"""Authored focus and caption phases for the pinned 2015 V1.0.2 director contract."""

MARKET = "L1_MARKET"
POLICY = "L2_EVENT"
STRUCTURE = "L3_MARKET_STRUCTURE"
COMPANY = "L4_INDUSTRY_COMPANY"
DOCUMENTARY = "L5_PEOPLE_SENTIMENT"
MACRO = "L6_MACRO_GLOBAL"

FLOW = "M1_MARKET"
KEY_POINT = "M2_KEY_POINT"
EVENT = "M3_EVENT_TAKEOVER"
ESTIMATE = "M4_COMPANY"
PHOTO = "M5_DOCUMENTARY"
SETTLEMENT = "M6_SETTLEMENT"


def phase(start, end, seconds, focus, mode, lines=(), **metadata):
    return {
        "start_date": f"2015-{start}",
        "end_date": f"2015-{end}",
        "seconds": seconds,
        "focus": focus,
        "mode": mode,
        "lines": list(lines),
        **metadata,
    }


PHASES = {
    "B01": [
        phase("06-03", "06-03", 8, MARKET, KEY_POINT, [
            "闪前 · 2015.06.03", "阶段最高收盘 3,982.25",
        ]),
    ],
    "B02": [
        phase("04-01", "04-01", 3, MARKET, FLOW, [
            "回到 2015.04.01", "创业板指收盘 2,404.91",
        ]),
        phase("04-01", "04-10", 7, MARKET, FLOW, ["4月10日 · 收盘 2,552.83"]),
    ],
    "B03": [
        phase("04-10", "04-13", 6, POLICY, EVENT, [
            "4月13日起", "A股“一人一户”限制放开",
        ], event_id="E-APR-01-01", event_variant="effective_date"),
        phase("04-13", "04-28", 8, STRUCTURE, EVENT, [
            "4月20—24日 · 新增A股账户", "413.03 万户",
            "4月28日 20:37 · 报道刊发",
        ], event_id="E-APR-01-04", event_variant="publisher_timestamp", event_time="20:37",
            statistics_range=["2015-04-20", "2015-04-24"], observation_window=["2015-04-20", "2015-04-24"]),
    ],
    "B04": [
        phase("04-28", "05-13", 8, COMPANY, ESTIMATE, [
            "5月13日 · 乐视网", "收盘总市值超过 1,500 亿元",
            "企业总市值",
        ], event_id="E-IND-01-04", event_variant="historical_observation"),
        phase("05-13", "05-29", 4, MARKET, FLOW, ["5月29日 · 收盘 3,542.84"]),
    ],
    "B05": [
        phase("05-29", "06-03", 12, MARKET, KEY_POINT, [
            "6月3日 · 阶段最高收盘", "3,982.25",
        ]),
    ],
    "B06": [
        phase("06-03", "06-05", 5, MARKET, KEY_POINT, [
            "6月5日 · 盘中高点 4,037.96", "同日收盘 3,885.83",
        ], anchor={"date": "2015-06-05", "field": "high"}),
        phase("06-05", "06-10", 3, MARKET, FLOW),
    ],
    "B07": [
        phase("06-10", "06-12", 4, POLICY, EVENT, [
            "6月12日 · 证监会重申", "不得为场外配资提供交易接口便利",
        ], event_id="E-JUN-01-01", event_variant="public_statement", motion_fraction=0.25),
        phase("06-12", "06-18", 5, STRUCTURE, EVENT, [
            "2015年6月 · 事后报道回顾", "沪深融资融券规模处于高位",
        ], event_id="E-JUN-01-04", event_variant="retrospective_statistic"),
        phase("06-18", "06-19", 3, MARKET, FLOW, ["6月19日 · 收盘 3,314.98"]),
    ],
    "B08": [
        phase("06-19", "06-26", 5, MARKET, KEY_POINT, [
            "6月26日 · 收盘 2,920.70", "较6月12日收盘 −25.10%",
        ], interval=["2015-06-12", "2015-06-26"], primary_lines=[0]),
        phase("06-26", "06-26", 4, POLICY, EVENT, [
            "6月27日 · 周末公告", "央行公布降息与定向降准",
        ], event_id="E-JUN-02-01", event_variant="announcement"),
        phase("06-26", "06-26", 3, POLICY, EVENT, [
            "6月28日 · 实施", "降息与定向降准",
        ], event_id="E-JUN-02-01", event_variant="june_implementation"),
        phase("06-26", "07-03", 4, MARKET, FLOW, ["7月3日 · 收盘 2,605.28"]),
    ],
    "B09": [
        phase("07-03", "07-03", 5, POLICY, EVENT, [
            "7月4日 · 21家券商承诺", "出资不低于1,200亿元", "投资蓝筹股ETF",
        ], event_id="E-JUN-02-02", event_variant="weekend_commitment"),
        phase("07-03", "07-03", 5, POLICY, EVENT, [
            "7月4日晚", "28家已获IPO批文公司暂缓发行",
        ], event_id="E-JUN-02-03", event_variant="weekend_company_announcement",
            secondary_layers=[
                {"layer": POLICY, "event_id": "E-JUN-02-02", "state": "faded_background"},
            ]),
        phase("07-03", "07-03", 6, POLICY, EVENT, [
            "7月5日 · 证监会公告", "央行将给予证金公司", "多种形式的流动性支持",
        ], event_id="E-JUN-02-04", event_variant="weekend_public_announcement",
            secondary_layers=[
                {"layer": POLICY, "event_id": "E-JUN-02-02", "state": "faded_background"},
                {"layer": POLICY, "event_id": "E-JUN-02-03", "state": "faded_background"},
            ]),
    ],
    "B10": [
        phase("07-03", "07-06", 2, MARKET, FLOW),
        phase("07-06", "07-07", 3, MARKET, KEY_POINT, ["7月7日 · 收盘 2,352.01"]),
        phase("07-07", "07-23", 7, MARKET, SETTLEMENT, [
            "7月7日→7月23日 · 收盘区间", "+26.19%", "7月23日 · 收盘 2,967.95",
        ], interval=["2015-07-07", "2015-07-23"]),
    ],
    "B11": [
        phase("07-23", "07-24", 2, MARKET, FLOW),
        phase("07-24", "07-27", 6, MARKET, KEY_POINT, [
            "7月27日 · 单日 −7.40%", "收盘 2,683.45",
        ]),
    ],
    "B12": [
        phase("07-28", "08-17", 7, MACRO, EVENT, [
            "8月11日", "人民币中间价报价机制调整",
        ], event_id="E-AUG-01-01", event_variant="policy_mechanism_announcement",
            anchor={"date": "2015-08-11", "field": "close"}),
        phase("08-17", "08-18", 6, MARKET, KEY_POINT, [
            "8月18日 · 单日 −6.08%", "收盘 2,504.17",
        ]),
        phase("08-18", "08-20", 3, MARKET, FLOW, ["8月20日 · 收盘 2,508.82"]),
    ],
    "B13": [
        phase("08-20", "08-21", 3.8, MARKET, KEY_POINT, [
            "8月21日 · 完整向下缺口 ①", "单日 −6.65%",
        ], gap="2015-08-21"),
        phase("08-21", "08-21", 3, MACRO, EVENT, [
            "8月21日 · 财新制造业PMI初值 47.1", "财新网页刊发 09:43:10",
        ], event_id="E-AUG-01-03", event_variant="publisher_webpage_timestamp"),
        phase("08-21", "08-24", 3.6, MARKET, KEY_POINT, [
            "8月24日 · 完整向下缺口 ②", "收盘 2,152.61 · 单日 −8.08%",
        ], gap="2015-08-24", motion_fraction=0.22),
        phase("08-24", "08-24", 3.6, DOCUMENTARY, PHOTO, [
            "2015.08.24 · 昆明", "中新社发 刘冉阳 摄",
        ], event_id="E-IMG-01-01", event_variant="documentary",
            asset_id="IMG-20150824-01", evidence_flag="PHOTO_EXACT_INPUT_REQUIRED_FOR_VISUAL_TEST"),
    ],
    "B14": [
        phase("08-24", "08-25", 7, MARKET, KEY_POINT, [
            "8月25日 · 完整向下缺口 ③", "开盘 1,996.04",
            "收盘 1,990.71 · 跌破2,000点", "单日 −7.52%",
        ], gap="2015-08-25", primary_lines=[2]),
        phase("08-25", "08-25", 9, POLICY, EVENT, [
            "8月25日 · 盘后", "央行公布降息降准安排",
            "8月26日起降息 · 9月6日起降准", "央行网页 18:15:34",
        ], event_id="E-AUG-02-05", event_variant="announcement"),
    ],
    "B15": [
        phase("08-25", "08-26", 10, MARKET, KEY_POINT, [
            "8月26日 · 降息实施日", "创业板指收盘 1,890.04", "单日 −5.06%",
        ], event_id="E-AUG-02-05", event_variant="rate_cut_implementation"),
    ],
    "B16": [
        phase("08-26", "09-02", 6, MARKET, KEY_POINT, [
            "9月2日 · 盘中低点 1,779.18", "较6月5日盘中高点 −55.94%",
        ], anchor={"date": "2015-09-02", "field": "low"}),
        phase("09-02", "09-15", 6, MARKET, KEY_POINT, [
            "9月15日 · 阶段最低收盘 1,797.56", "当日盘中低点 1,794.29",
            "较6月3日最高收盘 −54.86%",
        ], interval=["2015-06-03", "2015-09-15"], primary_lines=[0]),
    ],
    "B17": [
        phase("09-15", "09-16", 4, MARKET, KEY_POINT, [
            "9月16日 · 单日 +7.16%", "收盘 1,926.25",
        ]),
        phase("09-16", "09-21", 4, MARKET, KEY_POINT, [
            "9月21日 · 单日 +4.83%", "收盘 2,079.06",
        ]),
        phase("09-21", "09-25", 4, MARKET, KEY_POINT, [
            "9月25日 · 单日 −4.06%", "收盘 2,020.97",
        ]),
        phase("09-25", "09-28", 6, MARKET, KEY_POINT, [
            "9月28日 · 单日 +5.01%", "收盘 2,122.26",
        ]),
        phase("09-28", "09-29", 4, MARKET, KEY_POINT, [
            "9月29日 · 单日 −1.12%", "收盘 2,098.57",
        ]),
    ],
    "B18": [
        phase("09-29", "09-30", 3, MARKET, FLOW),
        phase("09-30", "10-08", 5, MARKET, KEY_POINT, [
            "10月8日 · 单日 +5.17%", "收盘 2,190.31",
        ]),
        phase("10-08", "10-12", 5, MARKET, KEY_POINT, [
            "10月12日 · 单日 +4.52%", "收盘 2,316.78",
        ]),
        phase("10-12", "11-25", 9, MARKET, SETTLEMENT, [
            "9月15日→11月25日 · 收盘区间", "+61.19% · 阶段修复",
            "11月25日 · 收盘 2,897.57", "此前 6/3→9/15 收盘回撤 −54.86%",
        ], interval=["2015-09-15", "2015-11-25"]),
    ],
}
