import { mkdirSync, readFileSync, writeFileSync } from 'node:fs';
const arg = key => process.argv[process.argv.indexOf(`--${key}`) + 1];
const shots = arg('shots'); mkdirSync(shots, { recursive: true });
const page = await (await fetch(`http://127.0.0.1:${arg('cdp')}/json/new?about:blank`, { method: 'PUT' })).json();
const ws = new WebSocket(page.webSocketDebuggerUrl);
await new Promise(resolve => ws.addEventListener('open', resolve, { once: true }));
let seq = 0; const pending = new Map(), errors = [], report = { errors, layouts: [] };
const send = (method, params = {}) => new Promise((resolve, reject) => {
  const id = ++seq, timer = setTimeout(() => { pending.delete(id); reject(Error(`CDP timeout: ${method}`)); }, 15000);
  pending.set(id, m => { clearTimeout(timer); m.error ? reject(Error(JSON.stringify(m.error))) : resolve(m.result); });
  ws.send(JSON.stringify({ id, method, params }));
});
ws.addEventListener('message', event => {
  const m = JSON.parse(event.data);
  if (pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id); }
  if (m.method === 'Runtime.exceptionThrown') errors.push(m.params.exceptionDetails.exception?.description || m.params.exceptionDetails.text);
});
const js = async expression => {
  const r = await send('Runtime.evaluate', { expression, awaitPromise: true, returnByValue: true });
  if (r.exceptionDetails) throw Error(r.exceptionDetails.exception?.description || r.exceptionDetails.text);
  return r.result?.value;
};
const assert = (value, message) => { if (!value) throw Error(message); };
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
const wait = async (expr, label, timeout = 12000) => {
  const end = Date.now() + timeout;
  while (Date.now() < end) { if (await js(expr)) return; await sleep(80); }
  throw Error(`Timeout: ${label}\n${await js("document.querySelector('.access-guide')?.innerText || document.body.innerText.slice(0,1800)")}`);
};
const click = async selector => {
  await wait(`document.querySelector(${JSON.stringify(selector)}) && !document.querySelector(${JSON.stringify(selector)}).disabled`, selector);
  await js(`document.querySelector(${JSON.stringify(selector)}).click()`);
};
const fill = (selector, value) => js(`(() => { const el = document.querySelector(${JSON.stringify(selector)});
  el.value = ${JSON.stringify(value)}; el.dispatchEvent(new Event('input', { bubbles: true })); })()`);
