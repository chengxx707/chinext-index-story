# DIRECTOR-V1.0.2-REPRESENTATIVE-VISUAL-TEST · 三段代表块审片回执

三段已生成 1080×1920、30 fps、静音 MP4 和 390×694 手机 MP4。共 118 秒、3,540 个正片帧。独立技术检查通过，**待 GPT 与用户审片**。报告使用的是实际编码文件、解码画面和合成帧记录。 [下载完整审阅 ZIP](director-v1.0.2-representative-visual-review.zip) · [执行回执](execution_receipt.json) · [独立 QA](independent_visual_qa.json)

输入是最新编辑提交 `16955b82ca0a2fbe63b2b168e5545fd701014c38`，沿用编译回执 `5e211d52afe376ff393a050493c4a1e780e780d9` 与时钟和图层实现 `67a8cc6740c521675f71c6c733997e429681c3a2`。独立视觉候选含 48 个 cue，保留 7,200 帧全局时基和 B17 的 22 秒。冻结 OHLC、事件台账、正式 427 秒主表、V1.0.1 文件和批准视觉资产在编码前后摘要一致。 [独立候选](candidate.json) · [接收与输入摘要](intake.json) · [时钟复验](clock_revalidation.json)

| 代表块 | 全局帧与时长 | 媒体及结论 |
| --- | --- | --- |
| B01–B02 | `[0,540)`，18 秒 | 6/3 收盘 3,982.25 独立闪前。f240 明确硬切回 4/1 收盘 2,404.91，正序抵达 4/10 的 2,552.83。 [1080 MP4](B01-B02/target.mp4) · [手机版](B01-B02/phone-390.mp4) · [联系表](B01-B02/keyframe-contact.jpg) · [Manifest](B01-B02/manifest.json) · [逐段审片](B01-B02/review.md) |
| B08–B10 | `[2280,3600)`，44 秒 | 6/27 公告和 6/28 实施保持 6/26 收盘 2,920.70。七月三项周末措施在 7/3 收盘 2,605.28 接力，旧节点降亮。随后显示 7/6 复市和 7/7→7/23 收盘区间 +26.19%，同一回撤轨回缩。 [1080 MP4](B08-B10/target.mp4) · [手机版](B08-B10/phone-390.mp4) · [联系表](B08-B10/keyframe-contact.jpg) · [Manifest](B08-B10/manifest.json) · [逐段审片](B08-B10/review.md) |
| B16–B18 | `[5520,7200)`，56 秒 | 9/2 盘中低点与 9/15 阶段最低收盘分开，按交易日完成反弹、回落、T2 接力及 11/25 的 +61.19% 区间结算。 [1080 MP4](B16-B18/target.mp4) · [手机版](B16-B18/phone-390.mp4) · [联系表](B16-B18/keyframe-contact.jpg) · [Manifest](B16-B18/manifest.json) · [逐段审片](B16-B18/review.md) |

## B13 与 B17 专项

- **B13，f4440。** 09:30「A股开盘」与 09:43:10「财新网页刊发」同屏。PMI 初值 47.1 主读点独立于右侧 8/21 收盘 2,341.95。事件首发保留空值。两个时间点仅用于同日时间线，日 K 保持完整。 [1080 关键帧](B13-PMI/B13-f4440.png) · [390 px 对照](B13-PMI/phone-390.png) · [静帧诊断](B13-PMI/diagnostics.json)
- **ETF，f6145–6270 全亮 4.2 秒。** 9/25 收盘先稳定在 2,020.97。随后显示 9/7–22 观察窗、9/25 报道、12.37 亿份至 18.07 亿份、+46.08% 及出处。淡出为 `[6271,6277)`，随后显示 9/28 反弹。
- **沪深两市成交额，f6358–6459 全亮 3.4 秒。** 9/28 收盘 2,122.26 已先出现，当日全日口径 4,044 亿元独立入场。淡出为 `[6460,6466)`，随后推进到 9/29 回落。逐帧确认两项 T2 无同屏。 [实际手机 MP4 解码对照](B16-B18/b17-t2-phone-contact.jpg)

## 实际技术检查与视觉差异

- 六个视频均独立全帧解码通过，帧率、尺寸、帧数、静音和黑场检测均通过。逐帧核对 3,540 个源合成画面的行情、单一活动轨、焦点和字幕边界。23 个镜头接点中 22 处常规接点投影逐帧相接，f240 为声明的硬切。帧诊断保留其相机相邻差分供复查。 [技术报告](independent_visual_qa.json)
- Chromium 在 390 px 视口按 1× 播完三段。首轮并行播放依次记录 0、2、2 个掉帧，后两段另作单片复播，三段采纳的播放记录依次为 0、0、0 个掉帧。技术报告中的全帧解码与浏览器播放统计各自记录。ZIP 内含播放观察和实际解码关键帧。本轮内部目视检查用解码连续取样和手机画面。用户全程审片待进行。
- **已修复，B17。** 试帧中 +46.08% 接近右侧行情读数。横向移动后，在 f6145 与右侧文字框保留 23 个目标分辨率像素间距。最终手机转场图可复查。
- **待评审，B01。** f240 的语义和画面接力清楚。首个闪前窗口使用现有首段固定取景，开头的读数明显，是否在当前 8 秒钩子内加入独立短推仍需创作评审。当前片保留已编译的边界。
- **待评审，B17。** 两项 T2 已留出可用的独立阅读和退场空间。为保留 22 秒，普通日涨跌字样的全亮窗口约 1.50–1.63 秒。390 px 抽查主数字清晰，出处字框约 9.8–10.8 px。若审片需要更慢，优先给日 K 字样加约 2 秒，或从普通行情推进调剂预算。本轮保留已批准的三段帧区间。

## 运行与复查

将随包工具放在本仓库忽略的 `output/director-v1.0.2-visual-test/work/`。用 Git 导出上面的实施提交到同级 `runtime/`，包含 `src/chinext_v6`、`tools/render_editorial_preview.py` 和旧版 `director_timeline.schema.json`。从编辑输入提交导出 `HANDOFF_TO_CODEX.md`、裁定、`EVENT_CLOCK_REGISTER_V1.0.2.json`、`compiled/v1.0.2/` 到同级 `inputs/`，保留原仓库路径。使用项目依赖、`jsonschema`、FFmpeg 和 Chromium，以如下入口复跑。工具只接受三段视频和已批准的 PMI 静帧。 [总清单](manifest.json)

```bash
review=output/director-v1.0.2-visual-test
python3 -B "$review/work/prepare_visual.py" --runtime-root "$review/runtime"   --inputs "$review/inputs" --output "$review/result"
python3 -B "$review/work/render_visual.py" --runtime-root "$review/runtime"   --candidate "$review/result/candidate.json" --legacy-dir "$review/result/legacy"   --out "$review/result" --all-blocks --pmi-stills --workers 4
python3 -B "$review/work/make_review_media.py" --result "$review/result"
python3 -B "$review/work/qa_visual.py" --result "$review/result"   --out "$review/result/independent_visual_qa.json"
```
