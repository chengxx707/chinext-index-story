# 创业板指数 · 2015 年工作流审计入口

OPS-001.1、WF-01A 和 WF-01B 的本地审计快照。使用真实归档与冻结 OHLC 跑完 2015 年试点，输出 5 个阶段、22 个分镜和约 153 秒的候选编排。候选待人工审阅。

[下载完整 ZIP](chinext-wf-01-2015-review.zip) · [任务 DAG](../../output/wf-01-2015/task-dag.md) · [屏幕文字](../../output/wf-01-2015/candidate/period_screen_copy.md) · [验证报告](../../output/wf-01-2015-evidence/verification.md)

## 逐文件审计

| 范围 | 文件 |
| --- | --- |
| 源码与配置 | [调度器说明](../../orchestration/README.md) · [工作流说明](../../orchestration/workflows/README.md) · [任务注册表](../../orchestration/registry/production.json) · [测试源码](../../tests/orchestration/) |
| 研究与证据 | [事件核验](../../output/wf-01-2015/research/period_research.json) · [来源台账](../../output/wf-01-2015/research/source_registry.json) · [证据报告](../../output/wf-01-2015/research/evidence_report.md) · [研究 Manifest](../../output/wf-01-2015/research/research_manifest.json) |
| 补证 | [完整中文采集 Prompt](../../output/wf-01-2015/research/external_research_requests/research_request.md) · [结构化采集任务](../../output/wf-01-2015/research/external_research_requests/research_request.json) · [回交 Schema](../../output/wf-01-2015/research/external_research_requests/return.schema.json) |
| 内容候选 | [导演分镜](../../output/wf-01-2015/candidate/period_storyboard.json) · [屏幕文字](../../output/wf-01-2015/candidate/period_screen_copy.md) · [候选生产配置](../../output/wf-01-2015/candidate/period_production.json) · [故事审计](../../output/wf-01-2015/candidate/story_audit.md) |
| 全片编排 | [浏览器粗预演 HTML 源文件](../../output/wf-01-2015/preview/preview.html) · [时间表与占位说明](../../output/wf-01-2015/preview/preview_timing.json) |
| 调度证据 | [执行前 Dry Run](../../output/wf-01-2015-evidence/dry-run.json) · [实际执行](../../output/wf-01-2015-evidence/run.json) · [同输入复跑](../../output/wf-01-2015-evidence/repeat.json) · [任务状态记录](../../output/wf-01-2015-state/records/) |
| 测试 | [51 项工作流测试](../../output/wf-01-2015-evidence/workflow-tests.log) · [114 项原工程回归](../../output/wf-01-2015-evidence/legacy-tests.log) |

## 实际执行 Manifest

- [A.production-docs](../../output/wf-01-2015-state/attempts/A.production-docs/c80937f9563b4c73fd957d3fef8850c4be797f2e894844a8c34f6b1dfbc38133/1/manifest.json)
- [B.component-keyframes](../../output/wf-01-2015-state/attempts/B.component-keyframes/24b85f8e719a1af0c53e5e216f58a0ba9ec25614c0ab0fff903e31445f6c7261/1/manifest.json)
- [A.2015-research](../../output/wf-01-2015-state/attempts/A.2015-research/bc317aa06e8a89acba9dcf1d288f9cd196239101966b32d7823d0f37866139a3/1/manifest.json)
- [A.production-check](../../output/wf-01-2015-state/attempts/A.production-check/3c588db34086d23d90757e56738573d35bbd4ff554ae028622750f6bc0274790/1/manifest.json)
- [A.2015-story](../../output/wf-01-2015-state/attempts/A.2015-story/d1d496889fe9d1be2a93e85dc8c47c2fc11f672a39de97ff1d1c9e9482900128/1/manifest.json)
- [A.full-preview](../../output/wf-01-2015-state/attempts/A.full-preview/a22c76c66cac87939171c9f19c827aa44fcd82725fa7e828b9b16660fac7fdea/1/manifest.json)

6 项任务通过、9 项阻断、0 项失败。视频和正式主表采纳仍待各自门禁。本次审计提交保留当时的状态目录和验证日志。需要复跑时，使用新的状态目录，例如 `--state-dir output/wf-01-2015-audit-rerun`。HTML 文件可下载后用浏览器打开。

ZIP SHA-256 `f747b56a751a490d51d37cfe131c80bc59c18c6602fa372be29cd508a6828a8e`。
