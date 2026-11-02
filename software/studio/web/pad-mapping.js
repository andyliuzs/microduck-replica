import { html, useEffect, useRef, useState } from './vendor/preact-htm.module.js';

const BUTTONS=[['south','A（下）'],['east','B（右）'],['west','X（左）'],['north','Y（上）'],['lb','LB'],['rb','RB'],
  ['select','Select／返回'],['start','Start／开始'],['du','十字上'],['dd','十字下'],['dl','十字左'],['dr','十字右'],
  ['l3','L3（左摇杆按下）'],['r3','R3（右摇杆按下）'],['home','Home']];
const AXES=[['lx','左摇杆左右'],['ly','左摇杆上下'],['rx','右摇杆左右'],['ry','右摇杆上下'],['lt','LT'],['rt','RT']];
const ALL=[...BUTTONS,...AXES], NAMES=Object.fromEntries(ALL), REQUIRED=new Set(['select','start','lx','ly','rx','ry']);
const instruction=role=>{
  if(['lx','rx'].includes(role))return '先向右推到底，再向左推到底，最后松手回中，点击“确认本轴”。只操作这一根轴。';
  if(['ly','ry'].includes(role))return '先向下推到底，再向上推到底，最后松手回中，点击“确认本轴”。只操作这一根轴。';
  if(['lt','rt'].includes(role))return '把目标扳机按到底，再完全松开，点击“确认本轴”。数字扳机按一下即可识别。';
  return `按一下你想作为“${NAMES[role]}”的实体键，然后松开。`;
};

