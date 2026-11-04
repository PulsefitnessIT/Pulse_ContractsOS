/* Commercial approval control centre for the protected SmartQuote pilot.
   Admin controls only. Server validates each attestation; nothing is issued
   from the browser without source, scope, quote and terms verification. */
async function initQuoteCommercialSetup(){
  const host=document.querySelector('#quoteCommercialSetupHost');
  if(!host||view!=='quoting')return;
  host.innerHTML='<p>Loading source tariff, terms and company identity approvals…</p>';
  try {
    const state=await api('/api/quoting/commercial-setup/status');
    if(view!=='quoting'||!document.querySelector('#quoteCommercialSetupHost'))return;
    renderQuoteCommercialSetup(state);
  }catch(error){host.textContent='Unable to review commercial setup: '+error.message;}
}

function commercialStateText(yes){
  return '<strong>'+esc(yes?'Verified':'Action required')+'</strong>';
}
function commercialApprovalFields(){
  return '<label>Commercial approval / change reference '+
    '<input name="approval_reference" minlength="8" maxlength="250" required '+
    'placeholder="Director or authorised manager approval reference"></label>'+
    '<label>Reason / source evidence '+
    '<input name="reason" minlength="12" maxlength="500" required '+
    'placeholder="Identify the approved document or commercial decision"></label>';
}
function renderQuoteCommercialSetup(state){
  const host=document.querySelector('#quoteCommercialSetupHost');
  if(!host)return;
  const tariff=state.tariff_source||{},settings=state.settings||{};
  const sourceOk=Boolean(tariff.staged);
  const rateRows=(tariff.rates||[]).map(rate=>
    '<tr><td>'+esc(rate.group)+'</td>'+
    '<td>'+esc(typeof rate.standard==='number'?(rate.standard*100).toFixed(2)+'%':'Review')+'</td>'+
    '<td>'+esc(typeof rate.minimum==='number'?(rate.minimum*100).toFixed(2)+'%':'Review')+'</td>'+
    '<td>'+esc(rate.status||'Not specified')+'</td></tr>').join('');
  const tiers=Object.entries(tariff.tiers||{}).map(([name,mul])=>
    esc(name)+': '+esc(mul)).join(' · ');
  const current=[
    ['Exact V10 tariff staged',sourceOk],
    ['Tariff commercially approved',tariff.commercially_approved],
    ['Approved maintenance terms',settings.terms?.configured && settings.terms?.integrity_valid],
    ['Verified supplier company details',settings.issuer?.configured && settings.issuer?.integrity_valid],
    ['Customer PDF issue switched on',state.customer_issuance_enabled]
  ];
  const status=current.map(([name,ok])=>'<tr><td>'+esc(name)+'</td><td>'+
    commercialStateText(ok)+'</td></tr>').join('');
  host.innerHTML=
    '<p>This control centre makes quotation setup manageable by an authorised '+
    'Administrator. The current August Master and exact Sage price-list '+
    'values are accepted equipment price bases. Step 1 is for the separate '+
    'maintenance rate percentages, package multipliers, minimums and discounts. '+
    'The provisional V10 service tariff is NOT automatically authorised by the '+
    'Sage price-source decision. Each approval records an actor and source fingerprint.</p>'+
    '<div style="overflow-x:auto"><table class="data-table"><thead>'+
    '<tr><th>Commercial release requirement</th><th>Status</th></tr></thead><tbody>'+
    status+'</tbody></table></div>'+
    '<details><summary><strong>Step 1 — Approve actual maintenance tariff rates</strong></summary>'+
    (sourceOk?'<p>Source policy: '+esc(tariff.pricing_status)+
      ' · SHA-256 '+esc(tariff.sha256)+'</p>'+
      '<p>Packages: '+tiers+'</p>'+
      '<div style="overflow-x:auto"><table class="data-table"><thead>'+
      '<tr><th>Group</th><th>Standard</th><th>Minimum</th><th>Status</th></tr></thead>'+
      '<tbody>'+rateRows+'</tbody></table></div>'+
      '<form id="commercialTariffForm">'+commercialApprovalFields()+
      '<label><input type="checkbox" name="confirm_equipment_rate_groups" required> '+
      'I have checked and approved equipment group rates</label>'+
      '<label><input type="checkbox" name="confirm_package_multipliers" required> '+
      'I have checked Silver, Gold and Platinum multipliers</label>'+
      '<label><input type="checkbox" name="confirm_minimums_and_discounts" required> '+
      'I have checked minimum prices and discount policy</label>'+
      '<label><input type="checkbox" name="confirm_parity_exceptions_reviewed" required> '+
      'I have reviewed source pricing parity and outstanding exceptions</label>'+
      '<button type="submit" class="button button-outline">Approve reviewed tariff version</button>'+
      '</form>':'<p class="notice warning">IT must stage and fingerprint the genuine '+
       'V10 pricing catalogue/configuration/rules. '+esc(tariff.error||'')+'</p>')+
    '</details>'+
    '<details><summary><strong>Step 2 — Approve current maintenance terms PDF</strong></summary>'+
    '<p>The exact PDF is stored privately and appended without modification to '+
    'each issued customer quotation.</p>'+
    '<form id="commercialTermsForm">'+
    '<label>Approved terms PDF <input name="file" type="file" accept=".pdf" required></label>'+
    commercialApprovalFields()+
    '<label><input type="checkbox" name="confirm_approved_current_terms" required>'+
    ' I confirm these are the current commercially approved terms and exclusions</label>'+
    '<button type="submit" class="button button-outline">Save approved terms</button></form>'+
    '</details>'+
    '<details><summary><strong>Step 3 — Verify supplier/company details</strong></summary>'+
    '<form id="commercialIssuerForm"><div class="form-grid">'+
    '<label>Full legal company name <input name="legal_name" required maxlength="120"></label>'+
    '<label>Company registration number <input name="company_number" required maxlength="30"></label>'+
    '<label>Registered office address <input name="registered_address" required maxlength="250"></label>'+
    '<label>Approved service email <input name="contact_email" required type="email" maxlength="250"></label>'+
    '<label>Customer telephone <input name="telephone" maxlength="40"></label>'+
    '<label>VAT registration (if applicable) <input name="vat_number" maxlength="40"></label>'+
    '</div>'+commercialApprovalFields()+
    '<label><input type="checkbox" name="confirm_verified_company_details" required>'+
    ' I have verified the details against company records</label>'+
    '<button type="submit" class="button button-outline">Approve supplier details</button></form>'+
    '</details>'+
    '<details><summary><strong>Step 4 — Enable customer quotation issuance</strong></summary>'+
    '<p>This step does not approve individual customer quotes. An Administrator '+
    'must still approve each priced quotation separately.</p>'+
    '<form id="commercialEnableForm">'+commercialApprovalFields()+
    '<label>Customer PDF availability <select name="enabled">'+
    '<option value="true">Enable after all release checks</option>'+
    '<option value="false">Disable customer quotations</option></select></label>'+
    '<label><input type="checkbox" name="confirm_customer_quote_acceptance_tests" required>'+
    ' I have completed an end-to-end acceptance test with real approved data</label>'+
    '<button type="submit" class="button button-primary">Apply quotation issue setting</button>'+
    '</form></details>'+
    '<p id="commercialSetupMessage" role="status" aria-live="polite"></p>'+
    '<button type="button" class="button button-outline" id="commercialAuditLoad">'+
    'Review commercial approval history</button>'+
    '<div id="commercialSetupAudit"></div>';
  const tariffForm=host.querySelector('#commercialTariffForm');
  if(tariffForm)tariffForm.addEventListener('submit',event=>commercialSubmit(event,'tariff',tariff.sha256));
  host.querySelector('#commercialTermsForm').addEventListener('submit',event=>commercialSubmit(event,'terms'));
  host.querySelector('#commercialIssuerForm').addEventListener('submit',event=>commercialSubmit(event,'issuer'));
  host.querySelector('#commercialEnableForm').addEventListener('submit',event=>commercialSubmit(event,'issuance'));
  host.querySelector('#commercialAuditLoad').addEventListener('click',commercialLoadAudit);
}

