# WF-02 2015 V1.0.1 回执独立审计

审计对象：`31de236cdbaeac8ec39391794ff79b0f2ab1dc88`  
输入候选：`c313edfa7959dfc6e9c56badfd3f662ae7fe01b4`  
日期：2026-11-22（北京时间）  
范围：只读核对远端 Git 树、回执、校验 JSON、日志和诊断。未重新编码视频，未重跑 165 项测试，未以程序播放结果替代完整人工观看。画面审看由主任务另行进行。

## 结论

这是一份真实推进到连续主体预览的交付。输入版本没有漂移，冻结数据、事件注册表和正式主表未改；媒体完整性和程序实时播放有相应记录。当前应归类为“167 秒低分辨率连续预览，照片镜未完成，等待实际视觉评审”，不能称为正式成片、全部渲染能力通过、已达到参考视频质量或已获用户视觉批准。

## 证据矩阵

| 项目 | 独立核对/交付证据 | 可成立的结论 | 边界 |
| --- | --- | --- | --- |
| 候选输入 | 独立获取两个提交的未截断递归 Git 树；`editorial/2015/releases/v1.0.1/` 两侧均 29 个 blob，路径和 blob SHA 逐个相同 | 完整接收指定 V1.0.1 内容，未改写候选 | Git blob 相等证明字节一致，不证明事实主张正确 |
| 保护输入 | 两提交中 `data/cyb_daily.csv`、`config/event_registry.json`、`config/production/film_master_v1.json` blob 各自相同 | 本次交付未改动这三项冻结输入 | 不等于全部旧生产代码未改，本轮确有新适配器 |
| 内容校验 | `content_validation.json` 34 执行、0 失败；manifest SHA 为 `1be7273db7a0c2be9159a9933af6c857a087691bb3951a21f1883c3f1b19d4a4` | 内容包结构、声明口径、引用与数值一致性检查通过 | `raw_originals_checked=false`；只对本环境可用的 3 个文件或阅读记录做字节核验；不是重新独立核验所有外部原件 |
| 渲染能力 | `content_renderer_validation.json` 35 执行、1 失败；15 项必需能力中缺 `historical_photo_scene`；`ready_for_candidate_import=false` | 14 项被适配器声明为已实现/复用，照片能力未闭合；整体带能力校验确实失败 | 声明和自动几何检查不是视觉质量验收；需结合实际媒体和代码 |
| 时钟/轨道 | `clock_validation.json` 5010 帧、28 镜、27 接缝、换轨帧 960；July7=-40.93766%，July23=-25.47053%，最终 1797.56 / -54.86069% | 有连续市场映射和单轨反弹回退证据；不是末尾一次灌满条 | 位置/投影接续不能单独证明速度舒适或节奏好 |
| 编码媒体 | `media_validation.json`：540×960、30/1、167.000s、5010 帧、H.264、无音轨、全解码通过、无黑场区间；MP4 SHA `876ebe10519d8ba321cfa9f01edebd5b8588a39e8133448dd24277c3395afccf` | 已交付完整低分辨率静音连续预览 | 主任务仍应独立取得实际文件核对哈希/观看；不能用 39 张 1080×1920 静帧称连续视频也是 1080×1920 |
| 实时播放 | `playback_observation.json`：headless Chromium、1×、未 seek、played [0,167]、ended=true、5010 frames、0 dropped、35 screenshots、wall 167.89s | 浏览器实际播放到末尾，程序报告无掉帧 | `visual_review.md` 明确没有共享桌面全程人工审片。0 掉帧不证明摄像机运动与叙事节奏质量 |
| 文字布局 | `layout_diagnostics.json` 67 个 1080×1920 采样帧，无出界/文字互相重叠 | 这些采样的几何边界检查通过 | 不是全 5010 帧的遮挡检查，也不是手机可读性验收；来源字形 bbox 高 16–18px，HUD 日期 16px，在 390px 宽缩放时约 5.8–6.5px/5.8px |
| 回归测试 | `regression_tests.log` 明确 165 passed in 37.53s | 日志支持所报回归通过数量 | 本次审计未重跑；测试通过不代替视觉审看 |
| 照片缺口 | `photo_source_receipt.json`：MISSING_ORIGINALS_IN_RUNTIME；目标 JPEG 68047B、940×625、SHA `e9d18208a1e60e402af95d132c6e3a5cd5d313ecc1a00d08142e1898669a555e`；原 URL 返回 403，研究 ZIP 不含 JPEG | 是 Codex 运行环境未拿到指定字节，不是研究端尚未找到照片，也不是照片被审计否决 | GPT 端有字节时应解决交付，不应重开照片搜索；图像 manifest 的 rights_status=NOT_PROVIDED 与内部预览能力缺口分别记录 |
| 缺镜处理 | GPT2015-21，frames [3630,3780)，保留 150 帧，延续 Aug24 图表/2152.61/单回撤轨，省略照片和图注 | 没有虚构照片或擅改 167 秒时长，替代处理写明 | 这 5 秒仍不等于原导演照片镜完成 |

