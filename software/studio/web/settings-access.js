import { html, useEffect, useRef, useState } from './vendor/preact-htm.module.js';
import { TwoStep } from './confirm.js';

export function AiSshEntry() {
  const go = e => {
    if (location.hash !== '#/settings/ssh') return;
    e.preventDefault();
    const section = document.getElementById('ssh-guide');
    section?.scrollIntoView({ block: 'start' });
    section?.focus({ preventScroll: true });
  };
  return html`<aside class="board ai-ssh-entry" aria-label="AI 助手连接指引">
    <div><b>需要 AI 帮你调试？</b><p>不用接显示器，在网页设好 SSH，就能让电脑上的 AI 编程助手连接主板。</p></div>
    <a class="access-button primary" href="#/settings/ssh" onClick=${go}>让 AI 连接鸭子（SSH）<span aria-hidden="true"> →</span></a>
  </aside>`;
}

function StepTitle({ number, title, state, titleId }) {
  return html`<div class="access-step-title"><h3 id=${titleId}><span class="access-step-number" aria-hidden="true">${number}</span>${title}</h3>
    <span class=${'access-state' + (state === '已设置' || state === '可连接' ? ' done' : '')} data-access-state>${state}</span></div>`;
}

function WebPassword({ api, hasPassword, onSaved, refreshSession }) {
  const [pw, setPw] = useState(''), [again, setAgain] = useState('');
  const [busy, setBusy] = useState(false), [msg, setMsg] = useState(null), [err, setErr] = useState(null);
  const submit = async e => {
    e.preventDefault(); setErr(null); setMsg(null);
    if (pw.length < 6) { setErr('网页登录密码至少 6 位'); return; }
    if (pw !== again) { setErr('两次输入不一样，请确认网页登录密码'); return; }
    setBusy(true);
    try {
      const r = await api('/api/password', { action: 'set', password: pw, confirm: again });
      if (!r.ok) { setErr(r.error || '网页密码没有保存，请重试'); return; }
      setPw(''); setAgain('');
      try { await refreshSession(); }
      catch { setMsg('网页登录密码已保存。请刷新页面后继续设置 SSH。'); return; }
      onSaved(); setMsg('网页登录密码已保存，这台浏览器仍保持登录。可以继续第 2 步。');
    } catch { setErr('连不上鸭子，检查网络后再试'); }
    finally { setBusy(false); }
  };
  const clear = async () => {
    setErr(null); setMsg(null);
    try {
      const r = await api('/api/password', { action: 'clear' });
      if (!r.ok) { setErr(r.error || '网页登录密码没有清掉'); return; }
      location.reload();
    } catch { setErr('连不上鸭子，检查网络后再试'); }
  };
  return html`<section class="board access-step password-settings" aria-labelledby="web-password-title">
    <${StepTitle} number="1" title="网页登录密码" titleId="web-password-title" state=${hasPassword == null ? '读取中' : hasPassword ? '已设置' : '待设置'} />
    <p class="access-description">保护控制网页：打开网页、控制鸭子和修改设置时使用。先保护网页，再允许从网页开启 SSH。</p>
    ${hasPassword == null ? html`<p role="status">正在读取登录状态…</p>` : html`
      <details class="access-edit" open=${!hasPassword}>
        <summary>${hasPassword ? '已设好，需要时再修改' : '设置网页登录密码'}</summary>
        <form onSubmit=${submit}>
          <p class="access-description">至少 6 位。${hasPassword ? '修改后，其他浏览器需要重新登录，这台保持登录。' : ''}</p>
          <label>${hasPassword ? '新的网页登录密码' : '网页登录密码'}
            <input type="password" name="password" autocomplete="new-password" value=${pw} required minLength="6"
              onInput=${e => setPw(e.target.value)} /></label>
          <label>确认网页登录密码
            <input type="password" name="confirm" autocomplete="new-password" value=${again} required minLength="6"
              aria-describedby="web-confirm-help" onInput=${e => setAgain(e.target.value)} /></label>
          <p class="access-help" id="web-confirm-help">再输入同一个密码，防止输错；不是再设一个密码。正常登录只输入一次。</p>
          <div class="access-actions"><button class="access-button primary" type="submit" disabled=${busy || !pw || !again}>
            ${busy ? '保存中…' : hasPassword ? '修改网页登录密码' : '保存网页登录密码'}</button>
            ${hasPassword ? html`<${TwoStep} label="清掉网页登录密码" ask="真的清掉？" onConfirm=${clear} />` : null}</div>
        </form>
      </details>`}
    ${err ? html`<p role="alert" class="access-error">${err}</p>` : null}
    ${msg ? html`<p role="status" class="access-help">${msg}</p>` : null}
  </section>`;
}

