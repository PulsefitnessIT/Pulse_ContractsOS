/* SmartQuote internal fast quote: operates from the one active Master.
   It reuses the coordinator's equipment schedule and does not depend on
   original V10 configuration rules. It can NEVER issue an approved quote. */
let quickDraftLines = [];
let quickDraftResult = null;
let quickDraftBasis = null;

function quickCurrentBasis(){
  const form=document.querySelector('#unifiedDraftForm');
  return JSON.stringify({
    customer:form?.elements.customer.value||'',
    site:form?.elements.site.value||'',
    package:form?.elements.tier.value||'',
    term:form?.elements.term_years.value||'',
    discount:form?.elements.discount_percent.value||'',
    equipment:unifiedEquipment.map(x=>({
      item_code:x.item_code, quantity:x.quantity, serial:x.serial,
      description:x.description
    })),
    quick_rates:quickDraftLines,
    scope:document.querySelector('#quickScopeNotes')?.value||'',
  });
}

function quickInvalidate(){
  if(!quickDraftResult)return;
  quickDraftResult=null;
  quickDraftBasis=null;
  const print=document.querySelector('#quickPrint');
  if(print)print.disabled=true;
  const status=document.querySelector('#quickDraftResponse');
  if(status)status.textContent='Quotation information changed. Reload equipment and recalculate.';
}


function quickQuoteHistoricRate(description) {
  const name=String(description||'').toLowerCase();
  if(/step.?mill|stair.?mill/.test(name))return '';
  if(name.includes('fluid') && name.includes('row'))return '13';
  if(name.includes('fluid') && /ube|recumbent/.test(name))return '10';
  if(/concept.?2/.test(name))return '9';
  if(/treadmill|elliptical|cross.?trainer/.test(name))return '3.75';
  return '3';
}

function initQuoteQuickDraft() {
  const host=document.querySelector('#quoteQuickDraftHost');
  if(!host||view!=='quoting')return;
  quickDraftLines=[];
  quickDraftResult=null;
  host.innerHTML=
    '<p>Use the equipment and customer details entered in the quotation above. '+
    'The unified Master provides the price; enter or confirm the annual '+
    'service rate for each machine. No historical V10 tariff mapping is required.</p>'+
    '<div style="display:flex;gap:.6rem;flex-wrap:wrap">'+
    '<button type="button" class="button button-outline" id="quickCopyEquipment">'+
    '1. Load machines from current draft</button>'+
    '<button type="button" class="button button-primary" id="quickGetPrice" disabled>'+
    '2. Calculate internal quote</button>'+
    '<button type="button" class="button button-outline" id="quickPrint" disabled>'+
    '3. Download branded internal PDF</button></div>'+
    '<div id="quickRateEditor"></div>'+
    '<label style="margin-top:1rem">Maintenance scope and exclusions '+
    '<textarea id="quickScopeNotes" rows="2" placeholder="Enter agreed scope and exclusions; subject to commercial approval"></textarea>'+
    '</label>'+
    '<div id="quickDraftResponse" role="status" aria-live="polite"></div>'+
    '<p class="fine-print">Historical percentage guides are NOT approved Silver, Gold or '+
    'Platinum prices. This workflow never enables customer PDF issue. Source '+
    'equipment prices, machine suitability, terms and tariff must be checked.</p>';
  host.querySelector('#quickCopyEquipment').addEventListener('click',quickCopyEquipment);
  host.querySelector('#quickGetPrice').addEventListener('click',quickCalculate);
  host.querySelector('#quickPrint').addEventListener('click',quickPrintInternal);
  const form=document.querySelector('#unifiedDraftForm');
  if(form){
    form.addEventListener('input',quickInvalidate);
    form.addEventListener('change',quickInvalidate);
  }
  host.querySelector('#quickScopeNotes').addEventListener('input',quickInvalidate);
}

