"""Continuous chapter engine: independent market, camera and editorial clocks.

OHLC and labelled prices remain discrete observations. The floating playhead
only moves the camera and reveals complete candles. Gold between closes is a
decorative polyline, never a synthetic observation or an intraday reconstruction.
"""
from __future__ import annotations
from pathlib import Path
from types import SimpleNamespace
import bisect,hashlib,json,math,re
import numpy as np
from PIL import Image,ImageDraw,ImageChops
from .model import MarketData,FrameState
from .drawing import SceneDrawer,C,smooth


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class MonotoneClock:
    def __init__(self, times, positions):
        self.times=np.asarray(times,dtype=float);self.positions=np.asarray(positions,dtype=float)
        if len(times)<2 or len(times)!=len(positions) or np.any(np.diff(self.times)<=0) or np.any(np.diff(self.positions)<=0):
            raise ValueError('Clock times and market positions must strictly increase')
        h=np.diff(self.times);d=np.diff(self.positions)/h
        self.slopes=np.empty(len(times));self.slopes[0]=d[0];self.slopes[-1]=d[-1]
        for i in range(1,len(times)-1):
            w1=2*h[i]+h[i-1];w2=h[i]+2*h[i-1]
            self.slopes[i]=(w1+w2)/(w1/d[i-1]+w2/d[i])
    def at(self,t):
        j=max(0,min(len(self.times)-2,bisect.bisect_right(self.times,t)-1));h=self.times[j+1]-self.times[j];u=max(0,min(1,(t-self.times[j])/h))
        return float((2*u**3-3*u**2+1)*self.positions[j]+(u**3-2*u**2+u)*h*self.slopes[j]+(-2*u**3+3*u**2)*self.positions[j+1]+(u**3-u**2)*h*self.slopes[j+1])


class Chapter:
    """Source-checked, frame-addressable input shared by all render chunks."""
    def __init__(self,root,config):
        self.root=Path(root).resolve();self.path=Path(config).resolve();self.data=json.loads(self.path.read_text());self.market=MarketData(self.root/'data/cyb_daily.csv')
        self.fps=self.data['fps'];self.duration=self.data['duration_seconds'];self.frame_count=round(self.duration*self.fps)
        self.events=self.data['events'];self.hashes={str(self.path):digest(self.path)}
        csv=self.root/'data/cyb_daily.csv'
        if digest(csv)!=self.data['csv_sha256']:raise ValueError('Frozen CSV digest differs')
        self.hashes[str(csv)]=digest(csv)
        for source in self.data['sources'].values():
            for field,key in [('document','sha256'),('extracted_text','text_sha256')]:
                p=(self.root/source[field]).resolve()
                if not p.is_relative_to(self.root) or digest(p)!=source[key]:raise ValueError(f'Source integrity failure: {source[field]}')
                self.hashes[str(p)]=source[key]
        knots=self.data['clock'];self.clock=MonotoneClock([k['t'] for k in knots],[self.market.index_for_date(k['date'])+k['fraction'] for k in knots])
        previous_end=0
        for e in self.events:
            if not previous_end<=e['start']<e['end']<=self.duration:raise ValueError('Overlapping or invalid editorial slots')
            previous_end=e['end'];e['index']=self.market.index_for_date(e['anchor'])
            if math.floor(self.clock.at(e['start'])+1e-8)<e['index']:raise ValueError(f'Event precedes market anchor: {e["id"]}')
            if e.get('quote'):
                s=self.data['sources'][e['source_id']];text=(self.root/s['extracted_text']).read_text(encoding='utf-8')
                if re.sub(r'\s+','',e['quote']) not in re.sub(r'\s+','',text):raise ValueError('Direct quote absent from reviewed body')
            if e.get('measurement'):
                a,b=e['measurement'];self.market.index_for_date(a);self.market.index_for_date(b)
                if self.market.index_for_date(b)>e['index']:raise ValueError('Measurement endpoint occurs in future')
            if e.get('metric'):
                q=e['metric'];end=self.market.index_for_date(q.get('date',q.get('to')));start=end-1 if q['kind']=='daily' else self.market.index_for_date(q['from'])
                pct=(self.market.close[end]/self.market.close[start]-1)*100
                if abs(round(float(pct),2)-q['pct'])>.001:raise ValueError(f'Metric differs: {e["id"]}')
        for date in ['2015-08-21','2015-08-24','2015-08-25']:
            i=self.market.index_for_date(date)
            if not self.market.high[i]<self.market.low[i-1]:raise ValueError('Full gap predicate failed')
        i=self.market.index_for_date('2015-08-26')
        if self.market.high[i]<self.market.low[i-1]:raise ValueError('August 26 incorrectly classified as complete gap')
    def assert_stable(self):
        if any(digest(p)!=sha for p,sha in self.hashes.items()):raise RuntimeError('Frozen chapter inputs changed during rendering')
    def camera(self,t):
        keys=self.data['camera'];j=max(0,min(len(keys)-2,bisect.bisect_right([k['t'] for k in keys],t)-1));a,b=keys[j:j+2];u=smooth((t-a['t'])/(b['t']-a['t']))
        c={key:a[key]+(b[key]-a[key])*u for key in ['low','high','lock_x']};c['span']=math.exp(math.log(a['span'])+(math.log(b['span'])-math.log(a['span']))*u);return c
    def state(self,n):
        if not 0<=n<self.frame_count:raise ValueError('Frame outside chapter')
        t=n/self.fps;play=self.clock.at(t);i=math.floor(play+1e-8);m=self.market;c=self.camera(t)
        high=m.index_for_date('2015-06-03');jul7=m.index_for_date('2015-07-07');jul23=m.index_for_date('2015-07-23');low=m.index_for_date('2015-09-15')
        if i<=high:base=m.index_for_date('2012-12-03');label='较2012低点上涨';mode='rise';limit=5.708
        elif jul7<i<=jul23:base=jul7;label='7月阶段反弹';mode='rise';limit=.2619
        elif i>low:base=low;label='低点后反弹';mode='rise';limit=.3
        else:base=high;label='高点后回撤';mode='drawdown';limit=.5486
        value=float(m.close[i]/m.close[base]-1)
        s=FrameState(t,n,play,i,m.dates[i],float(m.close[i]),round(c['span']),.85,max(0,i-round(c['span'])),i+2,c['low'],c['high'],'continuous_chapter',mode,label,value,min(1,abs(value)/limit),(),())
        return s,c