// Only address/account fields enter the note. Password values never reach this function.
export function sshConnection(ssh, net, hostname) {
  const hostOk = value => typeof value === 'string' && value.length <= 253 &&
    (/^[a-z0-9](?:[a-z0-9.-]*[a-z0-9])?$/i.test(value) || /^\[?[a-f0-9]*:[a-f0-9:]+\]?$/i.test(value));
  const candidates = [net?.known ? net.ip_now : null, net?.known ? net.ip4 : null, hostname];
  const host = candidates.find(hostOk);
  const user = ssh?.user || 'radxa';
  if (!host || !/^[a-z_][a-z0-9_-]*$/i.test(user)) return null;
  const target = host.replace(/^\[|\]$/g, '');
  const cmd = `ssh ${user}@${target}`;
  const method = ssh?.password_login ? 'SSH 系统登录密码（由我在终端提示时输入）' : '这台电脑上已登记公钥对应的 SSH 私钥';
  return { host: target, user, cmd, note: `请通过 SSH 连接我的 Microduck 主板，先只读检查连接和服务状态。\n主板地址：${target}\n用户名：${user}\nSSH 端口：22\n登录命令：${cmd}\n认证方式：${method}\n电脑需能访问这个主板地址；网页登录密码用于控制网页，SSH 登录使用系统密码或已登记的钥匙。` };
}