function quickCopyEquipment(){
  if(view!=='quoting')return;
  quickDraftLines=(Array.isArray(unifiedEquipment)?unifiedEquipment:[]).map(line=>({
    sku:String(line.item_code||'').trim().toUpperCase(),
    description:String(line.description||''),
    quantity:Number(line.quantity)||1,
    serials:String(line.serial||''),
    rate:line.annual_rate_percent!==null&&line.annual_rate_percent!==undefined?
      String(line.annual_rate_percent):quickQuoteHistoricRate(line.description||''),
    fixed:line.fixed_annual_unit_gbp!==null&&line.fixed_annual_unit_gbp!==undefined?
      String(line.fixed_annual_unit_gbp):''
  }));
  quickDraftResult=null;
  const button=document.querySelector('#quickGetPrice');
  const print=document.querySelector('#quickPrint');
  if(button)button.disabled=!quickDraftLines.length;
  if(print)print.disabled=true;
  const host=document.querySelector('#quickRateEditor');
  if(!host)return;
  if(!quickDraftLines.length){
    host.innerHTML='<p class="notice warning">Add machines with the normal equipment form first.</p>';
    return;
  }
  host.innerHTML='<h4>Confirm the annual maintenance rate for each selected machine</h4>'+
    '<div style="overflow-x:auto"><table class="data-table">'+
    '<thead><tr><th>Exact SKU / equipment</th><th>Qty</th>'+
    '<th>Historic guide % (editable)</th><th>Fixed annual per unit £ (optional)</th></tr></thead>'+
    '<tbody>'+quickDraftLines.map((line,i)=>
      '<tr><td><strong>'+esc(line.sku||'MISSING SKU')+'</strong><br>'+
      esc(line.description)+'</td><td>'+esc(line.quantity)+
      '</td><td><input data-quick-rate="'+i+'" type="number" step="0.01" min="0" max="100" '+
      'value="'+esc(line.rate)+'" style="width:100px"></td>'+
      '<td><input data-quick-fixed="'+i+'" type="number" step="0.01" min="0" '+
      'placeholder="Overrides %" style="width:140px"></td></tr>'
    ).join('')+'</tbody></table></div>';
  host.querySelectorAll('[data-quick-rate]').forEach(input=>{
    input.addEventListener('input',()=>{
      const index=Number(input.dataset.quickRate);
      quickDraftLines[index].rate=input.value;
      if(unifiedEquipment[index])unifiedEquipment[index].annual_rate_percent=
        input.value.trim()===''?null:input.value;
      quickDraftResult=null;
      const p=document.querySelector('#quickPrint');
      if(p)p.disabled=true;
    });
  });
  host.querySelectorAll('[data-quick-fixed]').forEach(input=>{
    input.addEventListener('input',()=>{
      const index=Number(input.dataset.quickFixed);
      quickDraftLines[index].fixed=input.value;
      if(unifiedEquipment[index])unifiedEquipment[index].fixed_annual_unit_gbp=
        input.value.trim()===''?null:input.value;
      quickDraftResult=null;
      const p=document.querySelector('#quickPrint');
      if(p)p.disabled=true;
    });
  });
  const status=document.querySelector('#quickDraftResponse');
  if(status)status.textContent='Rate suggestions are based on historic quote patterns. Review before calculation.';
}

function quickPayload(){
  const form=document.querySelector('#unifiedDraftForm');
  return {
    customer:String(form.elements.customer.value||'').trim(),
    site:String(form.elements.site.value||'').trim(),
    package:String(form.elements.tier.value||'Gold'),
    term_years:Number(form.elements.term_years.value||1),
    discount_percent:String(form.elements.discount_percent.value||0),
    notes:String(document.querySelector('#quickScopeNotes')?.value||''),
    lines:quickDraftLines.map(line=>({
      sku:line.sku,
      quantity:line.quantity,
      serials:line.serials,
      annual_rate_percent:line.fixed.trim()===''?
        (line.rate.trim()!==''?line.rate:null):null,
      fixed_annual_unit_gbp:line.fixed.trim()!==''?line.fixed:null
    }))
  };
}


