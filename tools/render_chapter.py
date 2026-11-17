#!/usr/bin/env python3
"""Render the source-checked 2015 chapter with resumable continuous chunks."""
from pathlib import Path
import argparse,hashlib,json,subprocess,sys,multiprocessing
from concurrent.futures import ProcessPoolExecutor
from PIL import Image,ImageDraw
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'src'))
from chinext_v6.continuous import Chapter,ContinuousRenderer,digest
from chinext_v6.renderer import encode_frames
_scene=None

def worker_init(root,config,width):
    global _scene
    _scene=ContinuousRenderer(root,config,width)

def worker(n):
    im,diag=_scene.render(n);diag.pop('text_boxes',None)
    return im.tobytes(),diag

def probe(path):
    return json.loads(subprocess.run(['ffprobe','-v','error','-count_frames','-show_entries','stream=codec_type,width,height,r_frame_rate,nb_read_frames:format=duration','-of','json',str(path)],capture_output=True,text=True,check=True).stdout)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--config',type=Path,default=ROOT/'config/production/chapter_2015_v3.json');p.add_argument('--output-dir',type=Path,default=ROOT/'output/chapter_2015_v3');p.add_argument('--width',type=int,default=1080);p.add_argument('--workers',type=int,default=2);p.add_argument('--keyframes',action='store_true');p.add_argument('--video',action='store_true');args=p.parse_args()
    if not(args.keyframes or args.video):p.error('Select --keyframes and/or --video')
    if args.width<360 or args.width%2 or round(args.width*16/9)%2:p.error('Even portrait dimensions required')
    out=args.output_dir.resolve();out.mkdir(parents=True,exist_ok=True);chapter=Chapter(ROOT,args.config)
    inputs=dict(chapter.hashes)
    for path in list((ROOT/'src/chinext_v6').glob('*.py'))+[Path(__file__),ROOT/'assets/earth_body.png',ROOT/'assets/earth_cinematic.png',Path('/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc'),Path('/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc'),Path('/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-Oblique.ttf')]:inputs[str(path.resolve())]=digest(path)
    snapshot=out/'chapter_snapshot.json';snapshot.write_text(json.dumps(chapter.data,ensure_ascii=False,indent=2)+'\n')
    signature=hashlib.sha256(json.dumps({'inputs':inputs,'width':args.width},sort_keys=True).encode()).hexdigest()
    if args.keyframes:
        scene=ContinuousRenderer(ROOT,snapshot,args.width);diags=[];paths=[]
        for event in chapter.events:
            for tag,t in [('entry',event['start']+.7),('mid',(event['start']+event['end'])/2),('exit',event['end']-.5)]:
                n=min(chapter.frame_count-1,round(t*chapter.fps));im,d=scene.render(n);file=out/'keyframes'/f'{event["id"]}_{tag}.png';file.parent.mkdir(exist_ok=True);im.save(file);paths.append(file);diags.append(d)
        sheet=Image.new('RGB',(1080,660*((len(paths)+2)//3)),(2,7,12));pen=ImageDraw.Draw(sheet)
        for i,file in enumerate(paths):
            x,y=(i%3)*360,(i//3)*660;sheet.paste(Image.open(file).resize((360,640)),(x,y));pen.text((x+5,y+643),file.stem,fill='white')
        sheet.save(out/'contact.jpg',quality=90);(out/'layout_checks.json').write_text(json.dumps(diags,ensure_ascii=False))
        issues=[{'frame':d['frame'],'event':d['event'],'bounds':d['out_of_bounds'],'overlaps':d['text_overlaps']} for d in diags if d['out_of_bounds'] or d['text_overlaps']]
        print(json.dumps({'keyframes':len(paths),'issues':issues},ensure_ascii=False),flush=True)
        if issues:raise RuntimeError('Keyframe layout defects; fix before encoding')
    if args.video:
        cache=out/'cache';cache.mkdir(exist_ok=True);records=[];segments=[];hits=0
        with ProcessPoolExecutor(max_workers=args.workers,mp_context=multiprocessing.get_context('spawn'),initializer=worker_init,initargs=(str(ROOT),str(snapshot),args.width)) as pool:
            for start in range(0,chapter.frame_count,600):
                end=min(chapter.frame_count,start+600);ident=hashlib.sha256(f'{signature}:{start}:{end}'.encode()).hexdigest()[:18];file=cache/f'{start:05d}_{ident}.mp4';meta=file.with_suffix('.json');use=False
                if file.is_file() and meta.is_file():
                    d=json.loads(meta.read_text());use=d.get('signature')==signature and d.get('video_sha256')==digest(file) and len(d.get('frames',[]))==end-start
                    if use:
                        v=probe(file)['streams'][0];use=(v['width'],v['height'],v['r_frame_rate'],int(v['nb_read_frames']))==(args.width,round(args.width*16/9),'30/1',end-start)
                if use:hits+=1;segment_records=d['frames'];print('CACHE',start,end,flush=True)
                else:
                    segment_records=[]
                    def frames():
                        for a in range(start,end,30):
                            for rgb,diag in pool.map(worker,range(a,min(a+30,end)),chunksize=3):
                                if diag['out_of_bounds'] or diag['text_overlaps']:raise RuntimeError(f'Layout failure at frame {diag["frame"]}: {diag}')
                                segment_records.append(diag);yield rgb
                            print('FRAMES',min(a+30,end),'/',chapter.frame_count,flush=True)
                    encode_frames(frames(),args.width,round(args.width*16/9),chapter.fps,file,preset='fast',crf=18)
                    meta.write_text(json.dumps({'signature':signature,'video_sha256':digest(file),'frames':segment_records},ensure_ascii=False))
                records.extend(segment_records);segments.append(file)
        concat=out/'concat.txt';concat.write_text(''.join("file '"+str(file)+"'\n" for file in segments));target=out/'chapter_2015_v3.mp4'
        subprocess.run(['ffmpeg','-v','error','-y','-f','concat','-safe','0','-i',str(concat),'-c','copy','-movflags','+faststart',str(target)],check=True)
        media=probe(target);v=media['streams'][0]
        checks={'frame_count':int(v['nb_read_frames'])==chapter.frame_count,'dimensions':(v['width'],v['height'])==(args.width,round(args.width*16/9)),'fps':v['r_frame_rate']=='30/1','silent':len(media['streams'])==1,'duration':abs(float(media['format']['duration'])-chapter.duration)<.04,'market_clock_strictly_increases':all(b['playhead']>a['playhead'] for a,b in zip(records,records[1:])),'no_text_layout_errors':all(not r['out_of_bounds'] and not r['text_overlaps'] for r in records),'all_hud_closes_exact':all(r['close']==float(chapter.market.close[chapter.market.index_for_date(r['date'])]) for r in records),'all_inputs_stable':all(digest(path)==sha for path,sha in inputs.items())}
        with (out/'decode.log').open('w') as log:subprocess.run(['ffmpeg','-hide_banner','-v','info','-xerror','-i',str(target),'-vf','blackdetect=d=0.1:pix_th=0.08','-an','-f','null','-'],stdout=log,stderr=log,check=True)
        checks['full_decode']=True;checks['no_black_intervals']='black_start:' not in (out/'decode.log').read_text()
        (out/'frame_checks.json').write_text(json.dumps(records,ensure_ascii=False));manifest={'passed':all(checks.values()),'checks':checks,'signature':signature,'input_sha256':inputs,'video_sha256':digest(target),'media':media,'cache_hits':hits,'cache_misses':len(segments)-hits,'human_review':'pending','source_scope':'local supplied archives checked; no new online verification'}
        (out/'render_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2));print(json.dumps({'passed':manifest['passed'],'checks':checks,'video':str(target),'cache_hits':hits},ensure_ascii=False),flush=True)
        if not manifest['passed']:raise RuntimeError('Chapter verification failed')
    chapter.assert_stable()
if __name__=='__main__':main()