function SshSettings({ api, hasPassword, net }) {
  const [ssh, setSsh] = useState(null), [loading, setLoading] = useState(true), [loadErr, setLoadErr] = useState(null);
  const [pw, setPw] = useState(''), [again, setAgain] = useState(''), [key, setKey] = useState('');
  const [busy, setBusy] = useState(false), [msg, setMsg] = useState(null), [err, setErr] = useState(null);
  const [copyMsg, setCopyMsg] = useState(null);
  const [fallback, setFallback] = useState(null), fallbackRef = useRef(null), alive = useRef(true);
  const load = async () => {
    setLoading(true); setSsh(null); setFallback(null); setCopyMsg(null);
    try {
      const r = await api('/api/ssh', { action: 'status' }, 15000);
      if (!alive.current) return;
      if (r.ok) { setSsh(r.ssh); setLoadErr(null); }
      else setLoadErr(r.error || '读不到 SSH 状态，稍后重试');
    } catch { if (alive.current) setLoadErr('连不上鸭子，检查网络后重试'); }
    finally { if (alive.current) setLoading(false); }
  };
  useEffect(() => { alive.current = true; load(); return () => { alive.current = false; }; }, []);
  useEffect(() => { if (fallbackRef.current) { fallbackRef.current.focus(); fallbackRef.current.select(); } }, [fallback]);
  const on = ssh?.password_login === true, keys = ssh?.key_list || [];
  const connection = sshConnection(ssh, net, location.hostname);
  const ready = !loading && ssh?.ssh_active === true && (on || keys.length > 0) && !!connection;
  useEffect(() => { setFallback(null); setCopyMsg(null); }, [ready, connection?.host, connection?.user, on, keys.length]);
  const call = async (body, okText) => {
    setErr(null); setMsg(null); setBusy(true); setFallback(null); setCopyMsg(null);
    try {
      const r = await api('/api/ssh', body, 60000);
      if (!alive.current) return null;
      if (!r.ok) {
        setErr(r.status === 401 ? '登录过期了，刷新页面重新登录' : r.error || '没有完成，请重试');
        await load(); return null;
      }
      if (r.ssh) setSsh(r.ssh);
      setMsg(typeof okText === 'function' ? okText(r) : okText); return r;
    } catch { if (alive.current) { setSsh(null); setErr('连不上鸭子，检查网络后点击“刷新 SSH 状态”'); } return null; }
    finally { if (alive.current) setBusy(false); }
  };
  const submitPw = async e => {
    e.preventDefault(); setErr(null); setMsg(null);
    if (pw.length < 8 || pw.length > 64) { setErr('SSH 系统登录密码要 8–64 位'); return; }
    if (pw !== again) { setErr('两次输入不一样，请确认 SSH 系统登录密码'); return; }
    const r = await call({ action: 'on', password: pw, confirm: again }, on ? 'SSH 系统登录密码改好了。' : 'SSH 密码登录已开启，连接说明见第 3 步。');
    if (r) { setPw(''); setAgain(''); }
  };
  const submitKey = async e => {
    e.preventDefault();
    const r = await call({ action: 'add_key', key }, x => x.added ? '钥匙登记好了，用这台电脑连接。' : '这把钥匙本来就登记过了。');
    if (r) setKey('');
  };
  const copy = async value => {
    setCopyMsg(null); setFallback(null);
    try { await navigator.clipboard.writeText(value); if (alive.current) setCopyMsg('已复制，可以粘贴给电脑上的 AI 助手。'); }
    catch { if (alive.current) { setFallback(value); setCopyMsg('浏览器未允许自动复制，请复制下面已选中的文字。'); } }
  };
  const state = loading ? '正在读…' : !ssh ? loadErr || '读不到 SSH 状态'
    : `${on ? '密码登录开着' : ssh.password_login === false ? '只认钥匙（密码登录关着）' : '密码登录开没开读不到'}，${keys.length ? `登记了 ${keys.length} 把钥匙` : '一把钥匙都没登记'}${ssh.ssh_active === false ? '；ssh 服务没在跑' : ssh.ssh_active == null ? '；SSH 服务状态读不到' : ''}`;
  return html`<div class="ssh-settings">
    <section class="board access-step" aria-labelledby="ssh-step-title">
      <${StepTitle} number="2" title="SSH 系统登录密码" titleId="ssh-step-title" state=${loading ? '读取中' : ready ? '可连接' : '待配置'} />
      <p class="access-description">SSH 远程登录供电脑终端或 AI 编程助手进入主板系统，查看日志、修改程序。日常使用网页控制鸭子，可以跳过这一步。</p>
      <p class="access-help">出厂只认钥匙、不认密码，也没有默认密码；你可以自己设置系统密码，或使用下面的公钥登录。</p>
      <div class="access-status-row"><p class="ssh-now" role="status">现在：${state}</p>
        <button class="access-button" type="button" data-ssh-refresh disabled=${loading || busy} onClick=${load}>刷新 SSH 状态</button></div>
      ${!hasPassword ? html`<p class="ssh-need-web-pw access-notice">请先完成第 1 步，设置网页登录密码，再开启 SSH 或登记钥匙。这样只有登录网页的人能修改远程登录设置。</p>` : null}
      ${err ? html`<p role="alert" class="access-error">${err}</p>` : null}
      ${msg ? html`<p role="status" class="ssh-msg access-help">${msg}</p>` : null}
      <details class="access-edit ssh-pw-edit" open=${!on && keys.length === 0}>
        <summary>${on ? '密码登录已开启，需要时修改密码' : keys.length ? '已有公钥登录，按需设置密码登录' : '设置 SSH 系统登录密码'}</summary>
        <form class="ssh-pw" onSubmit=${submitPw}>
          <p class="access-help">8–64 位，不能是 microduck。用于主板的 ${ssh?.user || 'radxa'} 系统账号，部分 sudo 管理操作也会使用它。</p>
          ${hasPassword ? html`<label>${on ? '新的 SSH 系统登录密码' : 'SSH 系统登录密码'}
            <input type="password" name="ssh-password" autocomplete="new-password" value=${pw} required minLength="8" maxLength="64" onInput=${e => setPw(e.target.value)} /></label>
            <label>确认 SSH 系统登录密码
              <input type="password" name="ssh-confirm" autocomplete="new-password" value=${again} required minLength="8" maxLength="64" aria-describedby="ssh-confirm-help" onInput=${e => setAgain(e.target.value)} /></label>` : null}
          <p class="access-help" id="ssh-confirm-help">再输入同一个 SSH 密码，防止输错；正常登录只输入一次。它与网页密码独立保存，修改其中一个不会同步修改另一个。</p>
          <div class="access-actions"><button type="submit" class="access-button primary ssh-on" disabled=${busy || loading || !hasPassword || !ssh || !pw || !again}>
            ${busy ? '正在保存…' : on ? '修改 SSH 系统登录密码' : '保存密码并开启 SSH'}</button>
            ${on ? html`<${TwoStep} label="关掉 SSH 密码登录" ask="真的关掉？" onConfirm=${() => call({ action: 'off' }, 'SSH 密码登录关掉了，只认钥匙。')} />` : null}</div>
        </form>
      </details>
      <details class="access-edit ssh-key-options"><summary>已有 SSH 公钥？使用公钥登录（可选）</summary>
        <form class="ssh-key" onSubmit=${submitKey}>
          <p class="access-help">把这台电脑的 SSH 公钥（.pub 文件）贴到下面。使用公钥时不必开启密码登录。</p>
          <details class="access-key-help"><summary>还没有公钥，怎么生成？</summary>
            <p class="access-help">在电脑终端运行 <code>ssh-keygen -t ed25519</code>，按提示生成一把新钥匙；已有钥匙时可直接使用，无需覆盖。</p>
            <p class="access-help">Windows PowerShell 查看公钥：<code>type $env:USERPROFILE\\.ssh\\id_ed25519.pub</code>；Mac / Linux：<code>cat ~/.ssh/id_ed25519.pub</code>。只贴公钥，不要贴私钥。</p></details>
          ${keys.length ? html`<ul class="ssh-keys">${keys.map(k => html`<li key=${k.fp}><span>${k.comment || '（没注释）'} <code>${k.type} ${k.fp.slice(0, 19)}…</code></span>
            ${hasPassword ? html`<${TwoStep} label="删掉" ask="真的删掉这把？" onConfirm=${() => call({ action: 'remove_key', fp: k.fp }, '这把钥匙删掉了。')} />` : null}</li>`)}</ul>` : null}
          ${hasPassword ? html`<label>电脑的 SSH 公钥<textarea name="ssh-key" rows="3" value=${key} placeholder="ssh-ed25519 AAAA… 你的电脑名" onInput=${e => setKey(e.target.value)} /></label>` : null}
          <button type="submit" class="access-button ssh-addkey" disabled=${busy || loading || !hasPassword || !key.trim()}>登记这把钥匙</button>
        </form>
      </details>
    </section>
    <section class="board access-step access-connection" aria-labelledby="connection-step-title">
      <${StepTitle} number="3" title="把连接说明交给 AI 助手" titleId="connection-step-title" state=${ready ? '可连接' : '等待第 2 步'} />
      <p class="access-description">在能访问鸭子的电脑上使用 AI 编程助手（如 Codex），把下面的连接说明粘贴给它。SSH 密码在终端询问时由你输入。</p>
      ${ready ? html`<div data-access-connection>
        <dl class="access-fields"><div><dt>主板地址</dt><dd>${connection.host}</dd></div><div><dt>用户名</dt><dd>${connection.user}</dd></div><div><dt>SSH 端口</dt><dd>22</dd></div></dl>
        <code class="ssh-cmd access-command">${connection.cmd}</code>
        <div class="access-actions"><button class="access-button primary" type="button" data-copy-ai onClick=${() => copy(connection.note)}>复制给 AI 的连接说明</button>
          <button class="access-button" type="button" onClick=${() => copy(connection.cmd)}>只复制 SSH 命令</button></div>
        <p class="access-help">连接说明只包含地址、账号和连接方式。SSH 已开启不代表电脑已经连上，请让 AI 先检查连接。</p>
        <details class="access-edit"><summary>自己用终端连接</summary><p class="access-help">Windows 打开 PowerShell，Mac / Linux 打开终端，运行上面的命令。首次连接会询问主机指纹，核对后确认；输入系统密码时终端不会显示字符，输完按回车。</p></details>
      </div>` : html`<p class="access-notice">${loading ? '正在检查 SSH 状态…' : ssh?.ssh_active === false ? 'SSH 服务没在运行，请确认主板服务状态后刷新。' : !ssh || ssh.ssh_active == null ? '还读不到 SSH 服务状态，请在第 2 步刷新重试。' : '完成第 2 步：开启密码登录，或登记这台电脑的 SSH 公钥。'}</p>`}
      ${ready && copyMsg ? html`<p role="status" class="access-copy-message access-help">${copyMsg}</p>` : null}
      ${ready && fallback ? html`<label class="access-copy-fallback">手动复制连接文字
        <textarea ref=${fallbackRef} data-copy-fallback readOnly rows="8" value=${fallback} /></label>` : null}
    </section>
  </div>`;
}

