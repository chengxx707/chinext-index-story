# WF-02 · 2015 V1.0.1 Codex 接收与执行回执

**主体预览已完成，缺 1 个照片镜头。** 167 秒原时序全部保留。素材和内容审核入场由本版本驱动，视觉仍为候选。

[下载 167 秒 MP4](final/preview_2015_v1.0.1_photo_missing.mp4) · [观看记录](final/visual_review.md) · [目标帧 1](final/keyframe_contact_01.jpg) · [目标帧 2](final/keyframe_contact_02.jpg) · [目标帧 3](final/keyframe_contact_03.jpg)

## 输入与产物

- 实际读取 `editorial/gpt-2015` 提交 [`c313edfa7959`](https://github.com/chengxx707/chinext-index-story/commit/c313edfa7959dfc6e9c56badfd3f662ae7fe01b4)。完整 V1.0.1 目录 29 文件与该提交逐文件一致。DATA-INGEST-002 的 37 个来源 ID 与声明摘要全部对应。 [接收记录](intake_receipt.json) · [导入的候选](../../editorial/2015/releases/v1.0.1/README.md)
- 候选内容校验 34/34。带导演能力校验时唯一未通过的项目是 `historical_photo_scene`，退出码 1。 [内容校验](content_validation.json) · [带能力核对](final/content_renderer_validation.json) · [能力清单](final/renderer_capabilities.json)
- 5,010 帧的真实交易日收盘、28 个准确命中和 27 处市场行与相机投影接缝均已核对。单活动轨在第 960 帧切换，7 月反弹时退回，最终 −54.86%。 [时序与几何检查](final/clock_validation.json)
- 540×960、30 fps、静音 MP4 通过 5,010 帧完整解码及黑帧检测。39 张检查图为 1080×1920，另检查 67 个绘制样本的文字边界和重叠。 [媒体验证](final/media_validation.json) · [版式诊断](final/layout_diagnostics.json) · [关键帧目录](final/keyframes/)
- 浏览器真实连续播放 0–167 秒，5,010 帧，0 掉帧。分时截图和实际解码图用于复看。 [观看记录](final/visual_review.md) · [播放日志](final/playback_observation.json)
- 165 项原工程和工作流测试通过；预览适配层另有上述现版本连续时钟和实图检查。 [回归日志](regression_tests.log)

## 缺镜、工程范围和评审

`IMG-20150824-01` 原件未进入本运行环境。第 3,630–3,779 帧（02:01–02:06）保留 8 月 24 日近景、真实收盘和回撤轨，省略照片与图注。正式照片剪接和原件可用性仍待验证。 [照片收件回执](photo_source_receipt.json)

这版可用于集中看主体节奏。重点留意 00:32 的快速推近、长政策阅读段、照片缺镜和手机署名行。正式 427 秒主表另作采用映射。冻结行情、原始素材、正式主表和本地未提交工作保留。

## 实际运行命令

```bash
python3 editorial/2015/releases/v1.0.1/validate_candidate.py --repo-root . --output output/wf-02-2015-gpt-v1.0.1/content_validation.json
.venv/bin/python tools/render_editorial_preview.py --keyframes --video --output output/wf-02-2015-gpt-v1.0.1/final --workers 4
python3 editorial/2015/releases/v1.0.1/validate_candidate.py --repo-root . --renderer-capabilities output/wf-02-2015-gpt-v1.0.1/final/renderer_capabilities.json --output output/wf-02-2015-gpt-v1.0.1/final/content_renderer_validation.json
.venv/bin/python -m pytest -q
```

退出码依次为 0、0、1（仅照片能力缺失）、0。 [编码日志](final/render.log) · [执行清单与产物 SHA-256](delivery_manifest.json)
