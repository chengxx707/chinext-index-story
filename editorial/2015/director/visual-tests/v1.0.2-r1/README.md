# DIRECTOR-V1.0.2-VISUAL-R1 · 代表块视觉与节奏修订

**R1 审阅片已交付，待用户审片。** 在 `b0d71e895a7d756fa2ebbb7d8f3f471d581f1ccb` 的 48 cue 已编码候选上修订。新候选 7,320 帧、244 秒。三段审阅片合计 122 秒。GitHub 提供两段新片和完整 ZIP，B08 原片也收入 ZIP，保留其原摘要。 [下载审阅包](director-v1.0.2-visual-r1-review.zip) · [候选配置](candidate.json) · [总 Manifest](manifest.json) · [执行回执](execution_receipt.json)

## 交付与实测

| 范围 | 全局帧与时长 | 交付状态 |
| --- | --- | --- |
| B01–B02 | `[0,540)`，18 秒 | 重新编码。 [1080 MP4](B01-B02/target.mp4) · [手机 MP4](B01-B02/phone-390.mp4) · [联系表](B01-B02/keyframe-contact.jpg) · [Manifest](B01-B02/manifest.json) |
| B08–B10 | `[2280,3600)`，44 秒 | 两种尺寸、联系表和诊断按上轮 SHA-256 复用。 [1080 MP4](https://github.com/chengxx707/chinext-index-story/blob/b0d71e895a7d756fa2ebbb7d8f3f471d581f1ccb/editorial/2015/director/visual-tests/v1.0.2/B08-B10/target.mp4) · [手机 MP4](https://github.com/chengxx707/chinext-index-story/blob/b0d71e895a7d756fa2ebbb7d8f3f471d581f1ccb/editorial/2015/director/visual-tests/v1.0.2/B08-B10/phone-390.mp4) · [联系表](https://github.com/chengxx707/chinext-index-story/blob/b0d71e895a7d756fa2ebbb7d8f3f471d581f1ccb/editorial/2015/director/visual-tests/v1.0.2/B08-B10/keyframe-contact.jpg) · [复用证据](reused_b08.json) |
| B16–B18 | `[5520,7320)`，60 秒 | 重新编码。B17 从 22 秒增至 26 秒，B18 平移 120 帧。 [1080 MP4](B16-B18/target.mp4) · [手机 MP4](B16-B18/phone-390.mp4) · [联系表](B16-B18/keyframe-contact.jpg) · [Manifest](B16-B18/manifest.json) |
| B13 | f4440、f4517 | 重新生成专项静帧。 [1080 静帧](B13-PMI/B13-f4440.png) · [390 px 静帧](B13-PMI/phone-390.png) · [前后对照](comparisons/pmi-context.jpg) |

## 实际画面修改和读感

- **B01。** 旧版 f6 已把日期、主点位和右侧重复点位一起亮出，随后固定持镜。R1 在 f0–48 用 1.6 秒缓动将可见跨度从 72 根收至 50 根，市场钟一直是 2015/6/3。当日日期先出现，f48 开始亮出 3,982.25 并伴随一次局部强调，f54 全亮，右侧 HUD 去掉重复点位。实际解码帧可见视窗递进，f240 的四月返回仍清楚。主要数字全亮 6.2 秒，余下持镜节奏待审。 [实际手机前后对照](comparisons/intro-and-cut.jpg)
- **B08–B10。** 6/27 公告和 6/28 实施各自可读，行情停在 6/26 收盘；7/3 收盘冻结承接三项周末措施，旧事件降亮。复市按 7/6、7/7、7/23 真实交易日接回，7/7 到 7/23 的 +26.19% 仍与真实回撤轨回缩同步。新旧配置在该段完全一致，两版共用绘制抽查 30 个 1080 RGB 帧逐像素相同。沿用原政策构图并避免为装饰加入来源不明的机构建筑。 [共用绘制复核](b08_shared_pixel_check.json) · [既有逐段审片](https://github.com/chengxx707/chinext-index-story/blob/b0d71e895a7d756fa2ebbb7d8f3f471d581f1ccb/editorial/2015/director/visual-tests/v1.0.2/B08-B10/review.md)
- **B17。** 五个普通日涨跌的全亮窗口从 1.50–1.63 秒调整至 **1.93–2.30 秒**，9/25 与 9/28 各 2.30 秒。增加的是落到真实收盘后的保留时间。所有真实交易日和最后的 11/25 修复结算均保留。手机解码图中 9/25 与 9/28 主数字读完后，视线能转向下一条 T2 信息。
- **ETF。** 9/25 收盘后再进场，f6193–6336 全亮 **4.8 秒**。保留 9/7–22 观察窗、12.37 亿份到 18.07 亿份、+46.08%、9/25 报道和「据中国证券报援引深交所数据」。390 px 下实测来源字框约 12.29 px，旧版约 10.84 px。观察区间和报道字段加大并保持分栏。六帧淡出后接回 9/28 真实行情。 [日线与 ETF 同节点前后对照](comparisons/daily-and-etf.jpg)
- **成交额。** 9/28 收盘读数先出现，f6448–6561 独立显示沪深两市全日 4,044 亿元，稳定 **3.8 秒**。放大亿元单位和同期出处，手机解码可分别读到总额、口径及来源。六帧淡出后接回 9/29，逐帧检查两项 T2 互不重叠，事实、来源和级别保持一致。 [成交额、退场与结算同节点前后对照](comparisons/turnover-and-repair.jpg)
- **B13。** 面板补「当日回顾」，同屏保留 09:30 A 股开盘、09:43:10 财新网页刊发、PMI 初值 47.1。完整 8/21 日 K 和 2,341.95 收盘与网页时间分区，首发时间仍未知，未生成分钟走势。 [专项静帧诊断](B13-PMI/diagnostics.json)

## 观看、验证和素材

- 工程检查执行了 48 cue Schema、7,320 帧时钟、66 项命中帧及作用域变化检查。R1 独立逐帧检查验证 B01 单次缓推和点位分阶段、B17 两项 T2 的全亮区间、退场、交易日、独立焦点、字幕位置与单一活动轨。V1.0.1 的 29 个文件、冻结 OHLC、事件注册表、正式 427 秒主表及批准资产的摘要在开工与编码后匹配。 [时钟](clock_revalidation.json) · [实帧检查](r1_motion_audit.json) · [输入稳定性](render_input_binding.json)
- 两段新片的四个 MP4 均通过尺寸、30 fps、静音、全帧解码和黑场测试。播放器在 390 px、1× 完整播放两段新版和两个同尺寸旧版对照。新版 B01–B02／B16–B18 记录 0／0 个掉帧。B08 沿用同一二进制的既有完整实播记录，0 个掉帧。另用实际编码前后帧检查布局与转场。用户审美验收仍待确认。 [独立技术报告](independent_visual_qa.json) · [对照帧与片内时码索引](comparisons/index.json)
- 两张最新参考图原件未取得。附件只有既有文本、研究包和历史照片交接 ZIP。使用仓库批准海报作为回看基准并复用深色背景、夜景地球、真实蜡烛和单轨。未找到语境相符且用途已核清的 2015 年中国机构建筑图，本轮未加入建筑图层。参考图匹配待原件补验。 [参考识别和输入摘要](intake.json)

## 待用户判断

1. B01 单次缓推后的 6.2 秒点位持镜是否够利落。若仍偏长，可缩短前导或末段持镜，并保留明确的四月回返。
2. B17 的 26 秒是否适合手机连续看，尤其是两项 T2 的出处和随后的行情恢复节奏。

建议先确认这两处，再批准按 244 秒候选制作整段连续预览。届时仍需检查代表片段之间的实际观看衔接。两张原图到手后可补核美术与背景信息密度。

回执附带候选、兼容时钟段、读感对照和本轮工具。工具入口沿用本项目 Pillow/FFmpeg 与既有行情渲染器，只重新编码 B01–B02 和 B16–B18。 [工具入口](tools/README.md)