export function AccessGuide({ api, hasPassword, net, refreshSession }) {
  const [savedWeb, setSavedWeb] = useState(false);
  const webReady = hasPassword === true || savedWeb;
  return html`<section id="ssh-guide" class="access-guide" tabIndex="-1" aria-labelledby="access-guide-title">
    <header class="board access-intro"><span class="access-eyebrow">电脑 AI 助手 · 远程调试</span>
      <h2 id="access-guide-title">让 AI 连接鸭子（SSH）</h2>
      <p>不用接显示器。按下面 3 步配置，让电脑上的 AI 编程助手通过 SSH 连接主板。</p>
      <div class="access-password-map"><div><b>网页登录密码</b><span>进入浏览器控制页面</span></div><span aria-hidden="true">≠</span><div><b>SSH 系统登录密码</b><span>从电脑进入主板系统</span></div></div>
      <p class="access-help">两种密码独立管理。输入框里的“确认密码”只是把同一个密码再输一遍，防止输错；正常登录只输入一次。</p>
    </header>
    <${WebPassword} api=${api} hasPassword=${webReady ? true : hasPassword} onSaved=${() => setSavedWeb(true)} refreshSession=${refreshSession} />
    <${SshSettings} api=${api} hasPassword=${webReady} net=${net} />
  </section>`;
}
