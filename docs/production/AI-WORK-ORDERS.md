# AI Work Orders｜GPT / Codex / External Research

> 规则：状态必须由实际执行记录更新。计划不等于运行；等待不等于后台工作。

| Work Order | 负责人 | 状态 | 输入 | 交付/退出条件 |
|---|---|---|---|---|
| EXT-2015-01 | 外部AI | COMPLETED | 8项采集任务 | 原始研究包回传 |
| OPS-001 | Codex | REVIEWED_WITH_CONDITIONS | 本地调度器 | 后续集成依项目审查 |
| OPS-001.1 | Codex | IMPLEMENTED_REPORTED | 调度器与DAG | 依赖修正和验证证据 |
| WF-01A | Codex + GPT | IN_PROGRESS | 外部资料、档案、行情 | 39条raw记录映射、证据审计 |
| WF-01B | GPT主编 / Codex编译 | CANDIDATE | 研究包与冻结OHLC | GPT批准的故事/分镜候选及Schema校验 |
| GPT-2015-AUDIT | GPT | IN_PROGRESS | 23规范化事件、原始回交包 | 逐条核验记录、争议和缺口 |
| GPT-2015-STORY | GPT | PENDING | 完成核验的研究包 | 六阶段历史叙事 |
| GPT-2015-BOARD | GPT | PENDING | 历史叙事 | 画面文字与镜头分镜 |
| CODEX-2015-IMPORT | Codex | WAITING | GPT候选包 | 导入、Schema校验、预览，不改正式主表 |
| USER-D01 | 用户 | DECISION_REQUIRED | T1/T2/T3严谨标准 | 确认或调整内容证据门槛 |

## 工作状态定义

- CREATED：已登记，尚未开始。
- RUNNING：当前执行轮次正在实际处理。
- WAITING：等待明确外部输入或审批。
- COMPLETED：有交付物和可追溯证据。
- BLOCKED：存在阻断项，列明原因及解除条件。
- FAILED：执行失败，保留日志和恢复点。

## 当前交接规则

GPT负责研究判断、历史叙事、屏幕文字和导演候选；Codex负责结构校验、确定性计算、编译、渲染和工程QA。Codex不得自行把未核验事件升格为正式上屏事实。

所有候选内容进入 editorial/2015/ 下的候选目录。只有用户批准后才允许进入正式生产配置。禁止直接覆盖 config/production/film_master_v1.json。
