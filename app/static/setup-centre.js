/* Pulse Fitness | Administrator Setup Centre.
   One guided, source-backed configuration experience, not links to legacy screens.
   All writes use existing protected API approval/validation; no localStorage.
*/
const SETUP_PAGES=[
  {id:'contracts',title:'Maintenance contracts',helper:'Check the approved Maintenance Master'},
  {id:'prices',title:'Equipment prices',helper:'Load the Unified Master Price List'},
  {id:'company',title:'Company details',helper:'Confirm the legal quotation issuer'},
  {id:'terms',title:'Agreement terms',helper:'Approve the maintenance terms PDF'},
  {id:'rates',title:'Maintenance rates',helper:'Approve service pricing separately'},
  {id:'review',title:'Finish setup',helper:'Review your readiness and next steps'}
];
let setupSelectedPage='contracts',setupLiveStatus=null,setupPendingPrices=null,setupActiveTariff=null;
let setupBusy=false;

async function setupCentrePage(){
  if(window.pulseAuthRole!=='Admin'){
    content.innerHTML='<div class="main-inner"><div class="notice warning">Only your Administrator can change setup and pricing approvals.</div></div>';
    return;
  }
  content.innerHTML='<div class="main-inner setup-centre">'+
    heading('Platform setup','One place to get Contracts OS and SmartQuote ready for your team.')+
    '<div id="setupWelcome" class="setup-intro" hidden></div>'+
    '<div id="setupSummary" aria-live="polite">Checking your setup…</div>'+
    '<div class="setup-layout"><nav class="setup-steps" id="setupSteps" aria-label="Setup steps"></nav>'+
    '<section class="setup-body card" id="setupPanel" aria-live="polite"></section></div>'+
    '</div>';
  await setupRefresh();
}

function setupApprovalFields(){
  return '<div class="setup-form-grid">'+
    '<label>Approval reference <input class="input" name="approval_reference" minlength="8" maxlength="250" '+
      'required placeholder="Approved decision / reference"></label>'+
    '<label>Reason or document evidence <input class="input" name="reason" minlength="12" maxlength="500" '+
      'required placeholder="What was checked and approved?"></label></div>';
}

function setupStepsHeader(){
  const n=SETUP_PAGES.findIndex(p=>p.id===setupSelectedPage);
  const step=SETUP_PAGES[n]||SETUP_PAGES[0];
  return '<div class="setup-section-top"><div class="setup-kicker">Step '+(n+1)+' of '+SETUP_PAGES.length+
    '</div><h2>'+esc(step.title)+'</h2><p>'+esc(step.helper)+
    '</p></div>';
}

function setupChecked(step){
  return Boolean((setupLiveStatus?.steps||[]).find(x=>x.id===step)?.ready);
}

function setupStatusPill(ready){
  return '<span class="setup-pill '+(ready?'is-ready':'is-pending')+'">'+
    (ready?'Ready':'Action needed')+'</span>';
}

function setupField(detail){
  return '<p class="setup-explainer">'+esc(detail||'')+'</p>';
}

async function setupRefresh(){
  const result=await api('/api/admin/setup/status');
  if(view!=='setup')return;
  setupLiveStatus=result;
  if(typeof window.updatePulseSettingsStatus==='function')window.updatePulseSettingsStatus(result);
  const ready=result.ready_count;
  const total=result.required_count;
  const progress=document.getElementById('setupSummary');
  progress.innerHTML='<div class="setup-summary-card">'+
    '<div><p class="setup-kicker">SETUP PROGRESS</p><h2>'+ready+' of '+total+' required checks ready</h2>'+
    '<p>'+(result.core_setup_ready?
      'Your required setup checks are complete. Customer PDF issue is a separate approval.':
      'Finish the remaining checks before customer quotations can be issued.')+
      '</p></div><div class="setup-meter" aria-label="'+ready+' of '+total+' complete">'+
      '<div style="width:'+Math.round(100*ready/Math.max(total,1))+'%"></div></div></div>';

  const welcome=document.getElementById('setupWelcome');
  if(window.pulseSetupFirstLogin){
    welcome.hidden=false;
    welcome.innerHTML='<strong>Welcome to SmartQuote setup.</strong> '+
      'We will check your existing information first. Anything already approved is recognised, '+
      'so there is no need to upload it again. You can save your progress and return later.';
  } else {
    welcome.hidden=true;
  }
  const links=document.getElementById('setupSteps');
  links.innerHTML=SETUP_PAGES.map((p,i)=>{
    const ready=(p.id==='review')?result.core_setup_ready:setupChecked(p.id);
    return '<button type="button" class="setup-step'+
      (setupSelectedPage===p.id?' is-selected':'')+
      '" data-setup-step="'+esc(p.id)+'" aria-current="'+
      (setupSelectedPage===p.id?'step':'false')+'">'+
      '<span class="setup-step-number">'+(ready?'✓':(i+1))+'</span>'+
      '<span><strong>'+esc(p.title)+'</strong><small>'+esc(p.helper)+'</small></span>'+
      '<span class="setup-step-status">'+(ready?'Ready':'Pending')+'</span></button>';
  }).join('');
  links.querySelectorAll('[data-setup-step]').forEach(b=>
    b.addEventListener('click',()=>setupSelect(b.dataset.setupStep)));
  await setupRenderSelected();
}

