# 2015 编辑候选 V1.0.0

**交付单位：一段完整的内容与导演候选。** 覆盖2015年4月1日至9月15日，167秒、28镜、5010帧，静音竖屏。

先读 [REVIEW_REPORT.md](REVIEW_REPORT.md)，看内容读 [period_screen_copy.md](period_screen_copy.md)，开始执行读 [CODEX_HANDOFF.md](CODEX_HANDOFF.md)。

## 文件分工

|文件|用途|
|---|---|
|`event_review.json`|外部39条事件的独立复核，以及另列的7月8日补充事件|
|`source_registry.json`|54条带范围说明的来源记录；保留原始归档与新网页阅读记录的差别|
|`archive_manifest.json`|两份输入ZIP摘要、117个包内文件、37条外部来源与33个不同原件的映射|
|`research/`|三组详细复核、数值复算、来源别名和随包的网页阅读记录|
|`narrative.md`|六阶段叙事、选用逻辑与全片时长影响|
|`period_screen_copy.md`|逐镜完整主文案、署名、事件时间和计划阅读时长|
|`director_storyboard.md`|画面层次、连续镜头与关键联动说明|
|`period_storyboard.json`|兼容已有记录Schema的阶段、节拍和镜头|
|`period_production.json`|整数帧生产单元与同版本镜头记录|
|`director_timeline.json`|每镜市场日期关键帧、事件时钟、命中帧、相机和真实几何|
|`director_timeline.schema.json`|导演伴随配置的结构契约|
|`market_metrics.json`|冻结CSV复算的价位、百分比、缺口和口径|
|`photo_manifest.json`|9张已查看图片的来源、尺寸、摘要和精度；选中昆明图01|
|`validate_candidate.py`|只读校验命令；不启动渲染、不修改主表|
|`validation_report.json`|本轮实际执行的内容/配置校验；与视觉验收严格分开|
|`manifest.json`|版本、输入摘要、产物摘要与真实完成状态|

## 证据定位

- `source_registry.original_path`：仓库根目录相对路径。
- `archive_member` 或以 `00_原始网页归档/`、`05_8月24日营业部现场照片/` 开头的审核路径：相对于 `2015-drawdown_originals_pack.zip` 内 `2015-drawdown_原始资料包/`。原包字节不在这个公开候选目录重复上传。
- `research/evidence/`：随本版本提供的精选网页阅读记录；其摘要不是原网页HTML的摘要。
- 原包内外部自报状态、来源时间字段保留为输入记录；实际选用遵循 `event_review.json` 的修正与 `director_timeline.json` 的时间角色。

## 复跑

在仓库根目录执行：

```bash
python3 editorial/2015/releases/v1.0.0/validate_candidate.py \
  --repo-root . \
  --output output/wf-02-2015-gpt-v1/content_validation.json
```

已在本机收到并解压原始资料包时，可追加 `--originals-dir`，指向包含 `00_原始网页归档/` 等子目录的实际目录。未提供此参数时，报告明确记为未复查外部原件字节；不会冒充已经取得这些文件。

如提供 `--renderer-capabilities path/to/capabilities.json`，文件应为能力名称数组，或含 `capabilities` 数组的对象。脚本会检查15项必需能力是否齐全；能力声明本身不能代替渲染证据。

发布后不原地改本目录。后续内容修改建立新版本，Codex执行产物写入独立 `output/` 目录。
