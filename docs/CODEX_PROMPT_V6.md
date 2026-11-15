# Codex 执行 Prompt：创业板指 V6 导演叙事增强版

你正在继续迭代一个真实数据驱动的创业板指动态可视化工程。当前仓库基线是 V5。请完整阅读以下文件后再修改代码：

1. `docs/V6_ENGINEERING_CONTRACT.md`
2. `config/v6_storyboard_draft.json`
3. `config/events_v6_draft.json`
4. `config/style_v6_draft.json`
5. `assets/reference/approved_visual_reference.png`
6. `assets/reference/earth_body_reference.png`

## 核心任务

从 V5 新建 V6，不覆盖 V5。制作约 22 秒、720×1280、30fps、无音乐的导演样片：

- 真实实心 OHLC 蜡烛；
- 单一 `playhead_index`联动日期、K线、事件、时间轴、镜头和状态轨；
- 2012—2015 事件密度增强；
- 一根活动阶段状态轨，按阶段在回撤/上涨/高点后回撤之间切换；
- 地球、时间轴、事件卡与 K 线的美术质量明显优于 V5；
- 2015 高点前有充分减速与信息铺垫，高点后保持近景展示真实回撤。

## 开工顺序

1. 运行 V5 测试与关键帧渲染，确认基线可运行；
2. 复制 `src/chinext_v5`为 `src/chinext_v6`，创建独立 V6 配置与 `render_v6.py`；
3. 先完成数据模型、camera shots、单状态轨和事件类型；
4. 写测试并通过；
5. 再做 K线、事件、地球和时间轴美术；
6. 先渲染关键帧总览，逐项检查后再渲染全视频；
7. 输出诊断 JSON、实现说明和 changelog。

## 绝对禁止

- 不得把 V6 降级为固定仪表盘；
- 不得让事件、状态条或时间轴独立按秒播放而脱离 `playhead_index`；
- 不得保留两根同时实时变化的完整进度条；
- 不得用重金属、浮雕、大片金框、短剧封面式标题或 PPT 卡片矩阵；
- 不得单独拉伸某根 K 线；
- 不得把未核验的 `2015.06 场外配资清理`默认启用；
- 不得写因果判断或买卖建议；
- 不得修改真实行情数字以增强视觉冲击。

## 关键实现要求

### A. 单活动状态轨

在模型层计算：

- `drawdown_pre_low`
- `rise_from_low`
- `drawdown_from_high`

任意帧只能有一个 `active_stage_mode`。完成阶段缩成小型 milestone，不保留第二根完整实时轴。

### B. Camera Shots

把纯数值 camera keyframes 升级为语义化 shots，并支持：

- `follow_window`
- `lookahead_locked`
- `critical_anchor`

事件展示时纵轴不得明显呼吸；关键点位近景必须看清实体和影线。

### C. 信息密度

2013—2015 至少呈现：

- 2013—2015 移动互联网 / 并购潮阶段背景；
- 2013.07.24 华谊兄弟并购手游公司；
- 2013 年创业板指 +82.73%；
- 2014.01.08 IPO 重启；
- 2015.04.13 一人多户放开；
- 2015.04.24 单周新开 A 股账户 413.03 万户；
- 2015.06.03 3982.25 阶段高点；
- 2015.06.19 高点后回撤约 -16.76%。

除有意留白外，不允许超过 1.5 秒只有 K 线平移而没有镜头、事件、阶段背景、年度数据或状态变化。

### D. 事件美术

主事件使用：

- 半透明深色玻璃底；
- 极轻暖金发丝边，只画局部边；
- 红色日期胶囊；
- 白色无衬线文字；
- 8–12 px 位移 + 淡入 + 细线绘制；
- 短促事件连接线，不能像趋势线。

辅助事件不使用完整卡片。

### E. 地球与时间轴

从 `earth_body_reference.png`生成：主体、大气层、城市灯光 bloom、红光反射。节点命中时地球表面要有轻微红色波纹。时间轴只显示 2012、2013、2014、2015，避免未来年份干扰本样片。

### F. K线美术

- 图表层使用 2× supersampling；
- 实体和影线清晰；
- 普通蜡烛不持续发光；
- 当前和关键蜡烛可轻微 bloom；
- 不画图表外框；
- 网格向边缘渐隐；
- 背景星点减量。

## 必须运行的验收

```bash
pytest -q
python render_v6.py --keyframes
python render_v6.py --video --keyframes
ffprobe output/chinext_v6_narrative_enhanced.mp4
```

输出：

- `output/chinext_v6_narrative_enhanced.mp4`
- `output/review_contact.jpg`
- `output/keyframes/*.png`
- `output/shot_diagnostics.json`
- `output/event_diagnostics.json`
- `README_V6.md`
- `CHANGELOG_V6.md`
- `docs/V6_IMPLEMENTATION_NOTES.md`

完成后，请报告：

1. 改动文件；
2. 测试结果；
3. 视频元数据；
4. 关键镜头如何实现；
5. 尚未达到最终发布级的限制；
6. 不要声称已发布，不要执行任何外部平台写操作。
