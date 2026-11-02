import {mkdirSync,readFileSync,writeFileSync,renameSync} from 'node:fs';
const arg=k=>process.argv[process.argv.indexOf(`--${k}`)+1];
mkdirSync(arg('shots'),{recursive:true});
const page=await(await fetch(`http://127.0.0.1:${arg('cdp')}/json/new?about:blank`,{method:'PUT'})).json();
const ws=new WebSocket(page.webSocketDebuggerUrl);await new Promise(r=>ws.addEventListener('open',r,{once:true}));
let seq=0;const pending=new Map(),errors=[],report={errors,widths:[]},wire=[],mappingIds=new Set();
const send=(method,params={})=>new Promise((resolve,reject)=>{
 const id=++seq,t=setTimeout(()=>{pending.delete(id);reject(Error(`CDP timeout ${method}`));},15000);
 pending.set(id,m=>{clearTimeout(t);m.error?reject(Error(JSON.stringify(m.error))):resolve(m.result)});
 ws.send(JSON.stringify({id,method,params}));
});
ws.addEventListener('message',e=>{const m=JSON.parse(e.data);if(pending.has(m.id)){pending.get(m.id)(m);pending.delete(m.id)}
 if(m.method==='Network.webSocketFrameSent'||m.method==='Network.webSocketFrameReceived'){
   try{const data=JSON.parse(m.params.response.payloadData);
    if(data.t==='cmd'&&data.name==='pad.op'&&data.args?.op==='mapping'){mappingIds.add(data.id);wire.push(data)}
    else if(data.t==='result'&&mappingIds.has(data.id))wire.push(data);
   }catch{}
 }
 if(m.method==='Runtime.exceptionThrown')errors.push(m.params.exceptionDetails.exception?.description||m.params.exceptionDetails.text)});
