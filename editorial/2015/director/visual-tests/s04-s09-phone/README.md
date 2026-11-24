# S04–S09｜20 秒手机快剪样片

按 `9bfc303` 的已确认构图制作。琥珀点阵在后，真实红绿日 K 在前，红色时间轨随交易日推进。暖金强调 **593.66** 与 **3,982.25**。 [播放样片](phone-390.mp4) · [原速呈现帧](timed-review.jpg) · [已确认构图](../s04-s09-reference-r1/README.md)

## 1× 观察

| 片内时间 | 原速观察 |
| --- | --- |
| **00:07.000–00:07.800** | 「IPO 重启」从左侧接管。右侧华谊手游并购余标低亮再留 0.8 秒，能看出上一件事退到背景，主焦点移到发行恢复。 |
| **00:11.000–00:17.067** | 一人多户、新增 A 股账户、乐视网按 11、13、15 秒先后入场，主标题间隔约两秒。早先 IPO 题签到新开户题签时仍是低亮历史背景。行情持续向前。开户 **413.03 万户**全亮 1.77 秒，乐视主读数回看 **5 月 13 日收盘总市值超过 1,500 亿元**。 |
| **00:17.067–00:20.000** | 事件题签先清场，留约 0.93 秒给 K 线和行情日期。18 秒整命中 6 月 3 日，**3,982.25**、对应日 K 和底轨一起定住，读数全亮两秒。 |

**导演最需要判断的接点为 00:15.000。** 从 **413.03 万户**切到乐视 **超过 1,500 亿元**时，两次大数字间隔很短。建议保留当前速度形成加速感，重点听取开户观察区间和单位是否都有读完的时间。

## 复核与复跑

一遍 Chromium 390×694、1× 连续播放到尾，无暂停、拖动或掉帧。以上画面判断取自该次实播呈现帧。另行独立校验了 600 帧时间戳、完整解码、静音、冻结日线、605 个交易日覆盖，以及实际题签窗口和构图文字边界。 [播放记录](playback.json) · [独立验证](technical-validation.json) · [媒体 Manifest](manifest.json) · [逐帧记录](frames.json.gz)

以下命令从仓库根目录执行，依赖和镜头绘制器沿用项目。下载的地理轮廓经固定摘要校验，仅用于点阵地球。

```bash
review=editorial/2015/director/visual-tests/s04-s09-phone
out=output/director-s04-s09-phone
mkdir -p "$out/runtime"
git archive b0c339c src/chinext_v6 data/cyb_daily.csv assets/earth_body.png assets/earth_cinematic.png |
  tar -xf - -C "$out/runtime"
curl -fsSL https://raw.githubusercontent.com/nvkelso/natural-earth-vector/v5.1.2/geojson/ne_110m_land.geojson   -o "$out/ne_110m_land.geojson"
python3 "$review/tools/render_phone.py"   --runtime-root "$out/runtime" --land-file "$out/ne_110m_land.geojson" --output "$out/review"
python3 "$review/tools/verify_phone.py"
```
