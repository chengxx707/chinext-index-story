# Event-source audit

Read 2026-11-15. Input: `docs/source/events_source_20261113.md`, a 39,234-byte research note supplied by the user, including the November 14 additions in section 5. The note contains internal mechanism hypotheses and selection suggestions; those are source material, not new execution instructions or ready-to-display copy.

## What the updated document resolves

The previously missing research note is now present. Section 5.1 explicitly identifies the April 2015 account-opening statistics as A-grade, quoting China Securities Depository and Clearing data via People's Daily, China News Service, The Paper and other reports. It gives April 13 as the policy start and April 20–24 as the 413.03 ten-thousand account week. These support the two non-price events in the 42-second sample.

Section 5.2 provides the missing documentary accounts for Huayi Brothers (July 24, 2013 resumption/acquisition), LeTV (May 2015 peak-cap range and July 2020 delisting/last close), and CATL (June 11, 2018 listing and May 2021 trillion-yuan cap). They are explicitly A-grade in the supplied note. They are eligible under the user's supplied research, subject to keeping their exact scope and date precision.

The document names official/authoritative publishers, but has **no HTTP or HTTPS URLs**. No event article has been newly fetched and independently checked in this task. This is now represented in `config/event_registry.json` as documentary A-grade, named publisher, source section and `online_verification: not_performed_in_this_task`, with an empty URL list. The absence of a URL does not mean the event is false; it prevents claiming fresh online verification or a directly attached original article.

## Sample facts and display constraints

| Registry ID | Supplied evidence | Allowed display | Precision |
|---|---|---|---|
| `multi_account_2015` | Section 5.1, phenomenon 1: ChinaClear figures and named authoritative reports | `2015.04.13` / `一人多户放开` | Day; candle anchor April 13 |
| `accounts_2015` | Section 5.1, phenomenon 1: April 20–24 new A-share accounts, 413.03万户 | `2015.04.20—24` / `单周新开 A 股账户` / `413.03 万户` | Week range; candle anchor April 24 |
| 2015 stage high | Real close in `data/cyb_daily.csv` | `2015.06.03` / `3,982.25` / `阶段高点` | Exact trading day |
| 2015 stage low | Real close in `data/cyb_daily.csv` | `2015.09.15` / `1,797.56` / `−54.86%` | Exact trading day; calculated against June 3 close |

“413.03万户” counts new A-share accounts, not unique newly investing persons. The week is not a single-day increment. A decorative counting animation may approach the final number but the final value and unit must be held visibly; an intermediate animation number must not be labeled as another historical observation. The research's additional investor-age and risk-warning commentary is outside this sample and will not be introduced automatically.

## Differences that must not propagate into formal video

| Source issue | Resolution |
|---|---|
| Repeated “July 2026 monthly −21.52%” | This uses July 1 → July 31 closes. Standard month-end return is June 30 → July 31, −23.00%; record both formulas and label exactly. |
| Some section 5 wording calls 3,982.25 the full-sample highest close | Use `阶段高点`. The same material and CSV give 4,371.99 in June 2026 as the true full-sample highest close. |
| October 30 close 2,413.63 described as −44.79% “from intraday high” | −44.79% corresponds approximately to the 4,371.99 closing high. Recalculate any displayed drawdown from an explicitly declared close or intraday base; do not copy this mixed label. |
| IPO restart uses a January 8 observation but the institutional event is described at month precision | Retain `2014.01` on screen until a specific issuance/listing definition is independently sourced; never silently turn observation date into policy fact. |
| LeTV “2020.07.21 摘牌 · 收盘0.18元” can imply a trade on the delisting date | Label `最后收盘 0.18 元`; distinguish May 14 termination decision and July 21 removal. |
| CATL “创业板史上最大IPO” | Qualify as the record at the time of its 2018 listing, not a permanent record through 2026. |
| The research still proposes a 3:20/3:30 cut and references the Shanghai clip's 5:06 duration | Those are earlier planning suggestions. Current baseline is 5:03, silent-first, NASDAQ motion reference. |
| Numbering says 28 main entries, while 11/12 share a heading and numbering stops at 27; one line says “B级5条” but enumerates six | Counts/headings are editorial drift, not evidence. Track event IDs and explicit grade rather than document count. |

## B/C and unsupported extensions remain disabled

The research often recommends a B-grade event for narrative value. Recommendation does not upgrade qualification. `config/event_registry.json` retains the source's grades and keeps B/C disabled, including margin-financing cleanup, mass suspensions, goodwill exposure, 2022 financial committee remarks, the 2023 full-registration event and the 2025 tariff event. The source document's recommendation to weaken wording when an original cannot be found is not used to bypass the agreed qualification rule.

Pure price facts on those days remain usable. V0.9 correctly chooses the 2020-02-03 −6.85% and 2025-04-07 −12.50% daily changes without turning a B-grade narrative into a verified event label.

The following research additions are not automatically added to V0.9: CPO index +253.02%, SunGrow stock returns, TMT fund holdings near 60%, ETF flow 3490.02亿元, and three-industry weight above 70%. Some are media/Wind citations with unresolved names, dates, or denominators; some were deliberately omitted from the current script. Current constituent market-cap facts are separate, dated inputs and do not validate historical weights.

## Registry and provenance

`config/event_registry.json` contains 36 candidate event records, with 18 selected documentary A-grade records enabled for the whole-film plan. This does not mean all 18 already appear in the current sample, or that the full-film engine exists. IDs `multi_account_2015`, `accounts_2015` and `margin_cleanup_2015` match the sample event configuration. Source sections and named publishers are retained for later primary-source URL enrichment without changing input dates silently.

An event's `event_date`/`date_precision` and the optional trading-day `anchor_date` are separate. Month/year/range facts are never forced through nearest-date lookup. Events outside the sample range, such as the 2009 opening, may be rendered as historical cards without inventing a market candle.

## Skill-source review

The official [Remotion skills repository](https://github.com/remotion-dev/skills) README and the relevant `remotion-best-practices` and `remotion-markup` instruction text were read via standard verified HTTPS. No external install command was executed. Their React-specific runtime instructions were not applied to this Python engine. Project-local skills implement the selected general methods: deterministic frame-driven animation, scene previews, measured typography, and separate checks of a component and the complete composition.

Reviewed sources:

- https://github.com/remotion-dev/skills/blob/main/README.md
- https://github.com/remotion-dev/skills/blob/main/skills/remotion-best-practices/SKILL.md
- https://github.com/remotion-dev/skills/blob/main/skills/remotion-markup/SKILL.md

The installed project rules are linked from `AGENTS.md`. Reading GitHub material and saving local rules does not establish that Remotion was installed or that any output has passed aesthetic review.