async function setupSelect(id){
  if(!SETUP_PAGES.some(x=>x.id===id))return;
  setupSelectedPage=id;
  if(view!=='setup')return;
  await setupRefresh();
}

function setupNav(){
  const i=SETUP_PAGES.findIndex(x=>x.id===setupSelectedPage);
  return '<div class="setup-navigation">'+
    (i>0?'<button type="button" class="button button-outline" id="setupBack">Previous</button>':'<span></span>')+
    (i<SETUP_PAGES.length-1?
      '<button type="button" class="button button-primary" id="setupNext">Next step</button>':
      '<button type="button" class="button button-outline" id="setupLater">Continue with internal drafts</button>')+
    '</div><p role="status" id="setupResponse" class="setup-message"></p>';
}

function setupError(error){
  const host=document.querySelector('#setupResponse');
  if(host)host.textContent='Unable to save: '+String(error.message||error);
}

function setupActionButton(button,task){
  if(setupBusy)return;
  setupBusy=true;button.disabled=true;
  Promise.resolve().then(task).catch(setupError).finally(()=>{setupBusy=false;button.disabled=false;});
}

async function setupRenderSelected(){
  const panel=document.getElementById('setupPanel');
  if(!panel)return;
  const current=setupLiveStatus||{};
  const records=current.steps?.find(x=>x.id===setupSelectedPage);
  const state=records?.detail||'';
  let body=setupStepsHeader();
  if(setupSelectedPage==='contracts'){
    body+=setupStatusPill(setupChecked('contracts'))+setupField(state)+
      '<div class="setup-info"><strong>What this checks</strong><p>Your approved Maintenance Master and '+
      'the stored customer agreements can be read on this PC. The existing Excel file is not overwritten.</p>'+
      '<p>Contract amounts and service history may still need review before reporting.</p></div>'+
      '<div class="setup-actions"><button type="button" class="button button-outline" id="setupShowContracts">View contracts</button>'+
      '<button type="button" class="button button-outline" id="setupShowImports">Review imports</button></div>';
    if(!setupChecked('contracts')&&(current.data_issues||[]).length){
      body+='<div class="setup-warning"><strong>Items to check</strong><ul>'+
        current.data_issues.slice(0,4).map(s=>'<li>'+esc(s)+'</li>').join('')+'</ul></div>';
    }
  } else if(setupSelectedPage==='prices'){
    body+=setupStatusPill(setupChecked('prices'))+setupField(state)+
      '<div class="setup-info"><strong>One equipment price list</strong>'+
      '<p>Upload a CSV of the Unified Master equipment prices. Matching product codes are updated; '+
      'other existing codes remain in place. This is separate from the Silver, Gold and Platinum maintenance rates.</p></div>'+
      '<form id="setupPriceUpload" class="setup-form">'+
        '<label>Select Unified Master price CSV <input type="file" name="file" accept=".csv,text/csv" required></label>'+
        '<button class="button button-primary" type="submit">Review prices before importing</button></form>'+
      (setupChecked('prices')?'<p><a href="/api/quoting/price-book/export.csv" download class="button button-outline">Download active Master price list</a></p>':'')+
      '<div id="setupPricePreview"></div>';
  } else if(setupSelectedPage==='company'){
    body+=setupStatusPill(setupChecked('company'))+setupField(state)+
      '<div class="setup-info">These details appear on authorised customer quotations. '+
      'Use the verified legal company name and registration details, not the gym site name.</div>'+
      (setupChecked('company')?'<p class="setup-explainer">Already verified. Only change these details if they are no longer correct.</p>':'')+
      '<details class="setup-approval-disclosure" '+(!setupChecked('company')?'open':'')+'>'+
      '<summary>'+ (setupChecked('company')?'Update verified company details':'Enter and verify company details')+'</summary>'+
      '<form id="setupCompanyForm" class="setup-form"><div class="setup-form-grid">'+
      '<label>Legal company name <input class="input" name="legal_name" required maxlength="120"></label>'+
      '<label>Company number <input class="input" name="company_number" required maxlength="30"></label>'+
      '<label>Registered office address <input class="input" name="registered_address" required maxlength="250"></label>'+
      '<label>Service email <input class="input" name="contact_email" type="email" required maxlength="250"></label>'+
      '<label>Telephone <input class="input" name="telephone" maxlength="40"></label>'+
      '<label>VAT number (if applicable) <input class="input" name="vat_number" maxlength="40"></label></div>'+
      setupApprovalFields()+
      '<label class="setup-check"><input type="checkbox" name="confirm_verified_company_details" required> '+
      'I have checked these details against Pulse Fitness company records.</label>'+
      '<button type="submit" class="button button-primary">Save verified company details</button></form></details>';
  } else if(setupSelectedPage==='terms'){
    body+=setupStatusPill(setupChecked('terms'))+setupField(state)+
      '<div class="setup-info"><strong>Current maintenance agreement terms</strong>'+
      '<p>Upload the approved maintenance terms and exclusions as a PDF. '+
      'Do not use draft terms or an engineer pack. Replacing approved terms requires a new recorded approval.</p></div>'+
      '<form id="setupTermsForm" class="setup-form">'+
      '<label>Approved maintenance terms PDF <input type="file" name="file" accept=".pdf,application/pdf" required></label>'+
      setupApprovalFields()+
      '<label class="setup-check"><input type="checkbox" name="confirm_approved_current_terms" required> '+
      'I confirm this is the current legally approved maintenance agreement terms PDF.</label>'+
      '<button type="submit" class="button button-primary">Save approved maintenance terms</button></form>';
  } else if(setupSelectedPage==='rates'){
    body+=setupStatusPill(setupChecked('rates'))+setupField(state)+
      '<div class="setup-info"><strong>Equipment prices are not maintenance contract rates.</strong>'+
      '<p>Silver, Gold and Platinum maintenance pricing also requires approved rate groups, '+
      'package multipliers, minimums and discount limits. The current Master Price List '+
      'does not authorise these automatically.</p></div>'+
      '<div id="setupRateArea">Checking the maintenance pricing policy…</div>';
  } else {
    body+='<div class="setup-checklist">'+(current.steps||[]).map(step=>
      '<div class="setup-check-row">'+setupStatusPill(step.ready)+
      '<span><strong>'+esc(step.title)+'</strong><small>'+esc(step.detail)+'</small></span></div>'
    ).join('')+'</div>'+
    '<div class="setup-info"><strong>What you can do now</strong><p>'+
      (current.internal_use_ready?
        'Contracts and the Unified Master are available for internal drafts.':
        'Contract records or the Unified Master still need attention before reliable internal pricing.')+
      '</p><p>'+
      (current.customer_quote_ready?
        'Customer quote issue has been separately authorised. Individual quotes still require their own checks.':
        'Customer PDF issue is not authorised by this setup wizard. It stays blocked until commercial approvals and separate release checks pass.')+
      '</p></div>'+
    (current.core_setup_ready?
      '<button id="setupFinish" type="button" class="button button-primary">Finish platform setup</button>':
      '<div class="setup-warning">You still have '+(current.required_count-current.ready_count)+
      ' required check(s). You may continue with internal work and return here later.</div>')+
      '<div id="setupGoLive"></div>';
  }
  panel.innerHTML=body+setupNav();
  if(document.getElementById('setupBack'))
    document.getElementById('setupBack').onclick=()=>setupSelect(SETUP_PAGES[SETUP_PAGES.findIndex(x=>x.id===setupSelectedPage)-1].id);
  if(document.getElementById('setupNext'))
    document.getElementById('setupNext').onclick=()=>setupSelect(SETUP_PAGES[SETUP_PAGES.findIndex(x=>x.id===setupSelectedPage)+1].id);
  if(document.getElementById('setupLater'))
    document.getElementById('setupLater').onclick=event=>setupActionButton(event.currentTarget,async()=>{
      await api('/api/admin/setup/progress',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({action:'continue_later'})});
      window.pulseSetupFirstLogin=false;
      setView('quoting');
    });
  if(document.getElementById('setupFinish'))
    document.getElementById('setupFinish').onclick=event=>setupActionButton(event.currentTarget,async()=>{
      const saved=await api('/api/admin/setup/progress',{method:'POST',
        headers:{'Content-Type':'application/json'},body:JSON.stringify({action:'finish'})});
      window.pulseSetupFirstLogin=false;
      if(saved.core_setup_ready)toast('Setup checks completed. Quote issue remains a separate approval.');
      await setupRefresh();
    });
  if(setupSelectedPage==='contracts'){
    document.getElementById('setupShowContracts').onclick=()=>setView('contracts');
    document.getElementById('setupShowImports').onclick=()=>setView('imports');
  }
  if(setupSelectedPage==='prices'){
    document.getElementById('setupPriceUpload').onsubmit=setupPreviewPrices;
  }
  if(setupSelectedPage==='company'){
    document.getElementById('setupCompanyForm').onsubmit=setupSaveCompany;
  }
  if(setupSelectedPage==='terms'){
    document.getElementById('setupTermsForm').onsubmit=setupSaveTerms;
  }
  if(setupSelectedPage==='rates')setupLoadRates().catch(setupError);
  if(setupSelectedPage==='review')setupLoadIssuance().catch(setupError);
}

