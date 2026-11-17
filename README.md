# 创业板指数视频工程

以用户提供的纳斯达克100视频为动态参考、批准海报为静态美术基准。全片生产主表初排7分07秒，尚未完成或验收完整成片。用户要求修订V1主体的衔接与遮挡，并明确拒绝39秒文献结尾；本轮已修正连续镜头、透明字幕及真实高低端点联动。真实档案照片尚未取得，相册制作被明确阻断。

## 当前两份制作文件

- [工程实施路线图 V1](docs/production/工程实施路线图_V1.md)
- [全片生产主表与完整屏幕文字稿 V1](docs/production/全片生产主表与完整屏幕文字稿_V1.md)

机器主表：[config/production/film_master_v1.json](config/production/film_master_v1.json)。两份文档分别说明怎么做、具体做什么；新版编排由该主表驱动。更多资料见[文档导航](docs/README.md)。

当前状态见[实施进度](docs/production/实施进度.md)。[对标复盘与修正说明 V2](docs/production/对标复盘与修正说明_V2.md)记录了实际参考视频、V1接缝与遮挡证据；[真实照片获取状态 V2](docs/production/真实照片获取状态_V2.md)记录了原报道线索和网络阻碍。V1视频只作历史比较，技术检查通过不代表用户观看通过。

已导出[V2主体97秒样片](docs/production/reviews/2015_representative_v2.mp4)：S07—S15、1080×1920、30fps、无音轨。114项测试、实际媒体与接缝检查通过；阅读与运动体感待实际观看评定。全文主表及427秒初排未改变。

## 仓库结构

```text
docs/production/          路线图、全片主表与屏幕文字等正式交付
docs/research/            事实候选、事件与素材审计
docs/source/              用户原始脚本、研究文件
config/production/        唯一生产主表与编排输入
config/                   既有样片配置、事件注册表
data/                     冻结OHLC、提取正文与研究台账
assets/                   视觉素材、参考图、文献原件
src/chinext_v6/           当前行情、绘制与生产模块
src/chinext_v5/           保留的旧基线
tools/                    编译、预览、渲染、检查入口
tests/                    数据、时间、版式与编排回归
output/                   本地生成视频/关键帧/缓存，不提交Git
```

## 环境与入口

Python 3.12、FFmpeg/libx264、Noto Sans CJK 字体。当前云环境已有这些系统依赖；Python版本写在`requirements.lock`。从仓库根目录运行：

```bash
bash tools/setup.sh
source .venv/bin/activate
make production-check
make components
make representative
make photo-status
```

新版代表渲染默认输出1080×1920、30fps无声片，支持`--width 720`内部预览；低分辨率预览不能作为目标规格通过。产物默认在忽略的`output/`中；精选交付副本经检查后放入`docs/production/reviews/`。使用现有隔离checkout，无需另建Git worktree，进程不必常驻。

旧42秒样片入口`render_v6.py`保留作历史对照。旧15秒字墙/市值结尾只通过`make legacy-ending`明确调用，不作为当前结尾候选。

## 事实与生产规则

先读`AGENTS.md`、[制作规范](docs/PRODUCTION_SPEC.md)和[事件审计](docs/EVENT_AUDIT.md)。三份项目技能位于`.agents/skills/`：`video-production`、`data-time-consistency`、`render-review-repair`。它们参考了GitHub官方通用方法并适配本项目，没有引入React/Remotion运行时。

`data/cyb_daily.csv`是唯一OHLC源，固定截至2026-11-10。当前收盘与日期绑定同一真实交易日；动画不会合成一个假收盘。事件资格来自`config/event_registry.json`，B/C默认关闭。用户材料的A级核验与本轮重新在线核验分开记录。

`config/full_storyboard.json`由`python tools/build_storyboard.py`从保留的V0.9生成：60个连续场景含尾注，共303秒。它保留作旧稿对照；当前新增内容使用`config/production/film_master_v1.json`，不再按旧秒数挤入。主表存在不代表全片渲染器已经实现。

## 检查与审阅

新版生产输入与组件入口：

```bash
make production-check
make production-docs
make components
make representative
make photo-status
make album
```

`production-check`验证主表文字导出是否一致，并编译全片帧时间表，核对来源、引语、冻结行情和显式历史跳转。`production-docs`从同一主表更新人读文稿；不要分别手改两份文字。`components`当前输出八类非相册内容组件的1080静帧与32秒无声动效；它是组件工程预览，不代表完整代表片或整片已通过审阅。

`representative`生成S07—S15的97秒主体修正版；V2使用跨节点连续投影、透明字幕和S09/S15真实双端点路径联动。当前集成渲染入口限制在代表范围，整片其他阶段尚未扩展。

`photo-status`诊断真实相册图片的入库与核验状态。`album`和`ending`都先执行照片ready检查，未满足条件则失败；当前合格历史照片为0张，不能生成正式相册。三个上传ZIP已复查，包含HTML、PDF、数据、地球和参考海报等，没有历史现场照片。已存在原报道和图注线索，但运行环境访问仍被出站白名单403拦截；网络白名单草稿已保存，尚未应用到运行环境。缺图时不再输出无照片的文献／文字结尾。

新增场景缓存按当前节点及其实际数据、来源正文、代码、素材、字体和相机参数建立摘要。复用时重新检查视频文件摘要与实际规格，装配后再验收总片；被修改或损坏的缓存不会作为成功结果继续使用。

```bash
python -m pytest -q
python tools/validate_project.py --config config/v6_sample.json --events config/events_v6.json --output output/v6_review/validation.json --layout
```

验证失败退出非零，JSON保留检查范围、问题和`manual_review: pending`。实际媒体检查包括帧数、时长、尺寸、帧率、无音轨、完整解码与异常黑帧。渲染清单记录输入/生产代码/资产哈希，不能用陈旧视频冒充当前实现。关键帧和逐帧诊断供检查同步、排版及镜头边界。

自动检查通过不代表连续运动、阅读节奏或相册已经通过用户审阅。V1的实际观看反馈已成为V2修正输入；V2已重新导出，规格、完整解码、黑场、排版和八个接缝检查有独立记录。代表片段通过后才扩展完整成片。详见`docs/QUALITY_GATES.md`和当前审阅记录。

## 美术素材

`assets/reference/approved_visual_reference.png`保留用户批准母版；不能把整张母版作为假图表背景。日K和全部数值由代码绘制。`assets/earth_cinematic.png`为本轮以用户参考生成的透明东亚夜景装饰资产，行情与节点均另行渲染。旧`earth_body.png`保留用于基线比较。

## 连续行情与新版2015章节

用户已认可V5运动与题签。当前新增入口为`make chapter-2015`（130秒章节）和`make chapter-2015-layout`；唯一章节输入是`config/production/chapter_2015_v3.json`。实现位于`src/chinext_v6/continuous.py`，不依赖output中的试验脚本。章节先集中审阅，再合并全片；结尾相册暂缓。旧97秒与全片427秒均保留历史状态。

章节按600帧切片缓存；缓存命中复核视频摘要和规格，装配后完整解码。所有切片使用全局帧号，双worker使用spawn。随包原文与UTF-8正文位于20261117来源目录，章节启动时校验摘要和直接引语。