async function commercialSubmit(event,kind,sourceSha){
  event.preventDefault();
  const form=event.currentTarget;
  if(!form.reportValidity())return;
  const feedback=document.querySelector('#commercialSetupMessage');
  const button=form.querySelector('button[type="submit"]');
  if(!feedback||!button)return;
  button.disabled=true;
  feedback.textContent='Verifying and recording approved '+kind+' evidence…';
  const formData=new FormData(form);
  try{
    let request;
    const url='/api/quoting/commercial-setup/'+kind;
    if(kind==='terms'){
      formData.set('confirm_approved_current_terms',
                   formData.has('confirm_approved_current_terms')?'true':'false');
      request={method:'POST',body:formData};
    }else{
      const payload=Object.fromEntries(formData.entries());
      if(kind==='tariff'){
        payload.expected_source_sha256=sourceSha;
        for(const key of ['confirm_equipment_rate_groups','confirm_package_multipliers',
          'confirm_minimums_and_discounts','confirm_parity_exceptions_reviewed']){
          payload[key]=formData.has(key);
        }
      }else if(kind==='issuer'){
        payload.confirm_verified_company_details=formData.has('confirm_verified_company_details');
      }else{
        payload.enabled=payload.enabled==='true';
        payload.confirm_customer_quote_acceptance_tests=
          formData.has('confirm_customer_quote_acceptance_tests');
      }
      request={method:'POST',headers:{'Content-Type':'application/json'},
               body:JSON.stringify(payload)};
    }
    const result=await api(url,request);
    if(view!=='quoting')return;
    await initQuoteCommercialSetup();
    const target=document.querySelector('#commercialSetupMessage');
    if(target)target.textContent=kind+' recorded by '+result.approved_by+
      '. Revision '+result.revision+'. Any previously enabled customer release '+
      'was disabled if these commercial sources changed.';
  }catch(error){
    feedback.textContent='Cannot approve '+kind+': '+error.message;
  }finally{button.disabled=false;}
}
async function commercialLoadAudit(){
  const host=document.querySelector('#commercialSetupAudit');
  if(!host)return;
  host.textContent='Loading commercial review history…';
  try{
    const data=await api('/api/quoting/commercial-setup/audit?limit=30');
    host.innerHTML='<div style="overflow-x:auto"><table class="data-table"><thead>'+
      '<tr><th>When</th><th>Approval</th><th>Revision</th>'+
      '<th>Authorised by</th><th>Reference</th><th>Reason</th></tr></thead><tbody>'+
      (data.items||[]).map(row=>'<tr><td>'+esc(row.approved_at)+
        '</td><td>'+esc(row.kind)+'</td><td>'+esc(row.revision)+
        '</td><td>'+esc(row.approved_by)+'</td><td>'+esc(row.approval_reference)+
        '</td><td>'+esc(row.reason)+'</td></tr>').join('')+
      '</tbody></table></div>';
  }catch(error){host.textContent='Cannot load commercial approvals: '+error.message;}
}