export function PadMapping({ mapping, link, active, Diagram, onClose }) {
  const [view,setView]=useState(mapping||{}),[error,setError]=useState(null),[busy,setBusy]=useState(false);
  const [name,setName]=useState(''),[reset,setReset]=useState(false),[automatic,setAutomatic]=useState(false);
  const current=useRef(view),closed=useRef(false),oldCapture=useRef(null),activeRef=useRef(active);
  current.current=view;
  activeRef.current=active;
  useEffect(()=>{if(mapping)setView(mapping)},[mapping]);
  const call=async(action,extra={})=>{
    setError(null);setBusy(true);
    try{
      const r=await link.cmd('pad.op',{op:'mapping',action,...extra},8000);
      if(closed.current)return null;
      if(!r.ok){setError(r.reason||r.error||'操作没有完成，请重试');return null}
      if(r.data)setView(r.data);
      return r.data;
    }catch{if(!closed.current)setError('与鸭子的连接断开，请恢复连接后重试');return null}
    finally{if(!closed.current)setBusy(false)}
  };
  const learn=(role,auto=false)=>{if(!auto)setAutomatic(false);return call('learn',{role})};
  const begin=async()=>{
    setReset(false);const next=await call('begin');
    if(next?.mine){setName(next.profile?.name||next.device?.name||'我的手柄');setAutomatic(true);await learn('south',true)}
  };
  const nextRole=role=>{
    const index=ALL.findIndex(([r])=>r===role);
    if(index>=0&&index+1<ALL.length)learn(ALL[index+1][0],true);else setAutomatic(false);
  };
  useEffect(()=>{
    const previous=oldCapture.current;
    if(automatic&&previous&&!view.capture&&view.draft?.[previous])nextRole(previous);
    oldCapture.current=view.capture?.role||null;
  },[view.capture?.role,view.draft]);
  useEffect(()=>{
    closed.current=false;
    call('status');
    const cancel=()=>{
      if(current.current.mine)call('cancel');
      setAutomatic(false);
    };
    const visible=()=>{if(document.visibilityState!=='visible')cancel()};
    const timer=setInterval(()=>{
      if(!activeRef.current||document.visibilityState!=='visible')return;
      const action=current.current.mine?'heartbeat':'status';
      link.cmd('pad.op',{op:'mapping',action},4000).then(r=>{
        if(closed.current)return;
        if(r.ok&&r.data)setView(r.data);
      }).catch(()=>{});
    },1000);
    document.addEventListener('visibilitychange',visible);
    return()=>{cancel();closed.current=true;clearInterval(timer);document.removeEventListener('visibilitychange',visible)};
  },[]);
  useEffect(()=>{
    if(!active&&view.mine){setAutomatic(false);call('cancel')}
  },[active,view.mine]);
  const close=async()=>{setAutomatic(false);if(view.mine)await call('cancel');onClose()};
  const draft=view.mine?view.draft||{}:view.profile?.bindings||{};
  const capture=view.capture,role=capture?.role;
  const shown=view.mine?(view.preview||{buttons:{},axes:{}}):view.mapped||{buttons:{},axes:{}};
  const canLearn=view.mine&&!busy;
  const disabled=busy||!view.available||view.output_blocked||!!view.owned;
  const skip=async target=>{const r=await call('skip',{role:target});if(r&&automatic)nextRole(target)};
  const row=([target,label])=>html`<div class=${'map-control-row'+(AXES.some(([r])=>r===target)?' map-axis-row':'')+(role===target?' selected':'')}>
    <button type="button" class="map-target" data-map-role=${target} data-bound=${!!draft[target]}
      disabled=${!canLearn} onClick=${()=>learn(target)} aria-pressed=${role===target}>
      <span>${label}${REQUIRED.has(target)?html`<small>必需</small>`:null}</span><span class="map-binding">${draft[target]?'✓ 已设置':'未设置'}</span></button>
    ${canLearn&&draft[target]?html`<button type="button" class="map-text-button" data-map-clear=${target} aria-label=${'清除'+label}
      onClick=${()=>{setAutomatic(false);call('clear',{role:target})}}>清除</button>`:null}
    ${canLearn&&draft[target]?.kind==='axis'?html`<button type="button" class="map-text-button" onClick=${()=>call('invert',{role:target})}>${draft[target].invert?'反向 ✓':'反向'}</button>`:null}
    ${canLearn&&draft[target]?.kind==='axis'?html`<label class="map-axis-deadzone"><span>死区</span><select data-map-deadzone=${target}
      aria-label=${label+'死区'} disabled=${busy} value=${String(draft[target].deadzone)}
      onChange=${e=>call('deadzone',{role:target,value:Number(e.currentTarget.value)})}>
      ${[.02,.04,.08,.12,.18,.25,.3].map(value=>html`<option value=${String(value)}>${Math.round(value*100)}%</option>`)}</select></label>`:null}
  </div>`;
  return html`<section class="board pad-mapping" data-mine=${!!view.mine} aria-labelledby="pad-mapping-title">
    <header class="map-header"><div><span class="map-eyebrow">实体手柄 · 按键学习</span><h3 id="pad-mapping-title">重新映射／校准</h3></div>
      <button type="button" class="map-button" disabled=${busy} onClick=${close}>${view.mine?'取消并关闭':'关闭'}</button></header>
    <p class="map-lead">点击图上的标准键，再按实体手柄上想作为这个键的按钮。即使 A／B 印字和位置不同，也按你设置的对应关系使用。</p>
    <div class="map-device" data-map-profile><b>${view.device?.name||'等待读到手柄'}</b><span>${view.profile?'已保存：'+view.profile.name:'默认识别 · 尚未保存自定义映射'}</span></div>
    ${view.output_blocked?html`<p class="map-paused" role="status" data-map-blocked>手柄动作输出已暂停。${view.mine?'当前只学习和测试输入，鸭子不会执行测试动作。':'请松开所有键、让摇杆回中，等待恢复。'}网页卸力仍可使用。</p>`:null}
    ${error||view.error?html`<p class="map-error" role="alert">${error||view.error}</p>`:null}
    ${view.message?html`<p class="map-message" data-map-message role="status">${view.message}</p>`:null}
    ${!view.mine?html`<div class="map-start"><p>先让鸭子“停下（站好）”，再开始学习。已有配置可单独重录，重连后自动加载。</p>
      <button class="map-button primary" type="button" data-map-begin disabled=${disabled} onClick=${begin}>${view.profile?'编辑已保存的映射':'开始按键学习'}</button>
      ${view.owned?html`<p>另一个页面正在映射，请在原页面完成或取消。</p>`:null}
      ${!view.available?html`<button class="map-button" type="button" disabled=${busy} onClick=${()=>call('status')}>重试读取手柄服务</button>`:null}</div>`:null}
    <div class="map-layout"><div class="map-visual">
      <div class="map-diagram"><${Diagram} live=${shown} kind="xbox" mappingView=${true} learn=${canLearn?target=>learn(target==='ls'?'lx':target==='rs'?'rx':target):null} /></div>
      <p class="map-help">本图使用标准 Xbox 名称：A 在下、B 在右、X 在左、Y 在上。点击摇杆图先学习左右轴；上下轴、L3／R3 在右侧列表选择。</p>
      ${capture?html`<div class="map-capture" role="status" data-map-capture data-role=${role}>
        <span>正在学习</span><b>${NAMES[role]}</b><p>${instruction(role)}</p>
        <small>${capture.state==='sweeping'?'已识别到轴，请完成两端行程并回中。':capture.state==='error'?'请点击同一目标重新学习。':'等待实体手柄输入…'}</small>
        <div class="map-actions">${AXES.some(([r])=>r===role)?html`<button type="button" class="map-button primary" data-map-confirm-axis disabled=${busy||capture.code==null||capture.state==='error'} onClick=${()=>call('confirm_axis')}>确认本轴</button>`:null}
          ${!REQUIRED.has(role)?html`<button type="button" class="map-button" disabled=${busy} onClick=${()=>skip(role)}>跳过此项</button>`:null}
          <button type="button" class="map-button" disabled=${busy} onClick=${()=>learn(role)}>重录此项</button></div>
      </div>`:view.mine?html`<p class="map-help">已识别的键会在图上高亮。继续点击目标重录，或推摇杆、按键检查对应关系。</p>`:null}
    </div><div class="map-controls"><h4>按键对应</h4><div class="map-button-grid">${BUTTONS.map(row)}</div>
      <h4>摇杆与扳机</h4>${AXES.map(row)}
      ${view.mine?html`<p class="map-help">死区用于抑制松手回中后的微小漂移，可分别调整每根轴。反向用于修正推杆方向。</p>`:null}
    </div></div>
    ${view.mine?html`<footer class="map-save"><label>这份映射的名称<input type="text" maxLength="60" value=${name} placeholder="例如：我的盖世小鸡" onInput=${e=>setName(e.target.value)} /></label>
      <p class="map-help">Select、Start 和四个摇杆轴必须设置。其他键可以跳过；未设置的键不会触发对应动作。保存后先松开全部按键、摇杆回中，再恢复控制。建议随后重新测一次手柄急停。</p>
      ${view.required_missing?.length?html`<p class="map-help">还需设置：${view.required_missing.map(r=>NAMES[r]).join('、')}</p>`:null}
      <div class="map-actions"><button type="button" class="map-button primary" data-map-save disabled=${busy||!!capture||!!view.required_missing?.length||!name.trim()}
        onClick=${()=>{setAutomatic(false);call('save',{name})}}>保存并应用到这个手柄</button>
        <button class="map-button" type="button" data-map-cancel disabled=${busy} onClick=${()=>{setAutomatic(false);call('cancel')}}>取消，保留原映射</button>
        <button class="map-text-button" type="button" data-map-reset disabled=${busy} onClick=${()=>setReset(true)}>恢复默认</button></div>
      ${reset?html`<div class="map-reset"><p>删除这个手柄的自定义映射，恢复默认识别？</p><button class="map-button" type="button" data-map-reset-confirm disabled=${busy}
        onClick=${()=>{setAutomatic(false);setReset(false);call('reset')}}>确认恢复默认</button><button class="map-button" type="button" onClick=${()=>setReset(false)}>保留配置</button></div>`:null}
    </footer>`:null}
  </section>`;
}
