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
    '3. Print internal draft / PDF</button></div>'+
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
    const json={
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
  if(!result||!result.complete_calculation){
    alert('Recalculate all equipment lines before printing.');
    return;
  }
  if(quickDraftBasis!==quickCurrentBasis()){
    quickInvalidate();
    alert('Customer, equipment or pricing changed. Recalculate before printing.');
    return;
  }
  // Open from the direct button click, then recheck the real price source.
  // The window remains empty and closes on a changed Master revision.
  const opened=window.open('','_blank');
  if(!opened){
    alert('Allow pop-ups for this internal quote preview, then try again.');
    return;
  }
  try{
    const current=await api('/api/quoting/quick-draft/status');
    if(current.price_book_sha256!==result.price_book_sha256){
      quickInvalidate();
      throw new Error('The unified Master price list changed. Recalculate your quote.');
    }
  }catch(error){
    opened.close();
    alert('Cannot print a stale quote: '+error.message);
    return;
  }
  const escHtml=(v)=>String(v??'').replace(/[&<>"']/g,
    c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const rows=result.equipment.map((row,i)=>'<tr>'+
    '<td>'+(i+1)+'</td><td>'+escHtml(row.name)+'<div class="code">'+escHtml(row.sku)+'</div></td>'+
    '<td>'+escHtml(row.quantity)+'</td><td>'+escHtml(row.serials||'To be confirmed')+'</td></tr>').join('');
  const total=Number(result.annual_partial_gbp).toLocaleString('en-GB',{
    style:'currency',currency:'GBP'
  });
  const term=Number(result.term_partial_gbp).toLocaleString('en-GB',{
    style:'currency',currency:'GBP'
  });
  const scope=String(document.querySelector('#quickScopeNotes')?.value||'')
    .slice(0,2500);
  const doc='<!doctype html><html><head><meta charset="utf-8">'+
    '<title>INTERNAL '+escHtml(result.draft_reference)+'</title>'+
    '<style>@page{size:A4;margin:14mm}*{box-sizing:border-box}'+
    'body{font:13px Arial,sans-serif;color:#1B1C1D}'+
    'header{background:#1B1C1D;color:#fff;border-bottom:5px solid #19CDFF;'+
    'padding:15px 18px;display:flex;align-items:center;justify-content:space-between;gap:24px;'+
    '-webkit-print-color-adjust:exact;print-color-adjust:exact}'+
    'header img{width:196px;max-height:48px;object-fit:contain;display:block}'+
    'h1{font-size:23px;letter-spacing:.01em;margin:0}h2{font-size:17px;margin-top:26px}'+
    '.small{font-size:11px;color:#d6ecf3}.draft{color:#19CDFF;font-weight:900}'+
    'table{width:100%;border-collapse:collapse;margin-top:15px}td,th{padding:9px;'+
    'border-bottom:1px solid #d9e1e8;text-align:left;vertical-align:top}'+
    'th{background:#e8f9ff;-webkit-print-color-adjust:exact;print-color-adjust:exact}'+
    'footer{border-top:2px solid #19CDFF;padding-top:15px;margin-top:36px;font-size:11px}'+
    '.code{font:11px monospace;color:#6E7476}tr{page-break-inside:avoid}'+
    '.right{text-align:right}h2{page-break-after:avoid}</style></head><body>'+
    '<header><div><img src="/static/brand/pulse-fitness-reverse.svg" '+
    'alt="Pulse Fitness"><span class="small">SERVICE &amp; AFTERSALES · MAINTENANCE PROPOSAL</span></div>'+
    '<div class="right draft">INTERNAL DRAFT<br><span class="small">'+
    escHtml(result.draft_reference)+'</span></div></header>'+
    '<h2>Prepared for</h2><p><strong>'+escHtml(result.customer)+
    '</strong><br>'+escHtml(result.site)+'</p>'+
    '<p>Proposed package: <strong>'+escHtml(result.package)+
    '</strong> · Term: '+escHtml(result.term_years)+' year(s)</p>'+
    '<h2>Equipment schedule</h2><table><thead><tr><th>#</th><th>Machine</th>'+
    '<th>Qty</th><th>Serial(s)</th></tr></thead><tbody>'+rows+'</tbody></table>'+
    '<h2>Proposed maintenance</h2><p><strong>Annual (ex VAT): '+escHtml(total)+
    '</strong><br>Total full term (ex VAT): '+escHtml(term)+'</p>'+
    '<h2>Scope / exclusions</h2><p>'+escHtml(scope).replace(/\n/g,'<br>')+'</p>'+
    '<footer><strong>INTERNAL DRAFT — NOT AUTHORISED FOR CUSTOMER ISSUE.</strong> '+
    'Annual maintenance percentages or manually entered fixed charges, service eligibility, '+
    'cover package, serial numbers and final terms require Pulse commercial approval. '+
    'The source price book does not itself approve maintenance cover. '+
    'Document is not a binding offer.</footer></body></html>';
  opened.document.open();
  opened.document.write(doc);
  opened.document.close();
  opened.focus();
  // Do not print before the supplied corporate logo has loaded.
  const logo=opened.document.querySelector('header img');
  if(logo && !logo.complete){
    logo.addEventListener('load',()=>opened.print(),{once:true});
    logo.addEventListener('error',()=>opened.print(),{once:true});
  }else{
    opened.print();
  }
}
