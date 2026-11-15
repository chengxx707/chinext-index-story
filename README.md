# 创业板指数视频工程

以用户提供的纳斯达克100视频为动态参考、批准海报为静态美术基准。主体视觉已认可；当前按新版生产主表进入场景编排与内容组件开发。V1初排7分07秒，尚未实现或验收完整成片。V5、原始脚本与研究文档保留；V6为独立的模型与绘制实现。

## 当前两份制作文件

- [工程实施路线图 V1](docs/production/工程实施路线图_V1.md)
- [全片生产主表与完整屏幕文字稿 V1](docs/production/全片生产主表与完整屏幕文字稿_V1.md)

机器主表：[config/production/film_master_v1.json](config/production/film_master_v1.json)。两份文档分别说明怎么做、具体做什么；新版编排由该主表驱动。更多资料见[文档导航](docs/README.md)。

已实现的组件及少量精选媒体见[制作预览与检查](docs/production/reviews/README.md)。

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
python render_v6.py --keyframes --output-dir output/v6_review
python render_v6.py --video --workers 2 --output-dir output/v6_review
python tools/validate_project.py --config config/v6_sample.json --events config/events_v6.json --output output/v6_review/validation.json --video output/v6_review/chinext_v6_sample.mp4 --layout
python tools/render_ending.py --keyframes --video --output-dir output/ending_review
```

前两个渲染命令输出既有1080×1920、30fps、42秒主体样片；旧结尾入口保留15秒组件样片供历史对照，该字墙/市值结尾已被时代相册方案取代。`--width 720 --output-dir output/v6_preview`可生成低成本内部预览，不能当作目标规格通过。产物默认在忽略的`output/`中；无需另建Git worktree。进程不必常驻。

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
```

`production-check`验证主表文字导出是否一致，并编译全片帧时间表，核对来源、引语、冻结行情和显式历史跳转。`production-docs`从同一主表更新人读文稿；不要分别手改两份文字。`components`输出九类内容组件的1080静帧与36秒无声动效，属于组件工程预览，不代表完整代表片或整片已通过审阅。

新增场景缓存按当前节点及其实际数据、来源正文、代码、素材、字体和相机参数建立摘要。复用时重新检查视频文件摘要与实际规格，装配后再验收总片；被修改或损坏的缓存不会作为成功结果继续使用。

```bash
python -m pytest -q
python tools/validate_project.py --config config/v6_sample.json --events config/events_v6.json --output output/v6_review/validation.json --layout
```

验证失败退出非零，JSON保留检查范围、问题和`manual_review: pending`。实际媒体检查包括帧数、时长、尺寸、帧率、无音轨、完整解码与异常黑帧。渲染清单记录输入/生产代码/资产哈希，不能用陈旧视频冒充当前实现。关键帧和逐帧诊断供检查同步、排版及镜头边界。

自动检查通过不表示美术已达到海报基准。应检查真实导出、连续帧和手机尺寸，并在代表片段集中审阅后才扩展完整电影。详见`docs/QUALITY_GATES.md`和当前审阅记录。

## 美术素材

`assets/reference/approved_visual_reference.png`保留用户批准母版；不能把整张母版作为假图表背景。日K和全部数值由代码绘制。`assets/earth_cinematic.png`为本轮以用户参考生成的透明东亚夜景装饰资产，行情与节点均另行渲染。旧`earth_body.png`保留用于基线比较。