async function setupPreviewPrices(event){
  event.preventDefault();
  const form=event.currentTarget;
  if(!form.reportValidity())return;
  const button=form.querySelector('button[type=submit]');
  setupActionButton(button,async()=>{
    setupPendingPrices=null;
    const result=await api('/api/quoting/price-book/preview',{method:'POST',body:new FormData(form)});
    if(view!=='setup'||setupSelectedPage!=='prices')return;
    setupPendingPrices=result;
    const c=result.changes||{};
    const area=document.getElementById('setupPricePreview');
    area.innerHTML='<div class="setup-info"><strong>Review before activation</strong>'+
      '<p>'+esc(c.uploaded_codes||0)+' imported codes · '+esc(c.updated_codes||0)+' updated · '+
      esc(c.new_codes||0)+' new · '+esc(c.retained_existing_codes||0)+' existing codes retained.</p>'+
      '<p>'+esc(c.held_codes||0)+' held prices and '+esc(c.zero_price_codes||0)+' zero-price rows will not become approved prices.</p></div>'+
      '<form id="setupPriceApproval" class="setup-form">'+
      '<label>Reason for activating this price file <input class="input" name="reason" minlength="12" maxlength="500" required></label>'+
      '<label class="setup-check"><input type="checkbox" name="confirm_held" required> '+
      'I have reviewed held and zero-price items.</label>'+
      '<button type="submit" class="button button-primary">Activate reviewed Master prices</button></form>';
    area.querySelector('form').onsubmit=setupActivatePrices;
  });
}
async function setupActivatePrices(event){
  event.preventDefault();
  if(!setupPendingPrices)return;
  const form=event.currentTarget;
  if(!form.reportValidity())return;
  setupActionButton(form.querySelector('button[type=submit]'),async()=>{
    const values=new FormData(form);
    await api('/api/quoting/price-book/activate',{
      method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({
        preview_token:setupPendingPrices.preview_token,
        reason:String(values.get('reason')||''),
        confirm_zero_and_held_prices:values.has('confirm_held')
      })
    });
    setupPendingPrices=null;
    toast('Unified Master equipment price list activated');
    await setupRefresh();
  });
}
async function setupSaveCompany(event){
  event.preventDefault();
  const form=event.currentTarget;
  if(!form.reportValidity())return;
  setupActionButton(form.querySelector('button[type=submit]'),async()=>{
    const fd=new FormData(form);
    const payload=Object.fromEntries(fd.entries());
    payload.confirm_verified_company_details=fd.has('confirm_verified_company_details');
    await api('/api/quoting/commercial-setup/issuer',{
      method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
    toast('Verified company details recorded');
    await setupRefresh();
  });
}
async function setupSaveTerms(event){
  event.preventDefault();
  const form=event.currentTarget;
  if(!form.reportValidity())return;
  setupActionButton(form.querySelector('button[type=submit]'),async()=>{
    const data=new FormData(form);
    data.set('confirm_approved_current_terms',
      data.has('confirm_approved_current_terms')?'true':'false');
    await api('/api/quoting/commercial-setup/terms',{method:'POST',body:data});
    toast('Approved maintenance agreement terms recorded');
    await setupRefresh();
  });
}
async function setupLoadRates(){
  const host=document.getElementById('setupRateArea');
  if(!host)return;
  let data=await api('/api/quoting/commercial-setup/status');
  if(view!=='setup'||setupSelectedPage!=='rates')return;
  const tariff=data.tariff_source||{};
  setupActiveTariff=tariff.staged?tariff.sha256:null;
  if(!tariff.staged){
    host.innerHTML='<div class="setup-warning"><strong>Maintenance rate policy not yet available.</strong>'+
    '<p>The existing customer-issue engine still needs its verified service-rate policy. '+
    'This is separate from the current Unified Master equipment prices. An administrator '+
    'and Commercial/IT must confirm the approved rules before customer PDF release. '+
    'Internal quotation drafts can be prepared in the meantime.</p></div>';
    return;
  }
  if(tariff.commercially_approved){
    host.innerHTML='<div class="setup-info">Your existing service-rate policy is approved. '+
      'No new approval is needed unless rates or terms change.</div>';
    return;
  }
  const rates=(tariff.rates||[]).slice(0,25);
  host.innerHTML='<div class="setup-info"><strong>Review the service rates below.</strong>'+
    '<p>The percentages and minimums must match an approved commercial decision.</p></div>'+
    '<div class="setup-rate-list">'+rates.map(r=>
      '<div><strong>'+esc(r.group||'Unspecified group')+'</strong>'+
      '<span>Standard '+esc(typeof r.standard==='number'?(r.standard*100).toFixed(2)+'%':'Review')+
      ' · Minimum '+esc(typeof r.minimum==='number'?(r.minimum*100).toFixed(2)+'%':'Review')+'</span></div>'
    ).join('')+'</div>'+
    '<p>Packages: '+Object.entries(tariff.tiers||{}).map(([name,mul])=>
    esc(name)+': '+esc(mul)).join(' · ')+'</p>'+
    '<form id="setupRatesForm" class="setup-form">'+setupApprovalFields()+
    '<label class="setup-check"><input type="checkbox" name="confirm_equipment_rate_groups" required> I checked equipment rate groups.</label>'+
    '<label class="setup-check"><input type="checkbox" name="confirm_package_multipliers" required> I checked package multipliers.</label>'+
    '<label class="setup-check"><input type="checkbox" name="confirm_minimums_and_discounts" required> I checked minimums and discounts.</label>'+
    '<label class="setup-check"><input type="checkbox" name="confirm_parity_exceptions_reviewed" required> I reviewed pricing exceptions.</label>'+
    '<button type="submit" class="button button-primary">Approve maintenance pricing policy</button></form>';
  document.getElementById('setupRatesForm').onsubmit=setupApproveRates;
}
async function setupApproveRates(event){
  event.preventDefault();
  const form=event.currentTarget;
  if(!form.reportValidity()||!setupActiveTariff)return;
  setupActionButton(form.querySelector('button[type=submit]'),async()=>{
    const fd=new FormData(form),payload=Object.fromEntries(fd.entries());
    for(const key of ['confirm_equipment_rate_groups','confirm_package_multipliers',
      'confirm_minimums_and_discounts','confirm_parity_exceptions_reviewed']){
      payload[key]=fd.has(key);
    }
    payload.expected_source_sha256=setupActiveTariff;
    await api('/api/quoting/commercial-setup/tariff',{
      method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
    toast('Maintenance pricing approval recorded');
    await setupRefresh();
  });
}
async function setupLoadIssuance(){
  const host=document.getElementById('setupGoLive');
  if(!host)return;
  if(!setupLiveStatus.core_setup_ready)return;
  if(setupLiveStatus.customer_issuance_enabled){
    host.innerHTML='<div class="setup-info">Customer PDF issue is currently enabled. '+
      'Individual customer quotations still require the usual checks and approvals.</div>';
    return;
  }
  host.innerHTML='<details class="setup-approval-disclosure"><summary>Separate authorisation for customer PDF issue</summary>'+
    '<p>Only enable this after end-to-end tests and commercial approval. '+
    'Completing the setup wizard does not enable customer issue.</p>'+
    '<form id="setupIssuanceForm" class="setup-form">'+setupApprovalFields()+
    '<label class="setup-check"><input type="checkbox" name="confirm_customer_quote_acceptance_tests" required>'+
    ' I confirm the customer quotation acceptance tests have passed.</label>'+
    '<button type="submit" class="button button-primary">Enable approved customer PDF issue</button></form></details>';
  document.getElementById('setupIssuanceForm').onsubmit=event=>{
    event.preventDefault();const form=event.currentTarget;
    if(!form.reportValidity())return;
    if(!window.confirm('Enable customer quotation PDF issue for approved quotations?'))return;
    setupActionButton(form.querySelector('button[type=submit]'),async()=>{
      const fd=new FormData(form),payload=Object.fromEntries(fd.entries());
      payload.enabled=true;
      payload.confirm_customer_quote_acceptance_tests=fd.has('confirm_customer_quote_acceptance_tests');
      await api('/api/quoting/commercial-setup/issuance',{
        method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
      toast('Customer PDF issue authorisation saved');
      await setupRefresh();
    });
  };
}
