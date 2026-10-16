// Builds src/i18n/zh.json from the prototype's UI dictionary (interface strings only, no data).
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
const src = fs.readFileSync(path.resolve('../i18n-zh.js'), 'utf8');
const ctx = { window: {} };
vm.runInNewContext(src, ctx);
const ui = ctx.window.LANTERN_I18N.zh.ui;
const extra = JSON.parse(fs.readFileSync('src/i18n/zh.extra.json', 'utf8'));
fs.writeFileSync('src/i18n/zh.json', JSON.stringify({ ...ui, ...extra }, null, 0));
console.log('zh.json:', Object.keys(ui).length, 'prototype +', Object.keys(extra).length, 'extra');
