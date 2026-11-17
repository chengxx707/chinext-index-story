#!/usr/bin/env python3
"""Export chapter screen copy from its sole JSON input."""
from pathlib import Path
import argparse,json,hashlib
ROOT=Path(__file__).resolve().parents[1]
def main():
    p=argparse.ArgumentParser();p.add_argument('--check',action='store_true');args=p.parse_args();source=ROOT/'config/production/chapter_2015_v3.json';d=json.loads(source.read_text())
    lines=['# 2015完整章节屏幕文字稿 V3','',f"唯一输入：`{source.relative_to(ROOT)}`。初排{d['duration_seconds']}秒，30fps、1080×1920、无声。",'',d['scope'],'','章节候选，待用户集中观看；不是完整影片或相册结尾。文字修改应先改JSON，再导出本文。','',f"输入SHA-256：`{hashlib.sha256(source.read_bytes()).hexdigest()}`。",'','| 片内秒数 | 历史日期／范围 | 屏幕主文字 | 来源／次级文字 |','|---|---|---|---|']
    for e in d['events']:lines.append(f"| {e['start']:g}—{e['end']:g} | {e['label']} | {'<br>'.join(e['lines'])} | {e['source']} |")
    lines+=['','## 测量与时间口径','','两组端点保留真实日期横坐标，使用同一价格投影接垂直括号。行情继续，不将历史测量终点改成当前行情日期。','','- 2012-12-03至2015-06-03：+570.80%、+3388.59点、约2年6个月。','- 2015-06-03至2015-09-15：−54.86%、−2184.69点、104个自然日。','- 8月21／24／25日是完整向下缺口，26日不是；8月24—26日累计以21日收盘为基准。','- 周末公告日期与行情观察日、盘后公布与次日实施分开。','- 金光为真实收盘点之间的装饰连线，不是盘中重建；HUD不显示插值收盘。','','## 来源','','本地随包原件核读，不宣称本轮重新联网验证。来源文献及提取正文均受章节输入中的摘要保护。','']
    for id,s in d['sources'].items():lines.append(f"- `{id}`：{s['title']}；`{s['document']}`。")
    text='\n'.join(lines)+'\n';dest=ROOT/'docs/production/2015章节屏幕文字稿_V3.md'
    if args.check:
        if not dest.exists() or dest.read_text()!=text:raise SystemExit('Chapter screen copy is stale')
        print('CHAPTER_DOCS_CURRENT')
    else:dest.write_text(text);print(dest)
if __name__=='__main__':main()