class ContinuousRenderer:
    def __init__(self,root,config,width=1080):
        self.chapter=Chapter(root,config);self.root=Path(root);self.m=self.chapter.market;self.w=width;self.h=round(width*16/9);self.s=width/720
        model=SimpleNamespace(video={'width':self.w,'height':self.h},style={},states=[],events=[],market=self.m,config={'sample':{'timeline_start':'2012-01-01','timeline_end':'2016-01-01','timeline_years':[2012,2013,2014,2015]}})
        self.drawer=SceneDrawer(model,self.root/'assets');self.hs=self.s*2;self.step=12.;self.y0=480.;self.y1=800.;self.base_low=250.;self.base_high=4600.
        self.first=self.m.index_for_date('2012-12-03')-40;self.last=math.floor(self.chapter.clock.at(self.chapter.duration));self.source_h=round(480*self.hs);self.lod_index=None;self.lod_images={}
        self.raster=Image.new('RGBA',(math.ceil((self.last-self.first+2)*self.step*self.hs),self.source_h));d=ImageDraw.Draw(self.raster)
        for i in range(self.first,self.last+1):
            x=(i-self.first+.5)*self.step*self.hs;o,h,l,c=[float(getattr(self.m,k)[i]) for k in ['open','high','low','close']];y=lambda v:(self.base_high-v)/(self.base_high-self.base_low)*self.source_h
            color=C['red'] if c>=o else C['green'];bw=self.step*.64*self.hs
            d.line((x,y(h),x,y(l)),fill=color,width=max(1,round(.7*self.hs)));a,b=sorted((y(o),y(c)));d.rectangle((x-bw/2,a,x+bw/2,max(a+1,b)),fill=color)
    def xy(self,index,price,state,camera):
        return camera['lock_x']+(index-state.playhead_index)*600/camera['span'],self.y1-(price-camera['low'])/(camera['high']-camera['low'])*(self.y1-self.y0)
    def text(self,image,xy,text,size=32,color=C['text'],bold=False):
        self.drawer._pen(image,True).text(xy,text,self.drawer.fonts.get(size,bold),color,id='chapter_'+str(len(self.drawer.text_boxes)),role='chapter')
        self.drawer.text_boxes[-1]['text']=text
    def render(self,n):
        s,c=self.chapter.state(n);m=self.m;t=s.t;i=s.current_index;phase=s.playhead_index-i;d=self.drawer;d.text_boxes=[]
        xscale=c['span']/600*self.step*self.hs/self.s;offset=(s.playhead_index-self.first+.5)*self.step*self.hs-c['lock_x']*self.s*xscale
        yscale=(c['high']-c['low'])/(self.base_high-self.base_low)*self.source_h/((self.y1-self.y0)*self.s);yoffset=(self.base_high-c['high'])/(self.base_high-self.base_low)*self.source_h
        chart_h=round((self.y1-self.y0)*self.s)
        if c['span']>240:
            # Horizontal mip levels are rebuilt only on a new observed date.
            # Truncate before filtering, so future bars cannot bleed into history.
            if self.lod_index!=i:
                end=min(self.raster.width,round((i-self.first+1)*self.step*self.hs))
                observed=self.raster.crop((0,0,end,self.source_h))
                padded=Image.new('RGBA',(end+96,self.source_h));padded.paste(observed,(0,0))
                self.lod_images={factor:padded.resize((math.ceil(padded.width/factor),self.source_h),Image.Resampling.LANCZOS) for factor in (4,16)}
                self.lod_index=i
            images=[self.lod_images[factor].transform((self.w,chart_h),Image.Transform.AFFINE,(xscale/factor,0,offset/factor,0,yscale,yoffset),Image.Resampling.BICUBIC) for factor in (4,16)]
            blend=smooth((math.log(max(xscale,8))-math.log(8))/(math.log(32)-math.log(8)))
            chart=Image.blend(images[0],images[1],blend)
        else:
            chart=self.raster.transform((self.w,chart_h),Image.Transform.AFFINE,(xscale,0,offset,0,yscale,yoffset),Image.Resampling.BICUBIC)
        # Mask all future candles. Fade only the current complete observed OHLC.
        cutoff=self.xy(i-.5,0,s,c)[0]*self.s;right=self.xy(i+.5,0,s,c)[0]*self.s;xx=np.arange(self.w);alpha=np.where(xx<cutoff,255,np.where(xx<=right,round(255*smooth(min(1,phase/.35))),0)).astype(np.uint8);alpha[(xx<26*self.s)|(xx>694*self.s)]=0
        mask=Image.fromarray(np.tile(alpha,(chart.height,1)));chart.putalpha(ImageChops.multiply(chart.getchannel('A'),mask))
        im=d.background.copy();im.alpha_composite(d.grid);im.alpha_composite(chart,(0,round(self.y0*self.s)));im.alpha_composite(d.earth_layer)
        # Gold follows known close points; interpolated glow positions have no price labels.
        u=smooth(min(1,phase/.35));gi=i-1+u;gp=float(m.close[i-1])+(float(m.close[i])-float(m.close[i-1]))*u;gx,gy=self.xy(gi,gp,s,c);light=d._new();pen=d._pen(light)
        points=[self.xy(j,float(m.close[j]),s,c) for j in range(max(self.first,i-5),i)]+[(gx,gy)]
        pen.line(points,(255,192,108,55),3);pen.line(points,(255,221,169,110),.8)
        intensity=.38
        for date in ['2015-06-03','2015-09-15']:intensity+=.25*math.exp(-((s.playhead_index-(m.index_for_date(date)+.35))/.35)**2)
        d._sprite(light,d.gold_glow,gx,gy,intensity);pen.ellipse((gx-3,gy-3,gx+3,gy+3),fill=C['gold_light']);pen.line((gx-22,gy,gx+22,gy),(255,207,130,90),.6)
        lm=Image.new('L',im.size);ImageDraw.Draw(lm).rectangle((26*self.s,self.y0*self.s,694*self.s,self.y1*self.s),fill=255);light.putalpha(ImageChops.multiply(light.getchannel('A'),lm));im.alpha_composite(light)
        d._world(im,s)
        active=next((e for e in self.chapter.events if e['start']<=t<e['end']),None)
        header=d._new();d._header(header,s)
        if active and active['id'] in {'june_policy','cleanup'} and i==active['index']:
            ImageDraw.Draw(header).rectangle((490*self.s,232*self.s,700*self.s,252*self.s),fill=(0,0,0,0))
            d.text_boxes=[box for box in d.text_boxes if box['id']!='current_close_label']
            d._pen(header,True).text((668,235),'上一交易日收盘',d.fonts.get(10),C['muted'],anchor='ra',id='prior_close_label',role='status')
        im.alpha_composite(header);d._footer(im)
        active=next((e for e in self.chapter.events if e['start']<=t<e['end']),None);measure=bool(active and active.get('measurement'))
        rail=d._new();d._rail(rail,s)
        if measure:rail.putalpha(rail.getchannel('A').point(lambda a:round(a*.20)))
        im.alpha_composite(rail)
        for e in self.chapter.events:
            if t<e['start']:continue
            x,y=self.xy(e['index'],float(m.close[e['index']]),s,c)
            if 26<=x<=694 and self.y0<=y<=self.y1:d._pen(im).ellipse((x-1.5,y-1.5,x+1.5,y+1.5),fill=(241,88,66,125))
        measurement_visible=False
        if active:
            e=active;local=t-e['start'];opacity=max(0,min(1,local/.3,(e['end']-t)/.35));layer=d._new();p=d._pen(layer);label=e['label'];tab=min(600,max(158,len(label)*16+20))
            p.polygon([(72,271),(72+tab,271),(63+tab,305),(63,305)],fill=(193,28,38,225));p.line((60,316,45,409),(249,47,51,255),2)
            self.text(layer,(78,274),label,17,bold=True)
            for j,line in enumerate(e['lines']):self.text(layer,(72,320+j*48),line,e.get('size',32),bold=True)
            p.line((72,412,72+260*smooth(min(1,local/.55)),412),(248,46,51,255),2);self.text(layer,(72,432),e['source'],12,C['muted'])
            if measure:
                a,b=[m.index_for_date(date) for date in e['measurement']];ca,cb=float(m.close[a]),float(m.close[b]);xa,ya=self.xy(a,ca,s,c);xb,yb=self.xy(b,cb,s,c)
                if 35<=xa<=520 and 35<=xb<=520 and self.y0<=ya<=self.y1 and self.y0<=yb<=self.y1:
                    measurement_visible=True;x=550.;color=C['gold']
                    for xx,yy in [(xa,ya),(xb,yb)]:p.line((xx,yy,x,yy),(*color[:3],170),.8);p.ellipse((xx-3,yy-3,xx+3,yy+3),fill=C['gold_light']);p.line((x-6,yy,x+6,yy),color,1)
                    p.line((x,ya,x,yb),color,1);mid=(ya+yb)/2;pct=(cb/ca-1)*100
                    self.text(layer,(565,mid-33),f'{pct:+.2f}%',21,color,True);self.text(layer,(565,mid+2),f'{cb-ca:+,.2f}点',11,color)
                    elapsed='约2年6个月' if cb>ca else f'{(m.dates[b]-m.dates[a]).days}个自然日';self.text(layer,(565,mid+23),elapsed,11,C['muted'])
                    self.text(layer,(max(35,xa-8),ya+10 if ca<cb else ya-27),e['measurement'][0].replace('-','.'),11,color)
                    self.text(layer,(max(35,min(420,xb-70)),yb-27 if cb>ca else yb+10),e['measurement'][1].replace('-','.'),11,color)
            else:
                x,y=self.xy(e['index'],float(m.close[e['index']]),s,c)
                if 26<=x<=694 and self.y0<=y<=self.y1:p.line([(144,464),(144,477),(x,y)],(231,179,127,160),.8);p.ellipse((x-3,y-3,x+3,y+3),outline=C['gold'],width=.8)
            if e.get('gap_dates'):
                for day in e['gap_dates']:
                    j=m.index_for_date(day)
                    if i>=j:
                        x,y=self.xy(j,float(m.high[j]),s,c)
                        if 26<x<694:p.line((x-5,y-3,x+5,y-3),C['gold'],1)
            layer.putalpha(layer.getchannel('A').point(lambda a:round(a*opacity)));im.alpha_composite(layer)
        boxes=d.text_boxes;out=[b['id'] for b in boxes if b['bbox'][0]<0 or b['bbox'][1]<0 or b['bbox'][2]>self.w or b['bbox'][3]>self.h];over=[]
        for j,a in enumerate(boxes):
            for b in boxes[j+1:]:
                A,B=a['bbox'],b['bbox']
                if min(A[2],B[2])-max(A[0],B[0])>1 and min(A[3],B[3])-max(A[1],B[1])>1:over.append([a['id'],b['id']])
        return im.convert('RGB'),{'frame':n,'t':t,'date':str(s.current_date.date()),'close':s.current_close,'playhead':s.playhead_index,'camera':c,'event':active['id'] if active else None,'out_of_bounds':out,'text_overlaps':over,'measurement_visible':measurement_visible,'gold':[gx,gy],'text_boxes':boxes}
