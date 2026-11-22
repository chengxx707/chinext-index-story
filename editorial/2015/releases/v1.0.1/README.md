# 2015 编辑候选 V1.0.1

**方案 A 已确认并落实；本版本可交给 Codex 导入与连续预演。**

覆盖2015年4月1日至9月15日，167秒、28镜、5010帧、30fps、静音竖屏。它是内容候选，不代表已渲染或已获视觉批准。

- [本版改动和报告](REVIEW_REPORT.md)
- [完整画面文字稿](period_screen_copy.md)
- [导演分镜](director_storyboard.md)
- [Codex 执行任务](CODEX_HANDOFF.md)
- [39条审计原记录](event_review.json)
- [28镜方案A采用决定](rigor_application.json)及[已确认标准](rigor_policy.json)
- [56条来源登记](source_registry.json)及[本轮补充阅读记录](research/evidence/rigor_a_reading_records.json)

机器输入必须一起使用：period_storyboard.json、period_production.json、director_timeline.json。manifest.json绑定本版本全部文件。原始资料包仍按archive_manifest.json的名称与摘要定位，本目录没有重复上传第三方原图或网页全文。

## 接收校验

~~~bash
python3 editorial/2015/releases/v1.0.1/validate_candidate.py --repo-root . --output output/wf-02-2015-gpt-v1.0.1/content_validation.json
~~~

若已解压原件ZIP，可加 --originals-dir 指向包内包含 00_原始网页归档 等目录的实际路径。缺少本地原件时会记录未复查外部字节，不虚报完成。

新版完整自包含，无需把补丁叠在旧候选上。V1.0.0保留供追溯；V1.0.1发布后同样不原地修改。后续产物写入独立output目录。

生成时间：2026-11-22 15:18（北京时间）。
