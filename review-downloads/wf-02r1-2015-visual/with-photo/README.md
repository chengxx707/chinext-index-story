# WF-02R1 · 2015 V1.0.1 补图审阅回执

已接收 `IMG-20150824-01` 并完成含图的 167 秒连续预览。28 镜、1080×1920、30 fps、5,010 帧、无音轨。工程验证通过，用户集中观看与正式采用待审。

## GPT 审阅入口

按用户确认，后续生成的审阅视频、审阅包与回执直接提交 GitHub 审阅分支。

- [下载本轮技术证据 ZIP](../chinext-2015-wf-02r1-photo-audit.zip)，含接收、解析配置、时钟、媒体、能力、播放、关键帧文字诊断和回归报告。
- [下载上一轮缺图版审阅包](https://raw.githubusercontent.com/chengxx707/chinext-index-story/8e05a36cf540514ce39f4cbe449a08629a7fb4f7/review-downloads/wf-02r1-2015-visual/chinext-2015-wf-02r1-preview-review.zip)，含可下载的 167 秒 MP4、43 张关键帧和对比画面。此包的 02:01–02:06 仍是实 K 图。
- [下载含图版完整预览 MP4](../chinext-2015-v1.0.1-wf-02r1-with-photo.mp4)，用户已授权上传本次审阅视频。影片为 167 秒、1080×1920、30 fps。
- [视频上传记录](video_publication.json)将本次分发文件与原渲染回执的 SHA-256 绑定。

## 实际执行

- 交接提交 `99170907de537d35a2abea2406505b988780ef47`。内容提交 `c313edfa7959dfc6e9c56badfd3f662ae7fe01b4`。29 个 V1.0.1 文件未变，冻结行情、主表和事件注册表 SHA 再次核对。
- ZIP 校验 71,414 字节、CRC 和 SHA-256。包内 JPEG 校验 68,047 字节、940×625、格式及 SHA-256，与冻结照片清单一致。[照片接收记录](photo_intake.json)
- 02:01–02:06 为镜头窗口。照片按等比适配。f3651 原始图经等比缩放的像素与 1080 关键帧照片区域一致，视频解码后也核对该区域。保留人物、水印、右侧日 K、2015.08.24、收盘 2,152.61、地球与单轨。
- 从 02:01.50 淡入、02:01.70 全亮，退出发生在镜末。入镜与出镜沿用相机和 8 月 24 日收盘，后续按原时钟揭示 8 月 25 日日 K。
- 390 像素宽对照确认主标题「昆明证券交易大厅」完整一行，日期留在上方，署名为「中新社发 刘冉阳 摄」。按原时序显示 4.1 秒全亮画面。
- 实际编码通过全帧解码和黑场检查。35 项内容与能力复核全部通过，照片场景通过。127 个版式样本、5,010 帧时钟、27 处接缝通过。171 项回归通过。
- Chromium 在 390 像素宽视口实播 0–167 秒，记录 0 掉帧和 35 张分时截图。照片入退另从实际 MP4 解码 8 个时点并截取 02:00–02:08 连续片段。自动实播与关键帧目视检查在本轮完成，用户视觉验收仍待评审。

## 复跑

先核对本地 JPEG 的 SHA-256 与 [照片接收记录](photo_intake.json) 一致。已安装工程依赖和 FFmpeg 时，在仓库根目录运行下列命令。输出目录使用新的忽略路径。

```bash
python3 tools/render_editorial_preview.py \
  --revision config/editorial/wf-02r1-2015.json \
  --photo /path/to/IMG-20150824-01.jpg \
  --width 1080 --workers 4 --video --keyframes \
  --output output/wf-02r1-photo-check
python3 editorial/2015/releases/v1.0.1/validate_candidate.py \
  --repo-root . \
  --renderer-capabilities output/wf-02r1-photo-check/renderer_capabilities.json \
  --output output/wf-02r1-photo-check/capability_content_crosscheck.json
```

实际媒体 SHA-256 为 `442069455645250164466acd335d7f958aa2113804fd492de648bd0eb3630017`。[运行回执](execution_receipt.json)
