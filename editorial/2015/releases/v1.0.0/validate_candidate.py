#!/usr/bin/env python3
"""Read-only content contract validation. This does not render or approve a film."""
from pathlib import Path
import argparse, csv, hashlib, json, math, sys
from datetime import date, datetime, timezone


def validate(package, root, originals=None, renderer_capabilities=None):
    sys.path.insert(0, str(root))
    from orchestration.workflows.schema import validate_schema, _check
    checks=[]
    def check(name, ok, detail):
        checks.append({'id':name,'passed':bool(ok),'detail':detail})
    def load(name):return json.loads((package/name).read_text(encoding='utf-8'))
    def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
    board=load('period_storyboard.json');production=load('period_production.json');director=load('director_timeline.json')
    review=load('event_review.json');sources=load('source_registry.json');photos=load('photo_manifest.json')
    raw=root/'data/cyb_daily.csv';master=root/'config/production/film_master_v1.json'
    rows=list(csv.DictReader(raw.open(encoding='utf-8-sig',newline='')))
    days=[r['date'] for r in rows];data={r['date']:{f:float(r[f]) for f in ['open','high','low','close']} for r in rows}
    indices={d:i for i,d in enumerate(days)}
    check('frozen_market_sha',sha(raw)==board['provenance']['market_sha256']=='d832c794deaabaeda7b3803e5e93da471d6075f5d807b65714b9ab243d477205',{'rows':len(rows),'start':days[0],'end':days[-1]})
    check('frozen_master_sha',sha(master)==board['provenance']['frozen_master_sha256']=='8fac8d3612116570635c3d27df553d0d2274a06f0f4708624d85967c4d392706','正式主表输入未变')
    check('market_rows',len(days)==len(set(days)) and days==sorted(days) and all(all(math.isfinite(x) and x>0 for x in r.values()) and r['low']<=min(r['open'],r['close'])<=max(r['open'],r['close'])<=r['high'] for r in data.values()),'日期唯一递增、正有限价格和OHLC关系')
    records=review['events']+review.get('supplemental_events',[]);event_ids={e['event_id'] for e in records};source_ids={s['source_id'] for s in sources['sources']}
    check('event_counts_and_ids',len(review['events'])==39 and len(event_ids)==len(records)==40,{'external':39,'supplemental':len(records)-39})
    check('source_ids_unique',len(source_ids)==len(sources['sources']),len(source_ids))
    missing=[];evidence_mismatches=[]
    for e in records:
        for x in e.get('source_evidence',[]):
            if x.get('source_id') not in source_ids:missing.append([e['event_id'],x.get('source_id')])
            p=x.get('path');digest=x.get('sha256')
            if p and p.startswith('research/') and digest:
                if not (package/p).is_file() or sha(package/p)!=digest:evidence_mismatches.append(p)
    check('all_review_source_references',not missing,missing or '原39条、补充1条的所有证据ID可解析')
    check('portable_evidence_files',not evidence_mismatches,evidence_mismatches or '随包阅读记录存在且SHA匹配')
    check('embedded_registry',board['source_registry']==sources['sources'],'分镜内嵌来源与独立注册表一致')
    for name,digest in [('event_review.json','event_review_sha256'),('source_registry.json','source_registry_sha256')]:
        check('provenance_'+digest,sha(package/name)==board['provenance'][digest],name)
    check('provenance_same',board['provenance']==production['provenance']==director['source_provenance'],'三个候选文件绑定相同输入')
    try:
        validate_schema('source_registry',sources)
        for name,key in [('story_beat','story_beats'),('shot','shots'),('market_period','market_periods')]:
            for obj in board[key]:validate_schema(name,obj)
        for obj in production['production_units']:validate_schema('production_unit',obj)
        _check(load('director_timeline.schema.json'),director,'director_timeline')
        check('schemas',True,'现有四类记录Schema、来源Schema及导演伴随Schema通过')
    except Exception as ex:check('schemas',False,str(ex))
    units=production['production_units'];shots={x['shot_id']:x for x in board['shots']};beats={x['beat_id']:x for x in board['story_beats']};cues={x['shot_id']:x for x in director['cues']}
    check('record_set_sizes',len(units)==len(shots)==len(beats)==len(cues)==28,'28镜、28节拍、28生产单元、28导演cue')
    cursor=0;previous=None;frame_errors=[];date_errors=[];value_errors=[];link_errors=[];clock_errors=[];reading_errors=[];all_frame_dates=[];capabilities=set()
    for u in units:
        sid=u['shot_id'];c=cues[sid];s=shots[sid];b=beats[u['beat_id']];n=u['duration_frames']
        if u['start_frame']!=cursor or u['end_frame_exclusive']-cursor!=n or c['start_frame']!=cursor or c['end_frame_exclusive']!=cursor+n:frame_errors.append(sid)
        keys=c['market_clock']['keyframes'];key_dates=[k['date'] for k in keys];offsets=[k['frame_offset'] for k in keys]
        if offsets[0]!=0 or offsets[-1]!=n-1 or any(a>=z for a,z in zip(offsets,offsets[1:])):frame_errors.append(sid+':keys')
        if any(d not in data for d in key_dates) or key_dates!=sorted(key_dates) or key_dates[0]!=u['start_market_date'] or key_dates[-1]!=u['end_market_date']:date_errors.append(sid)
        if previous is not None and key_dates[0]!=previous:date_errors.append(sid+':join')
        previous=key_dates[-1]
        for f in range(n):
            for a,z in zip(keys,keys[1:]):
                if a['frame_offset']<=f<=z['frame_offset']:
                    t=(f-a['frame_offset'])/(z['frame_offset']-a['frame_offset']);ix=indices[a['date']]+t*(indices[z['date']]-indices[a['date']]);day=days[math.floor(ix+1e-9)];all_frame_dates.append(day);break
        anchor=c['primary_anchor'];hit=anchor['hit_frame']-cursor
        if anchor['date']!=b['market_anchor'] or data[anchor['date']][anchor['field']]!=anchor['value'] or b['market_close']!=data[b['market_anchor']]['close']:value_errors.append(sid)
        if all_frame_dates[cursor+hit]!=anchor['date']:date_errors.append(sid+':hit')
        for endpoint in c['link_geometry']['close_endpoints']:
            if endpoint['value']!=data[endpoint['date']]['close']:value_errors.append(sid+':close_endpoint')
        if set(b['source_ids'])-source_ids or set(b['event_ids'])-event_ids or set(u['source_ids'])-source_ids:link_errors.append(sid)
        ec=c.get('event_clock')
        if ec and ec.get('market_freeze_after_hit') and any(d!=anchor['date'] for d in all_frame_dates[cursor+hit:cursor+n]):clock_errors.append(sid)
        if ec and ec.get('role')=='weekend_announcement':
            prior=max(d for d in days if d<ec['date'])
            if prior!=anchor['date'] or date.fromisoformat(ec['date']).weekday()<5:clock_errors.append(sid+':weekend')
        if ec and not ec.get('persistent_date_label_required'):clock_errors.append(sid+':label')
        if s['reading_duration']!=round((c['text_cue']['out_frame_exclusive']-c['text_cue']['full_alpha_from_frame'])/30,2) or c['text_cue']['out_frame_exclusive']>cursor+n:reading_errors.append(sid)
        capabilities.update(c['requires_renderer_capabilities']);cursor+=n
    check('frame_intervals',not frame_errors and cursor==5010==director['frame_count']==production['planned_frame_count'],frame_errors or '0..5009连续，无重叠、无空档')
    check('market_clock_and_hits',not date_errors and len(all_frame_dates)==5010 and all_frame_dates==sorted(all_frame_dates),date_errors or '逐帧映射真实交易行、跨镜接续、命中日正确')
    check('exact_prices_and_endpoints',not value_errors,value_errors or '主锚点、收盘与真实双端点匹配CSV')
    check('beat_source_event_links',not link_errors,link_errors or '全部节拍/单元来源与事件可回查')
    check('event_clock_freezes',not clock_errors,clock_errors or '盘后、周末市场冻结，独立事件日期标签必显')
    check('reading_time_arithmetic',not reading_errors,reading_errors or '计划稳定阅读秒数与整数帧一致；尚未作视觉可读性验收')
    gaps=[c['link_geometry']['gap'] for c in director['cues'] if c['link_geometry']['gap']]
    check('three_full_gaps',[g['current_date'] for g in gaps]==['2015-08-21','2015-08-24','2015-08-25'] and all(data[g['current_date']]['high']<data[g['previous_date']]['low'] and g['current_high']==data[g['current_date']]['high'] and g['previous_low']==data[g['previous_date']]['low'] for g in gaps),'不是8月24—26日三天都形成完整缺口')
    check('gap_domain_stays_constant',len({tuple(c['camera']['target_y_domain']) for c in director['cues'] if c['link_geometry']['gap']})==1,'三个缺口使用相同纵轴范围')
    metrics=load('market_metrics.json');errors=[]
    for key,start,end in [('high_to_low_close_pct','2015-06-03','2015-09-15'),('june12_to_june26_close_pct','2015-06-12','2015-06-26'),('july7_to_july23_close_pct','2015-07-07','2015-07-23'),('august24_26_return_pct','2015-08-21','2015-08-26')]:
        actual=100*(data[end]['close']/data[start]['close']-1)
        if abs(actual-metrics[key])>1e-6:errors.append(key)
    check('interval_returns',not errors,errors or '−25.10%、+26.19%、−19.30%、−54.86%按声明起止日复算')
    rail=director['rail'];v1=100*(data['2015-07-07']['close']/3982.25-1);v2=100*(data['2015-07-23']['close']/3982.25-1)
    check('reversible_single_rail',rail['drawdown']['base_close']==3982.25 and rail['rise']['base_close']==data['2012-12-03']['close'] and v2>v1 and abs(v2)<abs(v1) and rail['drawdown']['start_frame']==units[4]['end_frame_exclusive'],{'july7':round(v1,2),'july23':round(v2,2),'mode_switch_frame':rail['drawdown']['start_frame']})
    asset_ids={a['asset_id'] for a in photos['assets']};photo_refs=[c['photo_asset_id'] for c in director['cues'] if c['photo_asset_id']]
    check('photo_asset_links',set(photo_refs)<=asset_ids and photos['selected_asset_id'] in photo_refs and all(a.get('source_id') in source_ids for a in photos['assets']),{'selected':photo_refs,'assets':len(asset_ids)})
    check('no_unresolved_or_excluded_screen_claims',all(e['review_status'] not in ['UNRESOLVED','EXCLUDE'] for e in records if e.get('selected_in_candidate')),'部分支持的两融数据仅作明确署名和回顾标签的窄范围采用')
    hashes=[];verified=0
    for s in sources['sources']:
        p=root/s['original_path'] if s.get('original_path') else originals/s['archive_member'] if originals and s.get('archive_member') else None
        if p is not None and s.get('sha256'):
            if not p.is_file() or sha(p)!=s['sha256']:hashes.append(s['source_id'])
            else:verified+=1
    if originals:
        for a in photos['assets']:
            p=originals/a['path']
            if not p.is_file() or sha(p)!=a['sha256']:hashes.append(a['asset_id'])
            else:verified+=1
    check('available_source_bytes',not hashes,{'verified_files_or_records':verified,'mismatches':hashes,'raw_originals_checked':originals is not None})
    manifest=package/'manifest.json';manifest_errors=[]
    if manifest.is_file():
        for x in json.loads(manifest.read_text())['artifacts']:
            p=package/x['path']
            if not p.is_file() or sha(p)!=x['sha256'] or p.stat().st_size!=x['size_bytes']:manifest_errors.append(x['path'])
        check('manifest_artifact_hashes',not manifest_errors,manifest_errors or '版本包产物摘要匹配')
    renderer_checked=renderer_capabilities is not None
    if renderer_checked:
        supplied=json.loads(renderer_capabilities.read_text());supplied=set(supplied if isinstance(supplied,list) else supplied['capabilities'])
        missing_caps=sorted(capabilities-supplied);check('renderer_capabilities',not missing_caps,missing_caps or '声明支持所有必需能力；仍须实际渲染检查')
    errors=[c for c in checks if not c['passed']]
    return {'schema_version':1,'package_version':'1.0.0','generated_at':datetime.now(timezone.utc).isoformat(),'passed':not errors,'checks':checks,'summary':{'executed_checks':len(checks),'failed':len(errors),'shots':len(shots),'frames':cursor,'duration_seconds':cursor/30,'events_reviewed':len(review['events']),'supplemental_events':len(review.get('supplemental_events',[])),'source_records':len(source_ids)},'errors':errors,'not_executed':['视频编码与实际连续播放','版式与遮挡检查','与视觉参考质量比较','用户视觉验收'],'renderer_capabilities_checked':renderer_checked,'required_renderer_capabilities':sorted(capabilities),'raw_originals_checked':originals is not None,'manifest_checked':manifest.is_file(),'ready_for_candidate_import':not errors,'ready_for_final_production':False}


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--repo-root',type=Path);ap.add_argument('--originals-dir',type=Path);ap.add_argument('--renderer-capabilities',type=Path);ap.add_argument('--output',type=Path);args=ap.parse_args()
    package=Path(__file__).resolve().parent;root=(args.repo_root or package.parents[3]).resolve()
    try:result=validate(package,root,args.originals_dir,args.renderer_capabilities)
    except Exception as ex:result={'passed':False,'error':f'{type(ex).__name__}: {ex}'}
    text=json.dumps(result,ensure_ascii=False,indent=2)+'\n'
    if args.output:args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(text)
    print(text);sys.exit(0 if result['passed'] else 1)
