# HANDOFF TO CODEX｜2015内容审计与生产协作

协作分支：`editorial/gpt-2015`

## 当前任务

1. 保持Standby，不自行重写2015历史叙事或分镜。
2. 可读取本分支的：
   - `docs/production/PROJECT-DASHBOARD.md`
   - `docs/production/AI-WORK-ORDERS.md`
   - `editorial/2015/01-research/event-audit-register.md`
3. 不修改 `config/production/film_master_v1.json`、正式事件注册表、原始资料和已批准视觉资产。
4. 不触发渲染。

## GPT下一步内容交付

GPT将独立复核事件、完成raw-to-canonical映射、形成历史叙事和导演候选。完成后会在本分支新增版本化候选包，并更新本文件，给出确切Commit SHA及Codex任务。

## Codex后续接单条件

只有收到明确的 `CODEX_READY` 交接，才执行：
- Schema验证；
- 数据/日期/市场锚点一致性校验；
- 候选配置编译；
- 指定镜头预览；
- 产物Manifest与QA报告。

Codex不得把WF-01A的VERIFIED标签视为用户批准，也不得把GPT候选自动提升为正式主表。
