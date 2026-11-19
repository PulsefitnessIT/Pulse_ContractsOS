/* Synthetic contract setup UI assertions: no private data or browser dependency. */
const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const read=name=>fs.readFileSync(path.join(__dirname,'../app/static',name),'utf8');

test('Settings has one actual setup destination, not links to old admin screens',()=>{
 const settings=read('settings-menu.js');
 const html=read('index.html');
 assert.match(settings,/setView\('setup'\)/);
 assert.doesNotMatch(settings,/setView\('quoting'\)/);
 assert.doesNotMatch(settings,/setView\('source_audit'\)/);
 assert.doesNotMatch(settings,/setView\('master_sources'\)/);
 assert.ok(html.includes('id="pulseMenuAdvanced"'));
 assert.ok(html.includes('id="pulseMenuSignOut"'));
 assert.ok(html.includes('/static/setup-centre.js?'));
 assert.ok(html.includes('/static/setup-centre.css?'));
 assert.ok(!html.includes('id="pulseMenuSourceAudit"'));
});

test('Administrator initial login opens wizard once and stores first visit on server',()=>{
 const script=read('settings-menu.js');
 assert.match(script,/session\.role==='Admin'/);
 assert.match(script,/status\.first_login_wizard/);
 assert.match(script,/\/api\/admin\/setup\/progress/);
 assert.match(script,/JSON\.stringify\(\{action:'start'\}\)/);
 assert.match(script,/await api\('\/api\/pilot\/logout'/);
 assert.doesNotMatch(script,/localStorage|sessionStorage/);
});

test('Setup is guided with explicit customer-issue separation',()=>{
 const script=read('setup-centre.js');
 for(const name of ['Maintenance contracts','Equipment prices','Company details','Agreement terms',
                     'Maintenance rates','Finish setup']){
   assert.ok(script.includes(name),name);
 }
 assert.match(script,/customer_quote_ready/);
 assert.match(script,/core_setup_ready/);
 assert.match(script,/Continue with internal drafts/);
 assert.match(script,/Commercial\/IT/);
 assert.doesNotMatch(script,/V10/i);
 assert.doesNotMatch(script,/setView\('source_audit'\)/);
});

test('All essential setup uploads call existing protected preview and approval routes',()=>{
 const script=read('setup-centre.js');
 for(const api of [
   '/api/quoting/price-book/preview','/api/quoting/price-book/activate',
   '/api/quoting/commercial-setup/issuer','/api/quoting/commercial-setup/terms',
   '/api/quoting/commercial-setup/tariff','/api/quoting/commercial-setup/issuance'
 ])assert.ok(script.includes(api),api);
 assert.match(script,/confirm_approved_current_terms/);
 assert.match(script,/confirm_zero_and_held_prices/);
 assert.match(script,/confirm_customer_quote_acceptance_tests/);
});

test('Setup centre has responsive controls without horizontal tables',()=>{
 const css=read('setup-centre.css');
 const script=read('setup-centre.js');
 assert.match(css,/@media\(max-width:1030px\)/);
 assert.match(css,/@media\(max-width:600px\)/);
 assert.match(css,/setup-form-grid/);
 assert.doesNotMatch(script,/<table/i);
 assert.doesNotMatch(css,/overflow-x:auto/);
});

test('Daily SmartQuote screen does not expose historical pricing admin panels',()=>{
 const quote=read('quoting-workspace.js');
 const brand=read('coordinator-ui.css');
 assert.match(brand,/\.quote-admin-section\{display:none!important\}/);
 assert.match(quote,/quote-admin-section/);
});
