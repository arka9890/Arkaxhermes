#!/usr/bin/env node
/*
 * Audit UI Arkaxhermes tanpa browser: render semua layar dalam VM Node,
 * kumpulkan setiap data-act, lalu cocokkan dengan handler klik/change.
 *
 * Keluaran JSON ke stdout. Dipanggil scripts/audit.py; bisa juga dijalankan:
 *   node scripts/audit-ui.js
 */
'use strict';
const fs = require('fs');
const vm = require('vm');
const path = require('path');

const htmlPath = path.join(__dirname, '..', 'android', 'app', 'src', 'main', 'assets', 'www', 'index.html');
const html = fs.readFileSync(htmlPath, 'utf8');
const blocks = [...html.matchAll(/<script(?:\s[^>]*)?>([\s\S]*?)<\/script>/gi)];
if (!blocks.length) throw new Error('tidak ada blok <script> di index.html');
const js = blocks.map(b => b[1]).join('\n;\n');

const store = {}, listeners = {};
function elem(id) {
  return {
    id, innerHTML: '', textContent: '', value: '', checked: false,
    scrollTop: 0, scrollHeight: 1000,
    classList: { add() {}, remove() {}, toggle() {} },
    dataset: {}, tabIndex: 0,
    addEventListener() {}, getBoundingClientRect() { return { left: 0, top: 0, width: 900, height: 560 }; },
    insertAdjacentHTML() {}, focus() {}, setSelectionRange() {},
    setAttribute() {}, getAttribute() { return null; }, closest() { return null; },
    querySelectorAll() { return []; }, appendChild() {}, style: { setProperty() {} },
  };
}
const document = {
  documentElement: { setAttribute() {}, style: { setProperty() {} } },
  body: { insertAdjacentHTML() {} },
  getElementById(id) { return store[id] || (store[id] = elem(id)); },
  querySelector() { return null; },
  querySelectorAll() { return []; },
  addEventListener(ev, fn) { (listeners[ev] = listeners[ev] || []).push(fn); },
};
const localStorage = {
  _d: {}, getItem(k) { return this._d[k] || null; },
  setItem(k, v) { this._d[k] = String(v); }, removeItem(k) { delete this._d[k]; },
};
const window = { matchMedia: () => ({ matches: false }), ArkaxBridge: null };
const location = { hostname: 'example.com', protocol: 'https:', hash: '', port: '' };
const navigator = { clipboard: null };
const sandbox = {
  document, window, location, navigator, localStorage, console,
  matchMedia: () => ({ matches: false }),
  requestAnimationFrame: fn => setTimeout(fn, 0),
  setTimeout, clearTimeout, setInterval, clearInterval,
  fetch: () => Promise.reject(new Error('no network in demo')),
  TextDecoder, encodeURIComponent, decodeURIComponent, JSON, Promise, Date,
  Math, RegExp, Object, Array, String, Number, parseInt,
};
vm.createContext(sandbox);
vm.runInContext(js, sandbox, { filename: 'arkax-ui.js' });

const screens = JSON.parse(js.match(/var SCREENS = ([\s\S]*?);\nfunction screenById/)[1]);
const cliCatalog = JSON.parse(js.match(/var CLI_CATALOG = ([\s\S]*?);\nvar NAV/)[1]);

function click(act, val) {
  const t = {
    closest() { return this; },
    getAttribute(k) {
      if (k === 'data-act') return act;
      if (k === 'data-val') return val || '';
      return null;
    },
  };
  (listeners.click || []).forEach(fn => fn({ target: t, preventDefault() {} }));
}
function input(id, value) {
  const t = { id, value, type: 'text', getAttribute() { return null; }, closest() { return null; } };
  (listeners.input || []).forEach(fn => fn({ target: t, preventDefault() {} }));
}
function collectActs(html, set) {
  let m, re = /data-act="([^"]+)"/g;
  while ((m = re.exec(html))) set.add(m[1]);
  re = /data-act='([^']+)'/g;
  while ((m = re.exec(html))) set.add(m[1]);
}

// Handler klik saja (bukan case render switch).
const clickBlock = js.slice(
  js.indexOf("document.addEventListener('click'"),
  js.indexOf("document.addEventListener('input'")
);
const clickCases = new Set();
let m, re = /case\s+'([^']+)'\s*:/g;
while ((m = re.exec(clickBlock))) clickCases.add(m[1]);
clickCases.add('font'); // ditangani listener change, bukan klik

const renderedActs = new Set(), screenActs = {};
(async () => {
  await new Promise(r => setTimeout(r, 80));
  for (const s of screens) {
    click('nav', s.id);
    await new Promise(r => setTimeout(r, 4));
    const acts = new Set();
    collectActs(store.app.innerHTML, acts);
    collectActs(store.overlay.innerHTML, acts);
    screenActs[s.id] = [...acts].sort();
    acts.forEach(a => renderedActs.add(a));
    if (!store.app.innerHTML.includes('bottom-nav')) throw new Error('render gagal: ' + s.id);
  }
  // State tambahan: drawer, form, modal, instalasi, file actions, slash, pencarian.
  click('drawer'); collectActs(store.app.innerHTML, renderedActs);
  click('theme', 'dark'); click('theme', 'light');
  for (const k of ['skills', 'cron', 'mcp', 'hooks', 'batch', 'backup', 'logs', 'workspace', 'file']) {
    click('form', k); collectActs(store.overlay.innerHTML, renderedActs); click('modal-close');
  }
  click('form-key', 'OPENAI_API_KEY'); collectActs(store.overlay.innerHTML, renderedActs); click('modal-close');
  click('clear-data'); collectActs(store.overlay.innerHTML, renderedActs); click('modal-close');
  click('install'); click('install-start'); collectActs(store.overlay.innerHTML, renderedActs);
  click('install-close');
  click('nav', 'workspace'); click('file-menu', '/root/.hermes/MEMORY.md');
  collectActs(store.overlay.innerHTML, renderedActs); click('modal-close');
  click('nav', 'chat'); input('composer', '/'); collectActs(store.app.innerHTML, renderedActs);
  input('wsearch', 'skill'); collectActs(store.app.innerHTML, renderedActs);
  click('nav', 'cli'); input('cli-search', 'cron'); collectActs(store.app.innerHTML, renderedActs);

  const dead = [...renderedActs].filter(a => !clickCases.has(a));
  const unusedCases = [...clickCases].filter(a => !renderedActs.has(a));

  const pblock = js.match(/var P = \{([\s\S]*?)\n\};/)[1];
  const pKeys = new Set(); re = /([a-zA-Z0-9_-]+)\s*:\s*['"]/g;
  while ((m = re.exec(pblock))) pKeys.add(m[1]);
  const icons = new Set(); re = /icon\('([a-zA-Z0-9_-]+)'/g;
  while ((m = re.exec(js))) icons.add(m[1]);
  const missingIcons = [...icons].filter(i => !pKeys.has(i));

  process.stdout.write(JSON.stringify({
    screens: screens.map(s => s.id),
    screenCount: screens.length,
    cliCommandCount: cliCatalog.length,
    renderedActCount: renderedActs.size,
    clickCaseCount: clickCases.size,
    dead,
    unusedCases,
    iconCount: icons.size,
    pKeyCount: pKeys.size,
    missingIcons,
    screenActs,
  }, null, 2) + '\n');
  if (dead.length || missingIcons.length) process.exitCode = 2;
})().catch(e => { console.error('UI AUDIT ERROR:', e); process.exit(1); });
