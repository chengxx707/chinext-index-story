# 生产调度进度

统计来自已持久化的任务状态与尝试记录。

- A 线 · 完整视频生产　BLOCKED 7，PASSED 5
- B 线 · 视觉开发　BLOCKED 2，PASSED 1

| 任务 | 状态 | 尝试次数 | 说明 |
|---|---|---:|---|
| `A.2015-master-adoption` | BLOCKED | 0 | Human approval required for this input hash |
| `A.2015-research` | PASSED | 1 |  |
| `A.2015-story` | PASSED | 1 |  |
| `A.album-render` | BLOCKED | 0 | Prerequisites have not passed: A.archive-photos (BLOCKED) |
| `A.archive-photos` | BLOCKED | 1 | 合格档案照片 0 张，覆盖 0 个年份。现有工具要求至少 3 张且覆盖 3 个年份。 |
| `A.final-review` | BLOCKED | 0 | Prerequisites have not passed: A.full-render (BLOCKED) |
| `A.full-content-review` | BLOCKED | 0 | Human approval required for this input hash |
| `A.full-preview` | PASSED | 1 |  |
| `A.full-preview-render` | BLOCKED | 0 | 现有渲染器支持 S07–S15、A01–C03 或 H04，尚无完整画面预演入口。 |
| `A.full-render` | BLOCKED | 0 | 全片目标规格渲染与装配入口尚未实现。需检查全片内容、正式档案照片、画面与最终批准。Prerequisites have not passed: A.full-preview-render (BLOCKED), A.album-render (BLOCKED), B.representative-review (BLOCKED), A.full-content-review (BLOCKED) |
| `A.production-check` | PASSED | 1 |  |
| `A.production-docs` | PASSED | 1 |  |
| `B.component-keyframes` | PASSED | 1 |  |
| `B.representative-render` | BLOCKED | 0 | Human approval required for this input hash |
| `B.representative-review` | BLOCKED | 0 | Prerequisites have not passed: B.representative-render (BLOCKED) |

日志、产物摘要和历史状态可在同一状态目录下按任务 ID 与输入摘要查阅。

另有 0 份历史记录。
