/* Coordinator-first regression guards. These use only bundled public source. */
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const get=name=>fs.readFileSync(path.join(__dirname,'../app/static',name),'utf8');

test('UK dates convert ISO and Excel serials without touching other numbers',()=>{
  const source=get('app.js');
  const begin=source.indexOf('function isoDate(s)');
  const end=source.indexOf('function renewal(s)',begin);
  assert.ok(begin>=0&&end>begin);
  const ctx={Date,Number,String};
  vm.runInNewContext(source.slice(begin,end),ctx);
  assert.equal(ctx.formatDate('45799'),'21/05/2025');
  assert.equal(ctx.formatDate(45799),'21/05/2025');
  assert.equal(ctx.formatDate('2026-11-19'),'19/11/2026');
  assert.equal(ctx.formatDate('31/12/2026'),'31/12/2026');
  assert.equal(ctx.formatDate('100'),'100');
});
test('no new-contract register picker or automatic MOD selection',()=>{
  const js=get('app.js');
  assert.equal(js.includes('id="newSourceRegister"'),false);
  assert.ok(js.includes("source_register:editingNew ? 'Maintenance Database'"));
  assert.ok(js.includes('/agreement/preview.pdf'));
});
test('coordinator screens are not covered by technical source and V10 panels',()=>{
  const quote=get('quoting-workspace.js');
  for(const id of ['quoteV10SourcePanel','quoteCommercialSetupPanel',
    'quoteUnifiedBookPanel','quoteSageRefreshPanel','quoteGoLiveStatusPanel']){
    assert.ok(quote.includes('class="panel quote-admin-section" id="'+id+'"'));
  }
  const css=get('coordinator-ui.css');
  assert.ok(css.includes('.quote-admin-section{display:none!important}'));
  assert.ok(css.includes('.pulse-pro.pulse-advanced-settings .quote-admin-section:not([hidden])'));
});
test('responsive action centre has no editable horizontal table',()=>{
  const js=get('action-centre.js');
  assert.ok(js.includes('action-record-list'));
  assert.ok(js.includes('action-extra-fields'));
  assert.ok(!js.includes('<table class="data-table">'));
  assert.ok(!js.includes('scroll-table'));
});
test('top-right menu includes signout and admin-only pricing setup',()=>{
  const index=get('index.html');
  const menu=get('settings-menu.js');
  assert.ok(index.includes('id="pulseSettingsToggle"'));
  assert.ok(index.includes('id="pulseMenuSignOut"'));
  assert.ok(index.includes('data-admin-menu hidden'));
  assert.ok(menu.includes("session.role==='Admin'"));
  assert.ok(menu.includes("'/api/pilot/logout'"));
});
test('source records are displayed as cards and date-formatted',()=>{
  const script=get('master-source-registers.js');
  assert.ok(script.includes('source-row-list'));
  assert.ok(script.includes('formatDate(value)'));
  assert.ok(!script.includes("'<div class=\"scroll-table\"><table"));
});