async function quickCalculate(){
  const status=document.querySelector('#quickDraftResponse');
  const button=document.querySelector('#quickGetPrice');
  if(!status||!button)return;
  const form=document.querySelector('#unifiedDraftForm');
  if(!form){
    status.textContent='Create a quotation draft first.';
    return;
  }
  if(!quickDraftLines.length){
    status.textContent='Load the current equipment lines first.';
    return;
  }
  // Re-save only if the coordinator changed a customer, machine or rate.
  // Saved draft rate fields are reloaded on a subsequent visit.
  if(typeof unifiedDraftHasUnsavedChanges==='function' &&
     (!unifiedDraftSelected||unifiedDraftHasUnsavedChanges())){
    const saved=await unifiedSaveDraft();
    if(!saved){
      status.textContent='Save the customer and equipment changes before calculating.';
      return;
    }
  }
  button.disabled=true;
  status.textContent='Calculating against the latest unified Master price version…';
  try{
    const json=quickPayload();
    const calculated=await api('/api/quoting/quick-draft/preview',{
      method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify(json)
    });
    if(view!=='quoting'||!document.querySelector('#quickDraftResponse'))return;
    quickDraftResult=calculated;
    quickDraftBasis=quickCurrentBasis();
    status.innerHTML='<h4>Internal pricing draft: '+esc(calculated.draft_reference)+'</h4>'+
      '<p>Active Master v'+esc(calculated.price_book_revision)+' · '+
      esc(calculated.priced_line_count)+' of '+
      esc(calculated.line_count)+' lines priced.</p>'+
      '<p><strong>Annual (ex VAT): '+esc('£'+Number(calculated.annual_partial_gbp).toLocaleString(
        'en-GB',{minimumFractionDigits:2,maximumFractionDigits:2}))+
      '</strong> · Monthly equivalent (ex VAT): £'+
      esc(Number(calculated.monthly_partial_gbp).toLocaleString('en-GB',
        {minimumFractionDigits:2,maximumFractionDigits:2}))+
      ' · '+esc(calculated.term_years)+'-year term: £'+
      esc(Number(calculated.term_partial_gbp).toLocaleString('en-GB',
        {minimumFractionDigits:2,maximumFractionDigits:2}))+'</p>'+
      '<p class="notice warning">INTERNAL DRAFT ONLY — not approved for external customer issue. '+
      'Final maintenance rates, package cover and contract terms must be authorised.</p>'+
      (calculated.issues.length?
        '<ul>'+calculated.issues.map(issue=>'<li>'+esc(issue)+'</li>').join('')+'</ul>':'');
    const print=document.querySelector('#quickPrint');
    if(print)print.disabled=!calculated.complete_calculation;
  }catch(error){
    quickDraftResult=null;
    status.textContent='Quick quote blocked: '+error.message+
      '. Confirm all item codes and that the unified Master is active.';
  }finally{
    button.disabled=false;
  }
}

async function quickPrintInternal(){
  const result=quickDraftResult;
  const feedback=document.querySelector('#quickDraftResponse');
  const button=document.querySelector('#quickPrint');
  if(!result||!result.complete_calculation || !button){
    alert('Recalculate all equipment prices and rates before downloading.');
    return;
  }
  if(quickDraftBasis!==quickCurrentBasis()){
    quickInvalidate();
    alert('Customer, equipment or rates changed. Recalculate before downloading.');
    return;
  }
  button.disabled=true;
  try{
    const draft=quickPayload();
    draft.expected_price_book_sha256=result.price_book_sha256;
    const response=await fetch('/api/quoting/quick-draft/internal-preview.pdf',{
      method:'POST',
      credentials:'same-origin',
      headers:{
        'Content-Type':'application/json',
        'X-Pulse-CSRF':pilotCsrf()
      },
      body:JSON.stringify(draft)
    });
    if(response.status===401){
      location.href='/pilot/login';
      throw Error('Pilot session expired.');
    }
    if(!response.ok){
      let detail;
      try{const data=await response.json();detail=data.detail;}catch{}
      throw Error(detail||'PDF preview rejected ('+response.status+')');
    }
    if(quickDraftBasis!==quickCurrentBasis()){
      quickInvalidate();
      throw Error('The quote changed while the document was downloading.');
    }
    const blob=await response.blob();
    if(blob.type!=='application/pdf' || !blob.size)
      throw Error('Server returned an invalid PDF.');
    const url=URL.createObjectURL(blob);
    const link=document.createElement('a');
    link.href=url;
    link.download='Pulse_Fitness_'+result.draft_reference+'.pdf';
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(()=>URL.revokeObjectURL(url),3000);
    if(feedback)feedback.insertAdjacentHTML(
      'beforeend','<p class="fine-print">Branded INTERNAL DRAFT PDF downloaded. '+
      'Not authorised for external issue.</p>'
    );
  }catch(error){
    if(feedback)feedback.insertAdjacentHTML(
      'beforeend','<p class="notice warning">'+esc(error.message)+'</p>'
    );
  }finally{button.disabled=false;}
}
