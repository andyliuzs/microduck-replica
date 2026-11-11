import { html, useEffect, useRef, useState } from './vendor/preact-htm.module.js';
import { audioLabel, rhythmLabel } from './audio-ui-state.js';

export function AudioInteraction({ pad, link, activity, dialogue }) {
  const status = pad?.audio;
  const [active, setActive] = useState(activity.active);
  const [pending, setPending] = useState(false);
  const [error, setError] = useState(null);
  const alive = useRef(false), busy = useRef(false);
  useEffect(() => {
    alive.current = true;
    const off = activity.subscribe(({active:value}) => setActive(value));
    return () => { alive.current = false; off(); };
  }, [activity]);
  const change = async values => {
    if (busy.current || !activity.active || link.status !== 'open') return;
    busy.current = true; setPending(true); setError(null);
    try {
      const response = await link.cmd('pad.op', {op:'audio', ...values}, 2500);
      if (alive.current && !response?.ok) setError(response?.reason || response?.error || '语音开关没有完成');
    } catch (err) {
      if (alive.current) setError(err?.message || '语音连接中断');
    } finally {
      busy.current = false;
      if (alive.current) setPending(false);
    }
  };
  const ready = active && link.status === 'open' && !pending;
  const dlg = dialogue || {};
  const dlgOn = !!status?.dialogue;
  const human = dlg.reply_mode === 'human';
  return html`<section id="audio-interaction" class="pd-motion" aria-label="语音与音乐互动">
    <div class="motion-heading"><h4>语音与音乐互动</h4>
      <span class="motion-state" role="status" data-audio-listening=${!!status?.listening}>${audioLabel(status)}</span>
    </div>
    <div class="motion-toolbar">
      <a class="btn-light" href="#/settings" data-ai-link>配置 AI（文字 / 实时语音）</a>
      <button type="button" class=${status?.listening ? 'motion-stop' : 'btn-primary'} data-audio="listening"
        disabled=${!ready || !status?.available} onClick=${() => change({listening:!status?.listening})}>
        ${status?.listening ? '关闭监听' : '开启监听'}</button>
      <button type="button" class="btn-light" data-audio="music" disabled=${!ready || !status?.available || dlgOn}
        onClick=${() => change({music:!status?.music})}>${status?.music ? '退出音乐模式' : '听音乐'}</button>
    </div>
    ${error || status?.error ? html`<p class="motion-error" role="alert">${error || status.error}</p>` : null}
    ${!status?.available ? html`<p class="pd-small-p">${status?.why || '等待语音服务连接'}</p>` : null}
    <div class="pd-sec-h" style="margin-top:14px">AI 对话（豆包实时语音）</div>
    <div class="motion-toolbar">
      <button type="button" class=${dlgOn ? 'motion-stop' : 'btn-primary'} data-audio="dialogue"
        disabled=${!ready || !status?.available || !dlg.configured} onClick=${() => change({dialogue:!dlgOn})}>
        ${dlgOn ? '结束对话' : '开始对话'}</button>
      <button type="button" class="btn-light" data-audio="reply_mode" disabled=${!ready || !dlgOn}
        onClick=${() => change({reply_mode: human ? 'quack' : 'human'})}>
        回答方式：${human ? '人声' : '鸭叫'}（点我切换）</button>
    </div>
    ${!dlg.configured ? html`<p class="pd-small-p">还没配好豆包实时语音：到「配置 AI」里新建连接，选提供商「豆包·实时语音」，填 API Key 并设为当前。</p>` : null}
    ${dlgOn && !dlg.session ? html`<p class="pd-small-p" role="status">正在接通豆包实时语音…</p>` : null}
    ${dlg.error ? html`<p class="motion-error" role="alert">${dlg.error}</p>` : null}
    ${(dlg.transcript || []).length ? html`<div aria-live="polite" data-dialogue-transcript style="max-height:180px;overflow:auto">
      ${dlg.transcript.map((m,i) => html`<p key=${i} class="pd-small-p" style="margin:4px 0"><b>${m.role === 'user' ? '你' : '鸭子'}</b>：${m.text}</p>`)}
    </div>` : null}
    ${dlgOn ? html`<p class="pd-small-p motion-note">对话开着：按 R3 或点「结束对话」关闭。鸭叫模式下回答只显示文字并配叫声；
      说「说人话」或点上面的切换按钮改成人声。空闲约 5 分钟自动结束。</p>` : null}
    ${status?.listening && status?.music ? html`<p class="pd-small-p" data-audio-rhythm>${rhythmLabel(status.rhythm)}</p>
      <p class="pd-small-p">手机或音箱在旁边放歌，可以问“感觉怎么样”“喜欢这种歌吗”。
      叫声按近期节奏感觉变化；低置信度时会用询问声回应。音乐模式暂不执行坐站口令或复读整首歌。</p>` : null}
    <p class="pd-small-p motion-note">R3 按一下开启并短叫一声，再按一下关闭；提示声后稍停再说话。
      日常口令是“坐下”“站起来”，执行后用叫声确认，普通话语不会原样播放。录音复读单独保留，专门按键以后再设。
      AI 对话开着时不执行本地坐站口令，由 AI 决定动作。</p>
  </section>`;
}