const js=async expression=>{const r=await send('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});
 if(r.exceptionDetails)throw Error(r.exceptionDetails.exception?.description||r.exceptionDetails.text);return r.result?.value};
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
const assert=(v,m)=>{if(!v)throw Error(m)};
const wait=async(expr,label)=>{const end=Date.now()+14000;while(Date.now()<end){if(await js(expr))return;await sleep(60)}
 throw Error(`Timeout ${label}: ${await js("document.querySelector('.pad-mapping')?.innerText||document.body.innerText.slice(0,1800)")}`)};
const click=async s=>{await wait(`document.querySelector(${JSON.stringify(s)})&&!document.querySelector(${JSON.stringify(s)}).disabled`,s);await js(`document.querySelector(${JSON.stringify(s)}).click()`)};
const replaceInput=(path,raw)=>{
 writeFileSync(path+'.tmp',JSON.stringify(raw));
 for(let retry=0;;retry++){
  try{renameSync(path+'.tmp',path);return}catch(error){
   if(!['EPERM','EBUSY'].includes(error.code)||retry>=100)throw error;
   // A Windows Python read can briefly hold an NTFS handle without delete
   // sharing. Keep the atomic replacement and bound the retry to 500 ms.
   Atomics.wait(new Int32Array(new SharedArrayBuffer(4)),0,0,5);
  }
 }
};
const event=(kind,code,value)=>{const path=arg('input'),raw=JSON.parse(readFileSync(path,'utf8'));raw.seq++;
 raw.events.push({seq:raw.seq,kind,code,value});raw.events=raw.events.slice(-256);raw[kind===1?'buttons':'axes'][String(code)]=kind===1?!!value:value;
 replaceInput(path,raw)};
const inputFlag=(name,value)=>{const path=arg('input'),raw=JSON.parse(readFileSync(path,'utf8'));raw[name]=value;
 replaceInput(path,raw)};
const key=async(role,code)=>{await click(`[data-map-role="${role}"]`);await wait(`document.querySelector('[data-map-capture]')?.dataset.role===${JSON.stringify(role)}`,'capture arm');
 event(1,code,1);await wait(`document.querySelector('[data-map-role="${role}"]')?.dataset.bound==='true'`,'key captured');event(1,code,0);await sleep(250)};
try{
 await send('Page.enable');await send('Runtime.enable');await send('Network.enable');await send('Emulation.setFocusEmulationEnabled',{enabled:true});
 await send('Emulation.setDeviceMetricsOverride',{width:1440,height:1000,deviceScaleFactor:1,mobile:false});
 await send('Page.navigate',{url:arg('url')});
 await wait(`!!document.querySelector('[data-map-open]')`,'mapping entry');await click('[data-map-open]');
 await wait(`!!document.querySelector('.pad-mapping')`,'mapping panel');
 await click('[data-map-begin]');await wait(`document.querySelector('.pad-mapping')?.dataset.mine==='true'`,'native pause acknowledged');
 assert(await js(`document.querySelectorAll('.pad-mapping .pd-key-note').length===0`),'mapping diagram contains only input names');
 report.guarded=await js(`document.querySelector('[data-map-blocked]')?.innerText.includes('暂停')`);assert(report.guarded,'pause status');
 await js(`window.mappingObserver=new WebSocket(location.origin.replace('http','ws')+'/ws');window.mappingObserverResults={};
   mappingObserver.onmessage=e=>{let r=JSON.parse(e.data);if(r.t==='result')mappingObserverResults[r.id]=r};
   new Promise(resolve=>mappingObserver.onopen=resolve)`);
 await js(`mappingObserver.send(JSON.stringify({t:'cmd',id:'read-owner',name:'pad.op',args:{op:'mapping',action:'status'}}));
   mappingObserver.send(JSON.stringify({t:'cmd',id:'steal-owner',name:'pad.op',args:{op:'mapping',action:'learn',role:'south'}}));`);
 await wait(`mappingObserverResults['read-owner']&&mappingObserverResults['steal-owner']`,'observer ownership checks');
 assert(await js(`mappingObserverResults['read-owner'].data.owned&&!mappingObserverResults['read-owner'].data.mine&&
   !mappingObserverResults['steal-owner'].ok&&!JSON.stringify(mappingObserverResults).includes('fixture-private-token')`),'observer cannot change or obtain token');
 report.ownership=true;
 await key('south',305);await key('east',304);report.button_swap=true;
 await click('[data-map-role="west"]');await wait(`document.querySelector('[data-map-capture]')?.dataset.role==='west'`,'duplicate capture');
 event(1,305,1);await wait(`document.querySelector('.map-error')?.innerText.includes('已用于')`,'duplicate rejected');event(1,305,0);await sleep(250);
 assert(await js(`document.querySelector('[data-map-role="west"]').dataset.bound!=='true'`),'duplicate never overwrites');report.duplicate=true;
 await key('select',314);await key('start',315);
 for(const [role,code,value] of [['du',17,-1],['dd',17,1],['dl',16,-1],['dr',16,1]]){
   await click(`[data-map-role="${role}"]`);await wait(`document.querySelector('[data-map-capture]')?.dataset.role==='${role}'`,'hat capture');
   event(3,code,value);await wait(`document.querySelector('[data-map-role="${role}"]').dataset.bound==='true'`,'hat bound');event(3,code,0);await sleep(250);
 }report.hats=true;
 await key('rt',313);
 await click('[data-map-role="lt"]');await wait(`document.querySelector('[data-map-capture]')?.dataset.role==='lt'`,'trigger capture');
 event(3,2,255);await sleep(250);event(3,2,0);await sleep(250);await click('[data-map-confirm-axis]');
 await wait(`document.querySelector('[data-map-role="lt"]').dataset.bound==='true'`,'analog trigger');report.triggers=true;
 for(const [role,code] of [['lx',3],['ly',0],['rx',1],['ry',4]]){
   await click(`[data-map-role="${role}"]`);await wait(`document.querySelector('[data-map-capture]')?.dataset.role==='${role}'`,'axis arm');
   for(const v of role==='ly'?[-100,100,0]:[100,-100,0]){event(3,code,v);await sleep(250)}
   await click('[data-map-confirm-axis]');await wait(`document.querySelector('[data-map-role="${role}"]')?.dataset.bound==='true'`,'axis confirmed');
 }
 report.axis_calibration=true;
 await js(`{let select=document.querySelector('[data-map-deadzone="lx"]');select.value='0.18';select.dispatchEvent(new Event('change',{bubbles:true}));}`);
 await wait(`document.querySelector('[data-map-deadzone="lx"]')?.value==='0.18'`,'deadzone readback');report.deadzone=true;
 event(1,305,1);await wait(`!!document.querySelector('.pad-mapping .pd-svg .pd-on')`,'preview lights mapped A');event(1,305,0);
 for(const width of [1440,390,320]){
  await send('Emulation.setDeviceMetricsOverride',{width,height:1000,deviceScaleFactor:1,mobile:width<500});
  await js(`document.querySelector('.pad-mapping').scrollIntoView({block:'start'})`);await sleep(120);
  assert(await js(`document.documentElement.scrollWidth<=innerWidth+1`),`overflow ${width}`);
  const shot=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});
  writeFileSync(`${arg('shots')}/mapping-${width}.png`,Buffer.from(shot.data,'base64'));report.widths.push(width);
  await js(`document.querySelector('.map-save').scrollIntoView({block:'end'})`);await sleep(100);
  assert(await js(`document.documentElement.scrollWidth<=innerWidth+1`),`footer overflow ${width}`);
  const footer=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});
  writeFileSync(`${arg('shots')}/mapping-footer-${width}.png`,Buffer.from(footer.data,'base64'));
 }
 await click('[data-map-save]');await wait(`document.querySelector('[data-map-message]')?.innerText.includes('已保存')`,'saved readback');
 await send('Page.reload');await wait(`!!document.querySelector('[data-map-open]')`,'reload');await click('[data-map-open]');
 await wait(`document.querySelector('[data-map-profile]')?.innerText.includes('测试手柄')`,'saved profile reload');report.save_reload=true;
 assert(await js(`!document.querySelector('.pad-mapping').dataset.mine || document.querySelector('.pad-mapping').dataset.mine==='false'`),'reload cannot resume learning');report.no_auto_resume=true;
 await click('[data-map-begin]');await wait(`document.querySelector('.pad-mapping').dataset.mine==='true'`,'reenter');
 await click('[data-map-clear="lx"]');await click('[data-map-clear="ly"]');
 assert(await js(`document.querySelector('[data-map-save]').disabled`),'incomplete required draft cannot save');
 for(const [role,code] of [['lx',0],['ly',3]]){
   await click(`[data-map-role="${role}"]`);await wait(`document.querySelector('[data-map-capture]')?.dataset.role==='${role}'`,'saved axis swap arm');
   for(const value of [100,-100,0]){event(3,code,value);await sleep(250)}
   await click('[data-map-confirm-axis]');await wait(`!document.querySelector('[data-map-capture]')`,'saved axis swap confirmed');
 }
 await click('[data-map-save]');await wait(`document.querySelector('[data-map-message]')?.innerText.includes('已保存')`,'edited axis swap saved');
 await click('[data-map-begin]');await wait(`document.querySelector('.pad-mapping').dataset.mine==='true'`,'edited swap reenter');
 await click('[data-map-role="rx"]');event(3,0,100);
 await wait(`Number(document.querySelector('.pad-mapping [data-role="ls"] .pd-stick-cap')?.getAttribute('cx'))===132`,'edited swap native preview');
 event(3,0,0);report.edit_swap_save=true;
 await key('south',307);await click('[data-map-cancel]');await wait(`!document.querySelector('.pad-mapping').dataset.mine`,'cancel ack');
 await click('[data-map-begin]');await wait(`document.querySelector('.pad-mapping').dataset.mine==='true'`,'cancel reenter');
 await click('[data-map-role="lx"]');event(1,305,1);await wait(`!!document.querySelector('.pad-mapping [data-role="south"].pd-on')`,'cancel keeps original binding');event(1,305,0);report.cancel_preserves=true;
 await js(`location.hash='#/logs'`);await sleep(600);await js(`location.hash='#/pad'`);
 await wait(`!!document.querySelector('.pad-mapping')&&!document.querySelector('.pad-mapping').dataset.mine`,'leaving cancels lease');report.navigation_cancel=true;
 inputFlag('disconnect',true);await wait(`document.querySelector('[data-map-profile]')?.innerText.includes('等待读到')`,'device disconnected');
 inputFlag('disconnect',false);await wait(`document.querySelector('[data-map-profile]')?.innerText.includes('已保存')`,'device reconnect profile');report.reconnect=true;
 await click('[data-map-begin]');await wait(`document.querySelector('.pad-mapping').dataset.mine==='true'`,'background reenter');
 const backgroundStart=wire.length;
 await js(`Object.defineProperty(document,'visibilityState',{configurable:true,get:()=> 'hidden'});document.dispatchEvent(new Event('visibilitychange'))`);
 const backgroundDeadline=Date.now()+5000;let canceled=false;
 while(Date.now()<backgroundDeadline&&!canceled){
   const messages=wire.slice(backgroundStart),cancel=messages.find(m=>m.t==='cmd'&&m.args?.action==='cancel');
   canceled=!!cancel&&messages.some(m=>m.t==='result'&&m.id===cancel.id&&m.ok&&!m.data.mine);await sleep(30);
 }assert(canceled,'background receives native cancellation acknowledgment');
 await js(`Object.defineProperty(document,'visibilityState',{configurable:true,get:()=> 'visible'});document.dispatchEvent(new Event('visibilitychange'))`);
 await wait(`!document.querySelector('.pad-mapping').dataset.mine`,'background cancels native lease');report.background_cancel=true;
 await click('[data-map-begin]');await wait(`document.querySelector('.pad-mapping').dataset.mine==='true'`,'reset reenter');
 await click('[data-map-reset]');await wait(`!!document.querySelector('[data-map-reset-confirm]')`,'reset confirmation');await click('[data-map-reset-confirm]');
 await wait(`document.querySelector('[data-map-message]')?.innerText.includes('默认')`,'reset native ack');report.reset=true;
 assert(errors.length===0,errors.join('\n'));console.log(JSON.stringify(report,null,2));
}finally{writeFileSync(`${arg('shots')}/mapping-wire.json`,JSON.stringify(wire,null,2));ws.close()}