const submit = selector => js(`document.querySelector(${JSON.stringify(selector)}).requestSubmit()`);
const control = changes => {
  const path = arg('control'), old = JSON.parse(readFileSync(path, 'utf8'));
  writeFileSync(path, JSON.stringify({ ...old, ...changes }));
};
const snapshot = async name => {
  const r = await send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: false });
  writeFileSync(`${shots}/${name}.png`, Buffer.from(r.data, 'base64'));
};
try {
  await send('Page.enable'); await send('Runtime.enable');
  await send('Emulation.setDeviceMetricsOverride', { width: 1440, height: 1000, deviceScaleFactor: 1, mobile: false });
  await send('Page.navigate', { url: `${arg('url')}#/` });
  await wait(`!!document.querySelector('.overview .ai-ssh-entry')`, 'overview AI SSH entry');
  assert(JSON.parse(readFileSync(arg('control'), 'utf8')).changes === 0, 'entry cannot open SSH');
  await click('.overview .ai-ssh-entry a');
  await wait(`location.hash === '#/settings/ssh' && !!document.querySelector('.access-guide')`, 'guide route');
  await wait(`document.querySelector('.ssh-now')?.innerText.includes('只认钥匙')`, 'SSH initial state');
  assert(await js(`!!document.querySelector('.nav a[href="#/settings"][aria-current="page"]')`), 'settings nav stays selected');
  await sleep(200);
  assert(await js(`document.querySelector('.access-guide').getBoundingClientRect().top >= 50 && document.querySelector('.access-guide').getBoundingClientRect().top < 180`), 'deep link scrolls below sticky header');
  report.entry_and_route = true;
  let text = await js(`document.querySelector('.access-guide').innerText`);
  for (const word of ['网页登录密码', 'SSH 系统登录密码', '确认密码', '独立', '正常登录']) assert(text.includes(word), `explains ${word}`);
  assert(await js(`document.querySelectorAll('.ssh-settings input[type=password]').length === 0`), 'SSH gated until web password');
  await snapshot('guide-before-setup-desktop');
  await fill('.password-settings input[name=password]', 'fixture-web-pass-A');
  await fill('.password-settings input[name=confirm]', 'different-web-pass');
  await submit('.password-settings form');
  await wait(`document.querySelector('.password-settings [role=alert]')?.innerText.includes('不一样')`, 'confirmation mismatch');
  assert(JSON.parse(readFileSync(arg('control'), 'utf8')).changes === 0, 'confirmation changes no SSH state');
  report.password_confirmation = true;
  await fill('.password-settings input[name=confirm]', 'fixture-web-pass-A');
  await submit('.password-settings form');
  await wait(`document.querySelector('.password-settings [data-access-state]')?.innerText === '已设置'`, 'web password saved');
  await wait(`!!document.querySelector('.ssh-settings input[name=ssh-password]')`, 'SSH next step ready');
  assert(await js(`!document.querySelector('.password-settings details').open`), 'completed web step collapsed');
  await fill('[name=ssh-password]', 'fixture-ssh-pass-B');
  await fill('[name=ssh-confirm]', 'fixture-ssh-pass-B');
  await submit('.ssh-pw');
  await wait(`document.querySelector('.ssh-now')?.innerText.includes('密码登录开着')`, 'SSH password on with refreshed CSRF');
  report.session_refreshed = report.ssh_enabled = true;
  assert(await js(`document.querySelector('[name=ssh-password]').value === ''`), 'SSH password input cleared');
  await wait(`!!document.querySelector('[data-access-connection]')`, 'connection instruction');
  await js(`window.__copied = []; Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText:async text => {window.__copied.push(text)}}});`);
  await click('[data-copy-ai]');
  const copied = await js(`window.__copied.at(-1)`);
  assert(copied.includes('radxa') && copied.includes('22') && copied.includes('ssh '), 'copy contains usable connection fields');
  assert(!copied.includes('fixture-web-pass-A') && !copied.includes('fixture-ssh-pass-B') && !copied.includes(':8000'), 'copy includes no secrets or web SSH port');
  report.copy_without_secrets = true;
  assert(await js(`document.querySelector('.access-connection [role=status]')?.innerText.includes('已复制')`), 'copy result next to copy button');
  await js(`Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText:async()=>{throw Error('denied')}}});`);
  await click('[data-copy-ai]');
  await wait(`!!document.querySelector('[data-copy-fallback]')`, 'HTTP/manual copy fallback');
  assert(await js(`document.querySelector('[data-copy-fallback]').value.includes('ssh ')`), 'fallback actual text');
  report.copy_fallback = true;
  for (const width of [1440, 390, 320]) {
    await send('Emulation.setDeviceMetricsOverride', { width, height: 1000, deviceScaleFactor: 1, mobile: width < 500 });
    await js(`document.querySelector('.access-guide').scrollIntoView({block:'start'})`); await sleep(120);
    assert(await js(`document.documentElement.scrollWidth <= innerWidth + 1`), `no overflow at ${width}`);
    await snapshot(`guide-ready-${width}`); report.layouts.push(width);
    await js(`document.querySelector('.access-connection').scrollIntoView({block:'center'})`); await sleep(100);
    await snapshot(`guide-connection-${width}`);
  }
  await send('Page.reload');
  await wait(`!!document.querySelector('[data-access-connection]')`, 'existing access after reload');
  assert(await js(`!document.querySelector('.ssh-pw-edit').open`), 'existing SSH does not force new password');
  report.existing_access = true;
  control({ unknown: true }); await click('[data-ssh-refresh]');
  await wait(`document.querySelector('.ssh-now')?.innerText.includes('读不到')`, 'unknown SSH readback');
  assert(await js(`!document.querySelector('[data-copy-ai]')`), 'unknown state cannot be labelled ready');
  control({ unknown: false, active: false }); await click('[data-ssh-refresh]');
  await wait(`document.querySelector('.ssh-now')?.innerText.includes('没在跑')`, 'inactive service');
  assert(await js(`!document.querySelector('[data-copy-ai]')`), 'inactive service cannot be ready');
  control({ active: true }); await click('[data-ssh-refresh]');
  await wait(`!!document.querySelector('[data-access-connection]')`, 'status retry restores access');
  await click('.ssh-pw-edit summary');
  await fill('[name=ssh-password]', 'fixture-ssh-pass-B'); await fill('[name=ssh-confirm]', 'fixture-ssh-pass-B');
  control({ fail: true }); await submit('.ssh-pw');
  await wait(`document.querySelector('.ssh-settings [role=alert]')?.innerText.includes('重载失败')`, 'operation error');
  control({ fail: false }); await submit('.ssh-pw');
  await wait(`document.querySelector('.ssh-msg')?.innerText.includes('改好了')`, 'retry operation succeeds');
  report.retry = true;
  await click('.ssh-key-options summary');
  await click('.access-key-help summary');
  const keyHelp = await js("document.querySelector('.access-key-help').innerText");
  assert(keyHelp.includes('USERPROFILE\\.ssh\\id_ed25519.pub'), 'PowerShell path preserves backslashes');
  const type = Buffer.from('ssh-ed25519'), size = Buffer.alloc(4); size.writeUInt32BE(type.length);
  const keysize = Buffer.alloc(4); keysize.writeUInt32BE(32);
  const publicKey = `ssh-ed25519 ${Buffer.concat([size, type, keysize, Buffer.alloc(32,1)]).toString('base64')} fixture@pc`;
  await fill('[name=ssh-key]', publicKey); await submit('.ssh-key');
  await wait(`document.querySelector('.ssh-keys')?.innerText.includes('fixture@pc')`, 'public key management remains available');
  report.keys_preserved = true;
  control({ enabled: false }); await click('[data-ssh-refresh]');
  await wait(`!!document.querySelector('[data-access-connection]') && document.querySelector('.ssh-now')?.innerText.includes('只认钥匙')`, 'key-only access remains usable');
  await js(`Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText:async text => {window.__keyNote=text}}});`);
  await click('[data-copy-ai]');
  assert(await js(`window.__keyNote.includes('对应的 SSH 私钥') && !document.querySelector('.ssh-pw-edit').open`), 'key-only users do not need new password');
  assert(errors.length === 0, `browser errors: ${errors.join('\n')}`);
  console.log(JSON.stringify(report, null, 2));
} finally { ws.close(); }
