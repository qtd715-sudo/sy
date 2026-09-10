// Headless Chrome screenshot via DevTools Protocol with exact device metrics.
// usage: node cdp_shot.mjs <url> <cssW> <cssH> <dpr> <out.png> [--css <file>] [--wait <ms>] [--mobile 0|1] [--metrics]
// prints one JSON line: {"out":..., "scrollWidth":..., "clientWidth":..., "scrollHeight":...}
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';

const CHROME = process.env.CHROME || 'C:/Program Files/Google/Chrome/Application/chrome.exe';
const argv = process.argv.slice(2);
const [url, cssW, cssH, dpr, out] = argv;
const opt = (name, def) => { const i = argv.indexOf(name); return i >= 0 ? argv[i + 1] : def; };
const cssFile = opt('--css', null);
const waitMs = parseInt(opt('--wait', '1200'), 10);
const mobile = opt('--mobile', '1') === '1';
const maxTotalMs = parseInt(opt('--max', '60000'), 10);

const profile = fs.mkdtempSync(path.join(os.tmpdir(), 'cdp-prof-'));
const chrome = spawn(CHROME, [
  '--headless=new', '--disable-gpu', '--hide-scrollbars', '--no-first-run', '--no-default-browser-check',
  '--disable-extensions', '--mute-audio', '--disk-cache-size=1', '--media-cache-size=1',
  '--disable-features=IsolateOrigins,site-per-process',
  `--user-data-dir=${profile}`, '--remote-debugging-port=0', 'about:blank',
], { stdio: ['ignore', 'ignore', 'pipe'] });

const wsUrl = await new Promise((resolve, reject) => {
  let buf = '';
  const t = setTimeout(() => reject(new Error('chrome did not start: ' + buf)), 30000);
  chrome.stderr.on('data', (d) => {
    buf += d.toString();
    const m = buf.match(/DevTools listening on (ws:\/\/\S+)/);
    if (m) { clearTimeout(t); resolve(m[1]); }
  });
});

const ws = new WebSocket(wsUrl);
await new Promise((res, rej) => { ws.onopen = res; ws.onerror = rej; });

let nextId = 1;
const pending = new Map();
const listeners = [];
ws.onmessage = (ev) => {
  const msg = JSON.parse(ev.data);
  if (msg.id && pending.has(msg.id)) {
    const { resolve, reject } = pending.get(msg.id); pending.delete(msg.id);
    if (msg.error) reject(new Error(JSON.stringify(msg.error))); else resolve(msg.result);
  } else if (msg.method) {
    for (const l of listeners) l(msg);
  }
};
const send = (method, params = {}, sessionId) => new Promise((resolve, reject) => {
  const id = nextId++;
  pending.set(id, { resolve, reject });
  ws.send(JSON.stringify({ id, method, params, ...(sessionId ? { sessionId } : {}) }));
});

const { targetId } = await send('Target.createTarget', { url: 'about:blank' });
const { sessionId } = await send('Target.attachToTarget', { targetId, flatten: true });

await send('Page.enable', {}, sessionId);
await send('Network.enable', {}, sessionId);
await send('Runtime.enable', {}, sessionId);
await send('Emulation.setDeviceMetricsOverride', {
  width: parseInt(cssW, 10), height: parseInt(cssH, 10), deviceScaleFactor: parseFloat(dpr), mobile,
}, sessionId);
if (mobile) {
  await send('Emulation.setTouchEmulationEnabled', { enabled: true }, sessionId);
}

// network idle tracking
let inflight = 0; let lastActivity = Date.now(); let loaded = false;
listeners.push((msg) => {
  if (msg.sessionId !== sessionId) return;
  if (msg.method === 'Network.requestWillBeSent') { inflight++; lastActivity = Date.now(); }
  else if (msg.method === 'Network.loadingFinished' || msg.method === 'Network.loadingFailed') { inflight = Math.max(0, inflight - 1); lastActivity = Date.now(); }
  else if (msg.method === 'Page.loadEventFired') { loaded = true; }
});

const t0 = Date.now();
await send('Page.navigate', { url }, sessionId);
// wait: load event + network idle (no inflight for `waitMs`) or max
while (Date.now() - t0 < maxTotalMs) {
  await new Promise(r => setTimeout(r, 150));
  if (loaded && inflight === 0 && Date.now() - lastActivity >= waitMs) break;
}
// let fonts/layout settle
await new Promise(r => setTimeout(r, 400));

if (cssFile) {
  const css = fs.readFileSync(cssFile, 'utf8');
  await send('Runtime.evaluate', {
    expression: `(() => { const s = document.createElement('style'); s.id='__inject'; s.textContent = ${JSON.stringify(css)}; document.head.appendChild(s); return true; })()`,
  }, sessionId);
  await new Promise(r => setTimeout(r, 300));
}

const m = await send('Runtime.evaluate', {
  expression: `JSON.stringify({scrollWidth: document.documentElement.scrollWidth, clientWidth: document.documentElement.clientWidth, scrollHeight: document.documentElement.scrollHeight, title: document.title})`,
  returnByValue: true,
}, sessionId);

const shot = await send('Page.captureScreenshot', { format: 'png', captureBeyondViewport: false }, sessionId);
fs.mkdirSync(path.dirname(path.resolve(out)), { recursive: true });
fs.writeFileSync(out, Buffer.from(shot.data, 'base64'));

const metrics = JSON.parse(m.result.value);
console.log(JSON.stringify({ out, elapsedMs: Date.now() - t0, ...metrics }));

try { await send('Browser.close'); } catch {}
ws.close();
chrome.kill();
setTimeout(() => { try { fs.rmSync(profile, { recursive: true, force: true }); } catch {} process.exit(0); }, 300);
