import {spawn} from 'node:child_process';
import fs from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import {createServer} from 'node:http';
import {createReadStream} from 'node:fs';

const [video, out, durationText, frameArgument = ''] = process.argv.slice(2);
const markerFrames = [...new Set(frameArgument.split(',').filter(Boolean).map(Number))].sort((a,b)=>a-b);
if (markerFrames.some(frame => !Number.isInteger(frame) || frame < 0)) throw Error('Expected frame indices');
const duration = Number(durationText);
if (!(duration > 0 && duration <= 60)) throw Error('Expected approved representative-block duration');
await fs.mkdir(path.join(out, 'playback'), {recursive:true});
const temp = await fs.mkdtemp(path.join(os.tmpdir(), 'wf102-browser-'));
const html = `<!doctype html><meta charset="utf-8">
<style>body{margin:0;background:#000}video{display:block;width:390px;height:694px;object-fit:contain}</style>
<video id="media" muted playsinline preload="auto" src="/preview.mp4"></video>
<script>
window.records = [];
const v=document.getElementById('media');
for (const name of ['loadedmetadata','play','pause','seeking','ratechange','waiting','stalled','playing','error','ended']) {
 v.addEventListener(name, () => records.push({event:name, at:v.currentTime, clock:performance.now(),
  code:v.error?.code ?? null}));
}
</script>`;
const size=(await fs.stat(video)).size;
const server=createServer((req,res) => {
  if (req.url==='/preview.mp4') {
    const range=/^bytes=(\d+)-(\d*)$/.exec(req.headers.range ?? '');
    const start=range?Number(range[1]):0;
    const end=range && range[2]?Math.min(size-1,Number(range[2])):size-1;
    const headers={'Content-Type':'video/mp4','Accept-Ranges':'bytes','Content-Length':end-start+1};
    if (range) headers['Content-Range']=`bytes ${start}-${end}/${size}`;
    res.writeHead(range?206:200,headers);
    if(req.method==='HEAD') return res.end();
    createReadStream(video,{start,end}).pipe(res);
  } else if (req.url==='/review.html') {
    res.writeHead(200,{'Content-Type':'text/html; charset=utf-8'});
    res.end(html);
  } else {
    res.writeHead(404).end();
  }
});
await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
const reviewUrl=`http://127.0.0.1:${server.address().port}/review.html`;
const browser = spawn('/usr/bin/chromium', ['--headless', '--no-sandbox', '--disable-dev-shm-usage',
    '--disable-gpu', '--disable-background-timer-throttling', '--disable-renderer-backgrounding',
    '--remote-debugging-port=0', '--autoplay-policy=no-user-gesture-required',
    '--no-first-run', '--no-default-browser-check', `--user-data-dir=${temp}/profile`,
    reviewUrl], {stdio:'ignore'});
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
let socket;
const timeout = setTimeout(() => process.exit(5), (duration+35)*1000);
try {
  let port;
  for (let i=0; i<60 && !port; i++) {
    try { [port] = (await fs.readFile(path.join(temp,'profile/DevToolsActivePort'),'utf8')).split('\n'); }
    catch { await sleep(200); }
  }
  if (!port) throw Error('Browser did not start');
  const tabs = await (await fetch(`http://127.0.0.1:${port}/json/list`)).json();
  const tab = tabs.find(item=>item.url.includes('review.html')) ?? tabs.find(item=>item.type==='page');
  socket = new WebSocket(tab.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => {
    socket.addEventListener('open', resolve, {once:true});
    socket.addEventListener('error', reject, {once:true});
  });
  let id=0;
  const pending = new Map();
  socket.addEventListener('message', ({data}) => {
    const row=JSON.parse(data);
    if (!pending.has(row.id)) return;
    const [resolve,reject]=pending.get(row.id);
    pending.delete(row.id);
    if (row.error) reject(row.error); else resolve(row.result);
  });
  const cdp = (method, params={}) => new Promise((resolve,reject)=>{
    pending.set(++id,[resolve,reject]);
    socket.send(JSON.stringify({id,method,params}));
  });
  const evaluate = async expression => {
    const result=await cdp('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});
    if (result.exceptionDetails) throw Error(JSON.stringify(result.exceptionDetails));
    return result.result.value;
  };
  await cdp('Page.enable');
  await cdp('Page.navigate', {url:reviewUrl});
  for (let tries=0; tries<60; tries++) {
    if (await evaluate('Boolean(document.querySelector("video"))')) break;
    await sleep(200);
  }
  await cdp('Emulation.setDeviceMetricsOverride',{width:390,height:694,deviceScaleFactor:1,mobile:false});
  const page=await evaluate('({href:location.href,ready:document.readyState,video:!!document.querySelector("video"),title:document.title})');
  console.log(JSON.stringify({page}));
  if (!page.video) throw Error('Local video page unavailable');
  const codec=await evaluate('document.querySelector("video").canPlayType(\'video/mp4; codecs="avc1.42E01E"\')');
  if (!codec) throw Error('Chromium MP4/H.264 codec unavailable');
  const began=Date.now();
  await evaluate(`(() => {
    const v=document.querySelector('video');
    v.playbackRate = 1;
    const wanted = ${JSON.stringify(markerFrames)};
    window.visualSamples = [];
    if (wanted.length) {
      const canvas=document.createElement('canvas');
      canvas.width=390;
      canvas.height=694;
      const ctx=canvas.getContext('2d');
      let cursor=0;
      const capture=(now, metadata)=>{
        const current=Math.round(metadata.mediaTime * 30);
        if (wanted[cursor] <= current) {
          const targets=[];
          while (wanted[cursor] <= current) targets.push(wanted[cursor++]);
          ctx.drawImage(v,0,0,390,694);
          visualSamples.push({targets, current, mediaTime:metadata.mediaTime, jpg:canvas.toDataURL('image/jpeg',.91)});
        }
        if (cursor < wanted.length) v.requestVideoFrameCallback(capture);
      };
      v.requestVideoFrameCallback(capture);
    }
    return v.play();
  })()`);
  const snapshots=[];
  let result;
  for (let i=0; i<Math.ceil((duration+10)/3); i++) {
    result=await evaluate(`(()=>{
      const video=document.querySelector('video'), q=video.getVideoPlaybackQuality();
      return {currentTime:video.currentTime,duration:video.duration,width:video.videoWidth,height:video.videoHeight,
         rate:video.playbackRate,muted:video.muted,ended:video.ended,error:video.error?.code ?? null,readyState:video.readyState,
         frames:q.totalVideoFrames,dropped:q.droppedVideoFrames,events:records,played:Array.from({length:video.played.length},(_,i)=>[video.played.start(i),video.played.end(i)])};
    })()`);
    if (result.error) throw Error(`Media playback error ${result.error}`);
    if (result.ended) break;
    await sleep(2950);
  }
  const wallSeconds=(Date.now()-began)/1000;
  for (const {jpg, ...row} of await evaluate('window.visualSamples')) {
    const file=`playback/presented_${String(row.current).padStart(4,'0')}.jpg`;
    await fs.writeFile(path.join(out,file),Buffer.from(jpg.split(',')[1],'base64'));
    snapshots.push({...row,file});
  }
  const passed=!!result.ended && !result.error && result.rate===1 &&
       !result.events.some(event=>event.event==='seeking' || (event.event==='pause' && event.at<duration-.05)) && Math.abs(result.duration-duration)<=.01 &&
       result.width===390 && result.height===694 && result.currentTime>=duration-.01 &&
       result.played.length===1 && result.played[0][0]<=.05 &&
       result.played[0][1]>=duration-.01 && wallSeconds>=duration-1;
  await fs.writeFile(path.join(out,'playback_observation.json'),JSON.stringify({
    passed,mode:'chromium_headless_actual_realtime_playback_no_seeks',wallSeconds,result,snapshots
  },null,2)+'\n');
  if (!passed) throw Error('Chromium did not report complete playback');
} finally {
  clearTimeout(timeout);
  if (socket) socket.close();
  browser.kill();
  server.closeAllConnections();
  server.close();
  await fs.rm(temp,{recursive:true,force:true,maxRetries:3});
}
