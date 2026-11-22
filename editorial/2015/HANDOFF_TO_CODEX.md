# HANDOFF TO CODEX｜Director System V1.0

用户已确认：
- 导演主导方式A：金融纪录片式；
- 2015章节结尾A：阶段低点之后继续呈现反弹与修复；
- 信息严谨程度方案A：T1/T2/T3。

本轮GPT交付：
- editorial/2015/director/REFERENCE_DECONSTRUCTION.md
- editorial/2015/director/DIRECTOR_SYSTEM_V1.0.md
- editorial/2015/director/2015_STORY_ARCHITECTURE_V1.0.md
- editorial/2015/director/2015_BEAT_SHEET_V1.0.json
- editorial/2015/director/README.md

## 当前任务：DIRECTOR-V1.0-STRUCTURE-REVIEW

只做结构和数据审查，不开始编码渲染。

1. 检查Beat Sheet字段与现有DirectorTimeline、EditorialClock、renderer的映射差距。
2. 使用冻结 data/cyb_daily.csv 复核Beat Sheet所有行情锚点、区间百分比和日期。
3. 检查每个beat是否有市场时钟、事件时钟、镜头时钟、主视觉、辅助层、转场与验收条件。
4. 列出需要新增的渲染能力、现有可复用能力、缺少的数据／素材。
5. 检查2015年9月低点后反弹段是否按真实交易日顺序表达；不得将9月15日写成最终市场底。
6. 返回结构审计、数据差异和实现方案。不要自行改写GPT叙事或Beat Sheet。
7. 不修改V1.0.1内容包、冻结OHLC、正式427秒主表、原始素材或已批准视觉资产；不渲染视频、不推送main。

这是导演系统设计审查，不是立即执行新版本渲染。GPT收到审查回执后会形成下一轮工程契约。
