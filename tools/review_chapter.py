#!/usr/bin/env python3
"""Review actual encoded chapter frames and cross-chunk motion evidence."""
from pathlib import Path
import sys,json,subprocess,hashlib
import numpy as np
from PIL import Image,ImageDraw
ROOT=Path(__file__).resolve().parents[1]

def main():
    out=Path(sys.argv[1]) if len(sys.argv)>1 else ROOT/'output/chapter_2015_v3';video=out/'chapter_2015_v3.mp4';manifest=json.loads((out/'render_manifest.json').read_text());config=json.loads((out/'chapter_snapshot.json').read_text());records=json.loads((out/'frame_checks.json').read_text())
    assert hashlib.sha256(video.read_bytes()).hexdigest()==manifest['video_sha256']
    actual=out/'actual_frames';actual.mkdir(exist_ok=True);paths=[]
    for e in config['events']:
        t=(e['start']+e['end'])/2;p=actual/(e['id']+'.jpg')
        subprocess.run(['ffmpeg','-v','error','-y','-ss',str(t),'-i',str(video),'-frames:v','1','-q:v','2',str(p)],check=True);paths.append(p)
    sheet=Image.new('RGB',(1080,500*((len(paths)+3)//4)),(2,7,12));d=ImageDraw.Draw(sheet)
    for i,p in enumerate(paths):
        x,y=(i%4)*270,(i//4)*500;sheet.paste(Image.open(p).resize((270,480)),(x,y));d.text((x+5,y+482),p.stem,fill='white')
    sheet.save(out/'actual_contact.jpg',quality=94)
    # Decode the entire encoded chart region, including all assembly boundaries.
    proc=subprocess.Popen(['ffmpeg','-v','error','-xerror','-i',str(video),'-vf','crop=1000:460:40:740,scale=300:138,format=gray','-f','rawvideo','pipe:1'],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    count=0;prior=None;differences=[];size=300*138
    while True:
        b=proc.stdout.read(size)
        if not b:break
        if len(b)!=size:raise RuntimeError('Incomplete decoded frame')
        a=np.frombuffer(b,dtype=np.uint8).astype(np.int16)
        if prior is not None:differences.append(float(np.mean(np.abs(a-prior))))
        prior=a;count+=1
    error=proc.stderr.read().decode();assert proc.wait()==0,error
    measurements={}
    for e in config['events']:
        if e.get('measurement'):
            visible=[r for r in records if r['event']==e['id'] and r['measurement_visible']];measurements[e['id']]={'visible_frames':len(visible),'visible_seconds':len(visible)/30,'first':visible[0]['t'] if visible else None,'last':visible[-1]['t'] if visible else None}
    seams=[]
    for n in range(600,len(records),600):
        a,b=records[n-1:n+1];seams.append({'frame':n,'time':n/30,'prior_date':a['date'],'next_date':b['date'],'market_delta':b['playhead']-a['playhead'],'encoded_chart_delta':differences[n-1]})
    speeds=[30*(b['playhead']-a['playhead']) for a,b in zip(records,records[1:])]
    result={'video_sha256':manifest['video_sha256'],'actual_decoded_frames':count,'adjacent_chart_pairs':len(differences),'identical_chart_pairs':sum(v==0 for v in differences),'min_chart_delta':min(differences),'median_chart_delta':float(np.median(differences)),'trading_days_per_second':[min(speeds),max(speeds)],'measurements':measurements,'seams':seams,'reference_scope':'Existing decoded sequences from actual NASDAQ reference at 39.5–43s and 97–104s. Original 235s recording absent in current workspace; no fresh full-reference playback or numerical quality rating claimed.','human_review':'pending'}
    assert hashlib.sha256(video.read_bytes()).hexdigest()==manifest['video_sha256'], 'Video changed during actual review'
    assert count==round(config['duration_seconds']*30)
    assert all(v['visible_seconds']>4 for v in measurements.values())
    assert all(s['market_delta']>0 for s in seams)
    (out/'actual_review.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps(result,ensure_ascii=False,indent=2))
    reference=Image.open(ROOT/'docs/production/reviews/reference_comparison_v2/reference_range_sequence.jpg');cw=reference.width//4;panel=reference.crop((cw,reference.height//2,cw*2,reference.height));canvas=Image.new('RGB',(810,540),(2,7,12));pen=ImageDraw.Draw(canvas)
    panel.thumbnail((270,500));canvas.paste(panel,((270-panel.width)//2,0))
    for j,name in enumerate(['high','low'],1):canvas.paste(Image.open(actual/(name+'.jpg')).resize((270,480)),(j*270,0))
    for x,label in [(0,'NASDAQ reference: decoded sequence'),(270,'2015 chapter: June high'),(540,'2015 chapter: September low')]:pen.text((x+3,510),label,fill='white')
    canvas.save(out/'reference_comparison.jpg',quality=94)
if __name__=='__main__':main()