## 低运动区间：应升级为整段节奏评审的事实线索

从 `freeze_check.log` 重新相加得到：21 个已结束检测区间，共约 78.3000 秒；最后另有从 163.166667 秒持续到片尾的 3.833333 秒。合计约 **82.1333 秒，占 167 秒的 49.18%**。

这只能称为“按该检测器阈值识别的低运动区间”，不应称“49% 画面错误卡死”，也不能反过来用“都是阅读段”免除节奏审看。它提示：
- 应观察整段观看体验，而不只修 00:32 的一秒推近。
- 02:01–02:06 的缺照片段、02:12–02:24 连续政策阅读段是已知集中停留点。
- 信息阅读、交易日冻结与画面完全静止是不同概念；数据冻结可保留，镜头或分层信息呈现仍应有经过设计的动态。
- 这一审计不建议直接按检测时长删镜或改 167 秒；应先实际观察，再确定共享动效层和重点段修正。

## 需要维护的报告口径

1. “39 个事件已审计、56 条来源记录”仍然正确；不能因 Codex 未拿到原件退回为 GPT 尚未审计。
2. 当前版本：内容 34/34；带渲染能力 34/35；媒体/程序播放通过；用户视觉批准未发生。
3. 摄像机连续、读字清楚、信息节奏有效和达到视觉参考是四个不同判断，不能互相替代。
4. 自动编码、自动播放和截图复看已经执行；全文没有足够证据证明对纳斯达克原片作了本轮动态对照。其自述“原纳斯达克参考视频当前未重新取得”准确，需在最终审计中保留。

## 可追溯入口

- [交付 README](https://github.com/chengxx707/chinext-index-story/blob/31de236cdbaeac8ec39391794ff79b0f2ab1dc88/review-downloads/wf-02-2015-gpt-v1.0.1/README.md)
- [接收回执](https://github.com/chengxx707/chinext-index-story/blob/31de236cdbaeac8ec39391794ff79b0f2ab1dc88/review-downloads/wf-02-2015-gpt-v1.0.1/intake_receipt.json)
- [照片字节缺口](https://github.com/chengxx707/chinext-index-story/blob/31de236cdbaeac8ec39391794ff79b0f2ab1dc88/review-downloads/wf-02-2015-gpt-v1.0.1/photo_source_receipt.json)
- [带能力内容校验](https://github.com/chengxx707/chinext-index-story/blob/31de236cdbaeac8ec39391794ff79b0f2ab1dc88/review-downloads/wf-02-2015-gpt-v1.0.1/final/content_renderer_validation.json)
- [时钟与几何证据](https://github.com/chengxx707/chinext-index-story/blob/31de236cdbaeac8ec39391794ff79b0f2ab1dc88/review-downloads/wf-02-2015-gpt-v1.0.1/final/clock_validation.json)
- [媒体验证](https://github.com/chengxx707/chinext-index-story/blob/31de236cdbaeac8ec39391794ff79b0f2ab1dc88/review-downloads/wf-02-2015-gpt-v1.0.1/final/media_validation.json)
- [程序播放记录](https://github.com/chengxx707/chinext-index-story/blob/31de236cdbaeac8ec39391794ff79b0f2ab1dc88/review-downloads/wf-02-2015-gpt-v1.0.1/final/playback_observation.json)
- [逐帧布局抽样](https://github.com/chengxx707/chinext-index-story/blob/31de236cdbaeac8ec39391794ff79b0f2ab1dc88/review-downloads/wf-02-2015-gpt-v1.0.1/final/layout_diagnostics.json)
- [低运动检测](https://github.com/chengxx707/chinext-index-story/blob/31de236cdbaeac8ec39391794ff79b0f2ab1dc88/review-downloads/wf-02-2015-gpt-v1.0.1/final/freeze_check.log)
- [原交付复看记录及限制](https://github.com/chengxx707/chinext-index-story/blob/31de236cdbaeac8ec39391794ff79b0f2ab1dc88/review-downloads/wf-02-2015-gpt-v1.0.1/final/visual_review.md)

