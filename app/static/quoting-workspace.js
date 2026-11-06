/* Pulse Fitness unified quoting: one workspace; separate, protected data sources.
   Native drafts never contain inferred commercial prices. */
let unifiedDraftSelected = null;
let unifiedEquipment = [];
let unifiedDraftRecords = [];
let unifiedCatalogueMatches = [];
let unifiedSiteMatches = [];
let quotePriceEditorSelection = null;
let unifiedEditingEquipmentIndex = null;
let unifiedRemovedEquipment = null;
let unifiedLastSavedDraftState = null;
let unifiedLatestPricePreview = null;
let unifiedSavePending = false;
let unifiedNavigationGuardInstalled = false;

function unifiedDraftSnapshot() {
  const form=document.querySelector('#unifiedDraftForm');
  if(!form)return null;
  const values=Object.fromEntries(new FormData(form).entries());
  return JSON.stringify({
    customer:String(values.customer||'').trim(),
    site:String(values.site||'').trim(),
    contact:String(values.contact||'').trim(),
    source_contract_id:Number(values.source_contract_id||0),
    tier:String(values.tier||'Gold'),
    term_years:Number(values.term_years||1),
    discount_percent:Number(values.discount_percent||0),
    contract_start:String(values.contract_start||''),
    contract_end:String(values.contract_end||''),
    equipment:unifiedEquipment.map(e=>({
      item_code:String(e.item_code||'').trim(),
      description:String(e.description||'').trim(),
      serial:String(e.serial||'').trim(),
      serial_numbers:Array.isArray(e.serial_numbers)?e.serial_numbers.map(String):[],
      cover_start:String(e.cover_start||''),
      quantity:Number(e.quantity),
      source_import_id:e.source_import_id||null,
      source_pages:Array.isArray(e.source_pages)?e.source_pages:[],
      invoice_match_confirmed:e.invoice_match_confirmed===true,
      invoice_match_method:String(e.invoice_match_method||''),
      annual_rate_percent:e.annual_rate_percent??null,
      fixed_annual_unit_gbp:e.fixed_annual_unit_gbp??null,
      quantity_verified:e.quantity_verified!==false,
    }))
  });
}

function unifiedHasPendingEquipmentInput() {
  const form=document.querySelector('#unifiedEquipmentAdd');
  if(!form)return false;
  const keys=['description','item_code','serial','serial_numbers','cover_start'];
  return keys.some(key=>String(form.elements[key]?.value||'').trim()) ||
    Number(form.elements.quantity?.value||1)!==1;
}

function unifiedDraftHasUnsavedChanges() {
  const current=unifiedDraftSnapshot();
  return Boolean(unifiedEditingEquipmentIndex!==null ||
    unifiedHasPendingEquipmentInput() ||
    (current!==null && unifiedLastSavedDraftState!==null &&
      current!==unifiedLastSavedDraftState));
}

function unifiedCoordinatorGuidance() {
  const host=document.querySelector('#quoteCoordinatorGuide');
  const form=document.querySelector('#unifiedDraftForm');
  if(!host||!form)return;
  const customer=String(form.elements.customer.value||'').trim();
  const site=String(form.elements.site.value||'').trim();
  const count=unifiedEquipment.reduce((sum,item)=>sum+Number(item.quantity||0),0);
  const unconfirmed=unifiedEquipment.reduce((sum,item)=>
    sum+(String(item.serial||'').trim()?Math.max(0,item.quantity-1):item.quantity),0);
  const provisional=unifiedEquipment.filter(item=>
    item.invoice_match_method==='auto_exact_master' &&
    item.quantity_verified!==true).length;
  let step=1,action='Select a recorded site or enter a verified customer and site.';
  if(customer&&site){
    step=2;
    action='Find equipment by model or item code, add quantities and confirm serial numbers.';
    if(unifiedEquipment.length){
      step=3;
      action=provisional?
        'Confirm imported equipment quantities together before preparing the quotation PDF.':
        'Save and calculate the source-based maintenance estimate.';
      if(provisional)step=2;
      if(unifiedEditingEquipmentIndex!==null)
        action='Finish or cancel your equipment edit before saving this quotation.';
      else if(unifiedHasPendingEquipmentInput()){
        step=2;
        action='Select Add equipment line to include the machine you are entering before saving.';
      }
      else if(!unifiedDraftSelected||unifiedDraftHasUnsavedChanges())
        action='Save and calculate to include your latest changes.';
      else if(unifiedLatestPricePreview){
        step=4;
        action=unifiedLatestPricePreview.complete_price?
          'Review all source exceptions, package options and the manager approval checks before preparing a customer PDF.':
          'Some equipment cannot be fully priced. Check the exceptions and correct the source SKU or service mapping.';
      }
    }
  }
  host.innerHTML='<strong>Step '+step+' of 4 — '+
    esc(['Customer & site','Equipment','Calculate','Review & approve'][step-1])+
    '</strong><p>'+esc(action)+'</p>'+
    '<p class="fine-print">'+esc(unifiedEquipment.length)+
    ' equipment lines · '+esc(count)+' units'+
    (provisional?' · '+esc(provisional)+' invoice quantities to verify':'')+
    (unconfirmed?' · '+esc(unconfirmed)+' serials still to verify':'')+
    (unifiedDraftHasUnsavedChanges()?' · Unsaved changes':'')+
    '</p>';
}

function unifiedGuardNavigation() {
  if(unifiedNavigationGuardInstalled)return;
  const nav=document.querySelector('#nav');
  if(!nav)return;
  nav.addEventListener('click',event=>{
    if(view!=='quoting'||!unifiedDraftHasUnsavedChanges())return;
    const button=event.target.closest('[data-view]');
    if(!button||button.dataset.view==='quoting')return;
    if(!window.confirm('This quotation contains unsaved changes. Leave SmartQuote without saving?')){
      event.preventDefault();
      event.stopImmediatePropagation();
    }
  },true);
  unifiedNavigationGuardInstalled=true;
}

async function quotingWorkspacePage() {
  unifiedDraftSelected = null;
  unifiedEquipment = [];
  content.innerHTML =
    '<section class="panel pulse-smartquote-hero"><p class="pulse-workspace-eyebrow">PULSE FITNESS / SMARTQUOTE</p>' +
    '<h2>Maintenance quotations, made simple.</h2>' +
    '<p>Import your sales invoices, automatically match equipment codes to the unified Master, ' +
    'review only exceptions and calculate your maintenance proposal. ' +
    'Customer issue remains subject to approved tariffs and terms.</p>' +
    '<div class="pulse-step-strip" aria-label="SmartQuote workflow">' +
    '<span><b>1</b> Drop invoice PDFs</span>' +
    '<span><b>2</b> Auto-match exact codes</span>' +
    '<span><b>3</b> Review exceptions</span>' +
    '<span><b>4</b> Price &amp; approve</span></div></section>' +
    '<section class="panel" id="quoteGoLiveStatusPanel">' +
    '<div class="section-head"><div><h3>Customer quotation readiness</h3>' +
    '<p>See exactly what is still needed before the first approved customer PDF can be issued.</p></div>' +
    '<button type="button" class="button button-outline" id="quoteGoLiveRefresh">Check readiness</button></div>' +
    '<div id="quoteGoLiveStatus" aria-live="polite">Checking pricing and commercial setup…</div></section>' +
    '<section class="panel" id="unifiedDraftPanel">' +
    '<h3 id="unifiedDraftTitle">New quotation draft</h3>' +
    '<div class="notice" id="quoteCoordinatorGuide" role="status" aria-live="polite"></div>' +
    '<p>Start with a customer and equipment, save, then preview the Silver, Gold or Platinum price. '+ 
    'A customer PDF is available only after commercial approval.</p>' +
    '<form id="unifiedSiteSearch"><label>Find a site already recorded in Contracts OS ' +
    '<input name="q" minlength="2" maxlength="100" placeholder="Search recorded site name" required></label> ' +
    '<button class="button button-outline" type="submit">Find site</button></form>' +
    '<div id="unifiedSiteResults" aria-live="polite"></div>' +
    '<p class="fine-print">A recorded site label is not proof of the legal customer or current cover.</p>' +
    '<form id="unifiedDraftForm">' +
    '<input type="hidden" name="source_contract_id" value="">' +
    '<div class="form-grid">' +
    '<label>Customer <input name="customer" maxlength="250" required></label>' +
    '<label>Site <input name="site" maxlength="250" required></label>' +
    '<label>Contact <input name="contact" maxlength="250"></label>' +
    '<label>Maintenance cover <select name="tier"><option>Gold</option><option>Silver</option><option>Platinum</option></select></label>' +
    '<label>Term (years) <select name="term_years"><option value="1">1</option><option value="2">2</option><option value="3">3</option><option value="4">4</option><option value="5">5</option></select></label>' +
    '<label>Discount % <input name="discount_percent" type="number" min="0" max="100" step="0.01" value="0" required></label>' +
    '<label>Contract start <input name="contract_start" type="date"></label>' +
    '<label>Contract end <input name="contract_end" type="date"></label>' +
    '</div></form>' +
    '<h4>Start from a sales invoice (optional)</h4>' +
    '<p>Drag and drop up to 12 sales invoice PDFs. Codes matching priced machines in ' +
    'the unified Master are added to your draft automatically. Only unmatched ' +
    'codes need a coordinator to check the machine identity. Quantities and ' +
    'serial numbers remain to be verified before a quote can be issued.</p>' +
    '<form id="unifiedInvoiceImport"><label>Sales invoice PDF files ' +
    '<input name="files" type="file" accept=".pdf,application/pdf" multiple required></label>' +
    '<div id="unifiedInvoiceDropzone" class="pulse-invoice-drop" role="button" tabindex="0" ' +
    'aria-label="Drop one or more invoice PDFs here or press Enter to choose PDF files">' +
    '<strong>Drag and drop your sales invoice PDFs here</strong>' +
    '<p class="fine-print">Or click to select files. Up to 12 PDFs, ' +
    '20 MB each and 60 MB total. Exact Master machine-code matches are automatic; ' +
    'spare parts are excluded and unmatched codes are flagged for review.</p>' +
    '</div>' +
    '<button class="button button-primary" type="submit">Import &amp; match equipment</button></form>' +
    '<div id="unifiedInvoiceResults" role="status" aria-live="polite"></div>' +
    '<h4>Equipment lines</h4>' +
    '<form id="unifiedCatalogueSearch"><label>Find equipment in the unified Master (code or model) ' +
    '<input name="q" minlength="2" maxlength="100" required placeholder="Type a machine code or name"></label> ' +
    '<button type="submit" class="button button-outline">Find equipment</button></form>' +
    '<div id="unifiedCatalogueResults" aria-live="polite"></div>' +
    '<div id="unifiedEquipmentTable"></div>' +
    '<div id="unifiedQuantityReview" aria-live="polite"></div>' +
    '<form id="unifiedEquipmentAdd">' +
    '<div class="form-grid">' +
    '<label>Equipment description <input name="description" maxlength="400" required></label>' +
    '<label>Product code <input name="item_code" maxlength="100"></label>' +
    '<label>Serial number (single machine) <input name="serial" maxlength="120"></label>' +
    '<label>Multiple serial numbers <textarea name="serial_numbers" maxlength="64000" rows="2" placeholder="Optional: one per line or comma-separated"></textarea></label>' +
    '<label>Equipment cover starts <input name="cover_start" type="date"></label>' +
    '<label>Quantity <input name="quantity" type="number" min="1" max="10000" step="1" value="1" required></label>' +
    '</div><button type="submit" class="button button-outline">Add equipment line</button> ' +
    '<button type="button" class="button button-outline" id="unifiedCancelEquipmentEdit" hidden>Cancel edit</button></form>' +
    '<div style="display:flex;gap:0.6rem;flex-wrap:wrap;margin-top:1rem">' +
    '<button type="button" class="button button-primary" id="unifiedSaveAndPrice">Save &amp; calculate internal quote</button>' +
    '<button type="button" class="button button-outline" id="unifiedDraftSave">Save draft only</button>' +
    '<button type="button" class="button button-outline" id="unifiedDraftNew">New draft</button>' +
    '<button type="button" class="button button-outline" id="unifiedDraftPrice">Check customer-issue pricing</button></div>' +
    '<p id="unifiedDraftFeedback" role="status" aria-live="polite"></p>' +
    '<div id="unifiedPricePanel" aria-live="polite"></div>' +
    '</section>' +
    '<section class="panel" id="quoteQuickDraftPanel">' +
    '<h3>Your maintenance quotation estimate</h3>' +
    '<p>Use the selected machines and the single Master Price List. ' +
    'Review the proposed service rates, then calculate or download an ' +
    'internal quotation PDF. Customer issue requires separate approval.</p>' +
    '<div id="quoteQuickDraftHost"></div></section>' +
    '<section class="panel"><h3>Equipment price source evidence</h3>' +
    '<p>The unified Master is the active price authority after administrator activation. ' +
    'Historical August Master and Sage source comparisons remain available for audit, ' +
    'but are no longer separate price lists for coordinators to maintain.</p>' +
    '<button type="button" class="button button-outline" id="rrpPriorityStatusLoad">Check source coverage</button>' +
    '<div id="rrpPriorityStatus" aria-live="polite"></div></section>' +
    '<section class="panel" id="quoteV10SourcePanel" hidden>' +
    '<h3>Original V10 &amp; August Price Source Setup</h3>' +
    '<div id="quoteV10SourceHost"></div></section>' +
    '<section class="panel" id="quoteCommercialSetupPanel" hidden>' +
    '<h3>Customer Quotation — Commercial Setup</h3>' +
    '<div id="quoteCommercialSetupHost"></div></section>' +
    '<section class="panel" id="quoteUnifiedBookPanel" hidden>' +
    '<h3>Unified Master Price List</h3>' +
    '<p>One exact-code price source for Pulse Fitness. The initial combined list ' +
    'contains Sage items and preferred Master List Prices. Later imports update only ' +
    'matching product codes, with permanent version history.</p>' +
    '<div id="quoteUnifiedBookHost"></div></section>' +
    '<section class="panel" id="quoteSageRefreshPanel" hidden>' +
    '<h3>Sage Price List Refresh</h3>' +
    '<p>Upload a complete Sage Sales Price export, review price changes and activate ' +
    'a new dated snapshot. No existing quotations or Sage records will be changed.</p>' +
    '<div id="quoteSageRefreshHost"></div></section>' +
    '<section class="panel" id="quoteAdminPricePanel" hidden>' +
    '<h3>Administrator price corrections</h3>' +
    '<p>Edit the effective equipment price for an exact item code. ' +
    'All changes require a reason, keep their history and never update Sage or the original master directly. ' +
    'New Sage/master snapshots require the amended price to be rechecked.</p>' +
    '<form id="quotePriceLookupForm"><label>Exact equipment code ' +
    '<input name="sku" required maxlength="100" placeholder="Enter item code"></label> ' +
    '<button class="button button-outline" type="submit">Load price</button></form>' +
    '<div id="quotePriceEditorDetail" aria-live="polite"></div></section>' +
    '<section class="panel"><h3>Equipment Master Price List &amp; Catalogue — source reconciliation</h3>' +
    '<p>Check current SKU duplicates, missing source RRPs, console/configuration issues and legacy mappings before quoting.</p>' +
    '<button type="button" class="button button-outline" id="quoteSourceAuditLoad">Review source catalogue</button>' +
    '<div id="quoteSourceAudit" aria-live="polite"></div></section>' +
    '<section class="panel"><h3>Quotation drafts</h3><div id="unifiedDraftList">Loading saved drafts…</div></section>' +
    '<section class="panel"><h3>Existing SmartQuote quotations</h3>' +
    '<div id="unifiedLegacyList">Checking the original SmartQuote source…</div>' +
    '<div id="unifiedLegacyDetail" aria-live="polite"></div></section>';
  document.querySelector('#quoteGoLiveRefresh').addEventListener('click', loadQuoteGoLiveStatus);
  loadQuoteGoLiveStatus().catch(()=>{});
  document.querySelector('#unifiedEquipmentAdd').addEventListener('submit', unifiedAddEquipment);
  document.querySelector('#unifiedEquipmentAdd').addEventListener('input', unifiedCoordinatorGuidance);
  document.querySelector('#unifiedEquipmentAdd').addEventListener('change', unifiedCoordinatorGuidance);
  document.querySelector('#unifiedInvoiceImport').addEventListener('submit', unifiedImportInvoiceEvidence);
  initUnifiedInvoiceDropzone();
  document.querySelector('#unifiedCancelEquipmentEdit').addEventListener('click', unifiedStopEquipmentEdit);
  document.querySelector('#unifiedSiteSearch').addEventListener('submit', unifiedSearchSites);
  document.querySelector('#unifiedDraftForm').elements.site.addEventListener('input', () => {
    const form = document.querySelector('#unifiedDraftForm');
    form.elements.source_contract_id.value = '';
    const host = document.querySelector('#unifiedSiteResults');
    if (host) host.textContent = 'Site manually edited. Source link cleared; verify independently.';
  });
  document.querySelector('#unifiedCatalogueSearch').addEventListener('submit', unifiedSearchCatalogue);
  document.querySelector('#unifiedDraftSave').addEventListener('click', unifiedSaveDraft);
  document.querySelector('#unifiedSaveAndPrice').addEventListener('click', unifiedSaveAndPrice);
  document.querySelector('#unifiedDraftNew').addEventListener('click', unifiedNewDraft);
  document.querySelector('#unifiedDraftPrice').addEventListener('click', unifiedPricePreview);
  document.querySelector('#quoteSourceAuditLoad').addEventListener('click', loadQuoteSourceAudit);
  document.querySelector('#rrpPriorityStatusLoad').addEventListener('click', loadRrpPriorityStatus);
  document.querySelector('#quotePriceLookupForm').addEventListener('submit', quotePriceLookup);
  showQuotePriceEditorIfAdmin().catch(()=>{});
  if(typeof initQuoteQuickDraft==='function')initQuoteQuickDraft();
  document.querySelector('#unifiedDraftForm').addEventListener('input', unifiedClearPrice);
  document.querySelector('#unifiedDraftForm').addEventListener('change', unifiedClearPrice);
  // A renewal from Action Centre may pass only a source site label and its
  // existing record ID. Legal customer name, equipment and prices are NEVER
  // inferred; saveDraft verifies that the linked site still matches exactly.
  if (window.unifiedSourceFromAction) {
    const selected=window.unifiedSourceFromAction;
    window.unifiedSourceFromAction=null;
    const form=document.querySelector('#unifiedDraftForm');
    if (form && Number.isSafeInteger(selected.contract_id) && selected.contract_id>0) {
      form.elements.site.value=String(selected.site_label||'');
      form.elements.source_contract_id.value=String(selected.contract_id);
      document.querySelector('#unifiedSiteResults').textContent=
        'Source site selected from a renewal task. Confirm the legal customer, equipment, cover and price independently.';
      form.elements.customer.focus();
    }
  }
  unifiedLastSavedDraftState=unifiedDraftSnapshot();
  unifiedLatestPricePreview=null;
  unifiedSavePending=false;
  unifiedGuardNavigation();
  renderUnifiedEquipment();
  unifiedCoordinatorGuidance();
  // Independent requests: a disconnected original SmartQuote must never hide draft creation.
  await Promise.allSettled([loadUnifiedDrafts(), loadUnifiedLegacyQuotes()]);
}


function unifiedStopEquipmentEdit() {
  const form=document.querySelector('#unifiedEquipmentAdd');
  unifiedEditingEquipmentIndex=null;
  if(form) {
    form.reset();
    const button=form.querySelector('[type="submit"]');
    if(button)button.textContent='Add equipment line';
    const cancel=form.querySelector('#unifiedCancelEquipmentEdit');
    if(cancel)cancel.hidden=true;
    delete form.dataset.invoiceSku;
    delete form.dataset.invoiceSourceId;
    delete form.dataset.invoicePages;
    delete form.dataset.invoiceMatchConfirmed;
    delete form.dataset.invoiceConfirmedDescription;
    delete form.dataset.invoiceMatchMethod;
  }
  unifiedCoordinatorGuidance();
}

function renderUnifiedEquipment() {
  const host=document.querySelector('#unifiedEquipmentTable');
  if(!host || view!=='quoting')return;
  // A coordinator edit must invalidate any previously calculated quick quote.
  if(typeof quickInvalidate==='function')quickInvalidate();
  const rows=unifiedEquipment.map((item,i)=>
    '<tr><td>'+esc(item.description)+'</td><td>'+
    esc(item.item_code)+
    (item.source_import_id?
      '<p class="fine-print">Invoice #'+esc(item.source_import_id)+
      (item.source_pages?.length?' · page '+esc(item.source_pages.join(', ')):'')+
      '</p>'+
      (item.invoice_match_confirmed?
        '<p class="fine-print">'+(item.invoice_match_method==='auto_exact_master'?
          'Automatically matched exact Master code':'Coordinator-confirmed invoice/Master code match')+
        (item.invoice_match_confirmed_by?' · '+esc(item.invoice_match_confirmed_by):'')+
        '</p>':'<p class="notice warning">Invoice match not confirmed</p>'):'')+'</td>'+
    '<td>'+esc(Array.isArray(item.serial_numbers)&&item.serial_numbers.length?
      (item.serial_numbers.slice(0,2).join(', ')+
      (item.serial_numbers.length>2?' +'+(item.serial_numbers.length-2)+' more':'')):
      item.serial||'Not confirmed')+'</td><td>'+
    esc(item.cover_start||'Contract start')+'</td><td>'+esc(item.quantity)+
    (item.quantity_verified===false?'<p class="fine-print">Quantity to verify</p>':'')+
    '</td>'+
    '<td><button class="button button-outline" type="button" data-edit-line="'+i+'">Edit</button> '+
    '<button class="button button-outline" type="button" data-remove-line="'+i+'">Remove</button></td></tr>'
  ).join('');
  host.innerHTML=
    '<div style="overflow-x:auto"><table class="data-table"><thead><tr>'+
    '<th>Machine</th><th>Code</th><th>Serial</th><th>Cover starts</th><th>Qty</th><th></th>'+
    '</tr></thead><tbody>'+
    (rows||'<tr><td colspan="6">No equipment added yet.</td></tr>')+
    '</tbody></table></div>'+
    (unifiedRemovedEquipment?
      '<button class="button button-outline" type="button" id="unifiedUndoEquipmentRemove">'+
      'Undo last removal</button>':'');
  unifiedReviewImportedQuantities();
  host.querySelectorAll('[data-edit-line]').forEach(button=>button.addEventListener('click',()=>{
    const index=Number(button.dataset.editLine);
    if(!Number.isSafeInteger(index)||index<0||index>=unifiedEquipment.length)return;
    const item=unifiedEquipment[index];
    const form=document.querySelector('#unifiedEquipmentAdd');
    if(!form)return;
    for(const key of ['description','item_code','serial','cover_start','quantity'])
      form.elements[key].value=String(item[key]??'');
    if(form.elements.serial_numbers)
      form.elements.serial_numbers.value=Array.isArray(item.serial_numbers)&&
        item.serial_numbers.length>1?item.serial_numbers.join('\n'):'';
    if(item.source_import_id){
      form.dataset.invoiceSku=String(item.item_code||'').trim().toUpperCase();
      form.dataset.invoiceSourceId=String(item.source_import_id);
      form.dataset.invoicePages=JSON.stringify(item.source_pages||[]);
      if(item.invoice_match_confirmed===true){
        form.dataset.invoiceMatchConfirmed='yes';
        form.dataset.invoiceMatchMethod=String(item.invoice_match_method||'manual_confirmed');
        form.dataset.invoiceConfirmedDescription=String(item.description||'');
      } else {
        delete form.dataset.invoiceMatchConfirmed;
        delete form.dataset.invoiceConfirmedDescription;
        delete form.dataset.invoiceMatchMethod;
      }
    } else {
      delete form.dataset.invoiceSku;
      delete form.dataset.invoiceSourceId;
      delete form.dataset.invoicePages;
      delete form.dataset.invoiceMatchConfirmed;
      delete form.dataset.invoiceConfirmedDescription;
      delete form.dataset.invoiceMatchMethod;
    }
    unifiedEditingEquipmentIndex=index;
    const submit=form.querySelector('[type="submit"]');
    if(submit)submit.textContent='Save equipment changes';
    const cancel=form.querySelector('#unifiedCancelEquipmentEdit');
    if(cancel)cancel.hidden=false;
    const feedback=document.querySelector('#unifiedDraftFeedback');
    if(feedback)feedback.textContent='Editing equipment line '+(index+1)+
      '. Save equipment changes before calculating the quote.';
    form.elements.serial.focus();
  }));
  host.querySelectorAll('[data-remove-line]').forEach(button=>button.addEventListener('click',()=>{
    const index=Number(button.dataset.removeLine);
    if(!Number.isSafeInteger(index)||index<0||index>=unifiedEquipment.length)return;
    unifiedRemovedEquipment={item:{...unifiedEquipment[index]},index};
    unifiedEquipment.splice(index,1);
    unifiedStopEquipmentEdit();
    unifiedClearPrice();
    renderUnifiedEquipment();
  }));
  const undo=host.querySelector('#unifiedUndoEquipmentRemove');
  if(undo)undo.addEventListener('click',()=>{
    const removed=unifiedRemovedEquipment;
    if(!removed||unifiedEquipment.length>=500)return;
    unifiedEquipment.splice(Math.min(removed.index,unifiedEquipment.length),0,removed.item);
    unifiedRemovedEquipment=null;
    unifiedClearPrice();
    renderUnifiedEquipment();
  });
  unifiedCoordinatorGuidance();
}

function unifiedReviewImportedQuantities(){
  const host=document.querySelector('#unifiedQuantityReview');
  if(!host||view!=='quoting')return;
  const needs=unifiedEquipment.map((item,index)=>({item,index}))
    .filter(({item})=>item.invoice_match_method==='auto_exact_master' &&
      item.quantity_verified!==true);
  if(!needs.length){host.innerHTML='';return;}
  host.innerHTML='<section class="review-box">'+
    '<h3>Review imported equipment · '+esc(needs.length)+' line(s)</h3>'+
    '<p>Exact Master machine codes were matched automatically. The quantities '+
    'and serials shown below are suggestions transcribed from the invoice or '+
    'delivery note. Check them against the original PDFs and confirm in one action.</p>'+
    '<div style="overflow-x:auto"><table class="data-table">'+
    '<thead><tr><th>Matched machine</th><th>Qty from document</th>'+
    '<th>Serial numbers from document (edit as needed)</th></tr></thead><tbody>'+
    needs.map(({item,index})=>'<tr><td>'+esc(item.item_code)+' · '+
      esc(item.description)+'</td><td><input type="number" min="1" max="10000" '+
      'step="1" value="'+esc(item.quantity)+'" data-verify-quantity="'+index+'" '+
      'aria-label="Confirmed quantity for '+esc(item.item_code)+'" style="width:90px"></td>'+
      '<td><textarea data-verify-serial="'+index+'" rows="2" maxlength="64000" '+
      'aria-label="Serials for '+esc(item.item_code)+'" '+
      'style="min-width:240px;width:100%">'+
      esc(Array.isArray(item.serial_numbers)&&item.serial_numbers.length?
        item.serial_numbers.join('\n'):item.serial||'')+
      '</textarea></td></tr>').join('')+
    '</tbody></table></div>'+
    '<button type="button" class="button button-primary" id="unifiedConfirmQuantities">'+
    'Confirm all equipment quantities and listed serials</button>'+
    '<p class="fine-print">One listed serial is required for each physical '+
    'unit to avoid the customer-issue serial exception. Unlisted units '+
    'remain visible for manager review; do not invent serial numbers.</p>'+
    '<p id="unifiedQuantityError" role="alert"></p></section>';
  host.querySelector('#unifiedConfirmQuantities').addEventListener('click',()=>{
    const error=host.querySelector('#unifiedQuantityError');
    const updates=[];
    const occupied=new Set(unifiedEquipment.filter(line=>line.quantity_verified===true)
      .flatMap(line=>Array.isArray(line.serial_numbers)&&line.serial_numbers.length?
        line.serial_numbers:[line.serial])
      .map(x=>String(x||'').trim().toUpperCase()).filter(Boolean));
    for(const {item,index} of needs){
      const amount=host.querySelector('[data-verify-quantity="'+index+'"]');
      const serialInput=host.querySelector('[data-verify-serial="'+index+'"]');
      const value=Number(amount.value);
      const serialNumbers=String(serialInput.value||'').split(/[,;\n]+/)
        .map(x=>x.trim()).filter(Boolean);
      if(!Number.isSafeInteger(value)||value<1||value>10000){
        error.textContent='Enter a whole-number quantity from 1 to 10,000 for '+item.item_code+'.';
        amount.focus();return;
      }
      if(serialNumbers.length>value||serialNumbers.length>500 ||
         serialNumbers.some(value=>value.length>120)){
        error.textContent='More serial numbers than units, or an overlong list for '+item.item_code+'.';
        serialInput.focus();return;
      }
      for(const serial of serialNumbers){
        if(occupied.has(serial.toUpperCase())){
          error.textContent='Repeated serial '+serial+'. Each unit must have a distinct serial.';
          serialInput.focus();return;
        }
        occupied.add(serial.toUpperCase());
      }
      updates.push({index,quantity:value,
        serial:serialNumbers[0]||'',serial_numbers:serialNumbers});
    }
    for(const update of updates){
      const item=unifiedEquipment[update.index];
      item.quantity=update.quantity;
      item.serial=update.serial;
      item.serial_numbers=update.serial_numbers;
      item.quantity_verified=true;
    }
    unifiedClearPrice();
    renderUnifiedEquipment();
    const note=document.querySelector('#unifiedDraftFeedback');
    if(note)note.textContent=updates.length+' imported equipment line(s) confirmed. '+
      'Complete the customer details and select Save & calculate internal quote.';
  });
}

function unifiedAddEquipment(event) {
  event.preventDefault();
  const form=event.currentTarget;
  const data=Object.fromEntries(new FormData(form).entries());
  const quantity=Number(data.quantity);
  const feedback=document.querySelector('#unifiedDraftFeedback');
  if(!Number.isSafeInteger(quantity)||quantity<1||quantity>10000){
    if(feedback)feedback.textContent='Enter a whole-number equipment quantity from 1 to 10,000.';
    return;
  }
  if(!String(data.description||'').trim()){
    if(feedback)feedback.textContent='Enter an equipment description.';
    return;
  }
  const editing=unifiedEditingEquipmentIndex;
  if(editing===null&&unifiedEquipment.length>=500){
    if(feedback)feedback.textContent='Maximum 500 equipment lines per draft.';
    return;
  }
  if(editing!==null&&(!Number.isSafeInteger(editing)||editing<0||editing>=unifiedEquipment.length)){
    unifiedStopEquipmentEdit();
    if(feedback)feedback.textContent='The equipment list changed. Select the line to edit again.';
    return;
  }
  const invoiceId=Number(form.dataset.invoiceSourceId||0);
  const sameCode=String(form.dataset.invoiceSku||'')===
    String(data.item_code||'').trim().toUpperCase();
  const sameDescription=String(form.dataset.invoiceConfirmedDescription||'').trim()===
    String(data.description||'').trim();
  const invoiceConfirmed=form.dataset.invoiceMatchConfirmed==='yes' &&
    sameCode && (form.dataset.invoiceMatchMethod==='auto_exact_master' ||
                 sameDescription);
  if(invoiceId>0 && sameCode && !invoiceConfirmed){
    if(feedback)feedback.textContent='The invoice code and Master machine must be '+
      'explicitly confirmed by the coordinator before this line can be linked. '+
      'Go back to Compare with Master and tick the confirmation box.';
    return;
  }
  const invoiceLinked=invoiceId>0 && Number.isSafeInteger(invoiceId) &&
    sameCode && invoiceConfirmed;
  const invoicePages=form.dataset.invoicePages?
    JSON.parse(form.dataset.invoicePages):[];
  const typedSerial=String(data.serial||'').trim();
  const parsedSerials=String(data.serial_numbers||'').trim()?
    String(data.serial_numbers).split(/[,;\n]+/).map(x=>x.trim()).filter(Boolean):
    (typedSerial?[typedSerial]:[]);
  if(parsedSerials.length>quantity || parsedSerials.length>500){
    if(feedback)feedback.textContent='More serial numbers than equipment units, or too many serials. Check the list.';
    return;
  }
  const local=new Set();
  for(const entry of parsedSerials){
    const key=entry.toUpperCase();
    if(entry.length>120 || local.has(key)){
      if(feedback)feedback.textContent='Duplicate or overlong serial number: '+entry.slice(0,60);
      return;
    }
    local.add(key);
    const duplicate=unifiedEquipment.findIndex((line,index)=>
      index!==editing&&(Array.isArray(line.serial_numbers)&&line.serial_numbers.length?
        line.serial_numbers:[line.serial]).some(x=>String(x||'').trim().toUpperCase()===key));
    if(duplicate!==-1){
      if(feedback)feedback.textContent='Serial '+entry+
        ' already exists on equipment line '+(duplicate+1)+'.';
      return;
    }
  }
  const serial=parsedSerials[0]||'';
  const prior=editing!==null?unifiedEquipment[editing]:null;
  const record={
    description:String(data.description).trim(),
    item_code:String(data.item_code||'').trim(),
    serial,
    serial_numbers:parsedSerials,
    cover_start:String(data.cover_start||''),
    quantity,
    annual_rate_percent:prior?.annual_rate_percent??null,
    fixed_annual_unit_gbp:prior?.fixed_annual_unit_gbp??null,
    quantity_verified:true,
    source_import_id:invoiceLinked?invoiceId:null,
    source_pages:invoiceLinked&&Array.isArray(invoicePages)?
      invoicePages:[],
    invoice_match_confirmed:invoiceLinked,
    invoice_match_method:invoiceLinked?
      String(form.dataset.invoiceMatchMethod||'manual_confirmed'):'',
  };
  if(editing!==null)unifiedEquipment[editing]=record;
  else unifiedEquipment.push(record);
  unifiedRemovedEquipment=null;
  unifiedStopEquipmentEdit();
  unifiedClearPrice();
  renderUnifiedEquipment();
  if(feedback)feedback.textContent=(editing!==null?'Equipment changes saved.':'Equipment line added.')+
    (quantity>parsedSerials.length?' Check any missing serial numbers before customer issue.':
      ' Save and calculate the draft to retain the changes.');
}

function unifiedNewDraft() {
  if(unifiedSavePending)return;
  if (unifiedEditingEquipmentIndex !== null) {
    const feedback=document.querySelector('#unifiedDraftFeedback');
    if(feedback)feedback.textContent='Save or cancel your equipment edit before starting another quotation.';
    return;
  }
  if(unifiedDraftHasUnsavedChanges() &&
      !window.confirm('Discard unsaved changes and start a new quotation?'))return;
  unifiedDraftSelected = null;
  unifiedEquipment = [];
  unifiedRemovedEquipment=null;
  unifiedStopEquipmentEdit();
  unifiedClearPrice();
  const form = document.querySelector('#unifiedDraftForm');
  if (form) form.reset();
  const heading = document.querySelector('#unifiedDraftTitle');
  if (heading) heading.textContent = 'New quotation draft';
  const feedback = document.querySelector('#unifiedDraftFeedback');
  if (feedback) feedback.textContent = '';
  unifiedLastSavedDraftState=unifiedDraftSnapshot();
  renderUnifiedEquipment();
}

async function unifiedSaveDraft() {
  const form = document.querySelector('#unifiedDraftForm');
  const feedback = document.querySelector('#unifiedDraftFeedback');
  const button = document.querySelector('#unifiedDraftSave');
  const combined = document.querySelector('#unifiedSaveAndPrice');
  if (!form || !form.reportValidity() || !feedback || !button || unifiedSavePending) return null;
  if (unifiedEditingEquipmentIndex!==null){
    feedback.textContent='Save or cancel the equipment line you are editing first.';
    return null;
  }
  if(unifiedHasPendingEquipmentInput()){
    feedback.textContent='You have started an equipment line that is not yet in the quote. Select Add equipment line first.';
    return null;
  }
  const data = Object.fromEntries(new FormData(form).entries());
  const payload = {
    customer:data.customer, site:data.site, contact:data.contact,
    tier:data.tier, term_years:Number(data.term_years), discount_percent:Number(data.discount_percent),
    contract_start:data.contract_start, contract_end:data.contract_end,
    source_contract_id:data.source_contract_id ? Number(data.source_contract_id) : null,
    equipment:unifiedEquipment
  };
  let url = '/api/quoting/drafts', method = 'POST';
  if (unifiedDraftSelected) {
    url += '/' + encodeURIComponent(unifiedDraftSelected.id);
    method = 'PUT';
    payload.revision = unifiedDraftSelected.revision;
  }
  unifiedSavePending=true;
  button.disabled = true;
  if (combined) combined.disabled = true;
  feedback.textContent = 'Saving…';
  try {
    const saved = await api(url, {method, headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)});
    unifiedDraftSelected = {id:saved.id, revision:saved.revision};
    unifiedLastSavedDraftState=unifiedDraftSnapshot();
    unifiedRemovedEquipment=null;
    unifiedClearPrice();
    feedback.textContent = 'Saved. This quotation remains unpriced and cannot be issued yet.';
    document.querySelector('#unifiedDraftTitle').textContent = 'Edit quotation draft';
    await loadUnifiedDrafts();
    return saved;
  } catch (error) {
    feedback.textContent = error.message + ' If another user saved changes, reload the draft.';
    return null;
  } finally {
    unifiedSavePending=false;
    button.disabled = false;
    if (combined) combined.disabled = false;
    unifiedCoordinatorGuidance();
  }
}

async function unifiedSaveAndPrice(){
  const result=await unifiedSaveDraft();
  // One connected workflow: save the real draft, reuse the one active Master
  // and prepare a clearly marked INTERNAL estimate without the old V10 gate.
  if(!result)return;
  if(typeof quickCopyEquipment==='function' &&
     typeof quickCalculate==='function'){
    quickCopyEquipment();
    await quickCalculate();
    document.querySelector('#quoteQuickDraftPanel')?.scrollIntoView({
      behavior:'smooth',block:'start'
    });
  }else{
    await unifiedPricePreview();
  }
}

async function loadUnifiedDrafts() {
  const host = document.querySelector('#unifiedDraftList');
  if (!host) return;
  try {
    const response = await api('/api/quoting/drafts?limit=100');
    if (view !== 'quoting' || !document.querySelector('#unifiedDraftList')) return;
    unifiedDraftRecords = response.items || [];
    host.innerHTML = unifiedDraftRecords.length
      ? '<div style="overflow-x:auto"><table class="data-table"><thead><tr><th>Customer</th><th>Site</th><th>Cover</th><th>Equipment lines</th><th>Updated</th><th></th></tr></thead><tbody>' +
        unifiedDraftRecords.map(d => '<tr><td>' + esc(d.customer) + '</td><td>' + esc(d.site) +
          '</td><td>' + esc(d.tier) + '</td><td>' + esc(d.equipment.length) +
          '</td><td>' + esc(d.updated_at) + '</td><td><button class="button button-outline" type="button" data-open-draft="' +
          esc(d.id) + '">Open draft</button></td></tr>').join('') +
        '</tbody></table></div>'
      : '<p>No drafts saved yet.</p>';
    host.querySelectorAll('[data-open-draft]').forEach(b => b.addEventListener('click', () => unifiedOpenDraft(b.dataset.openDraft)));
  } catch (error) {
    const target = document.querySelector('#unifiedDraftList');
    if (target) target.innerHTML = '<p class="notice warning">' + esc(error.message) + '</p>';
  }
}

async function unifiedOpenDraft(id) {
  const feedback = document.querySelector('#unifiedDraftFeedback');
  if (!feedback || unifiedSavePending) return;
  if(unifiedDraftHasUnsavedChanges() &&
      !window.confirm('Discard unsaved changes and open another quotation?'))return;
  try {
    // Fetch current revision, not the potentially stale paginated register snapshot.
    const draft = await api('/api/quoting/drafts/' + encodeURIComponent(id));
    if (view !== 'quoting' || !document.querySelector('#unifiedDraftForm')) return;
    const form = document.querySelector('#unifiedDraftForm');
    form.elements.customer.value = draft.customer;
    form.elements.site.value = draft.site;
    form.elements.source_contract_id.value = String(draft.source_contract_id || '');
    form.elements.contact.value = draft.contact;
    form.elements.tier.value = draft.tier;
    form.elements.term_years.value = String(draft.term_years || 1);
    form.elements.discount_percent.value = String(draft.discount_percent ?? 0);
    form.elements.contract_start.value = draft.contract_start || '';
    form.elements.contract_end.value = draft.contract_end || '';
    unifiedEquipment = draft.equipment.map(e => ({...e}));
    unifiedRemovedEquipment=null;
    unifiedStopEquipmentEdit();
    unifiedClearPrice();
    unifiedDraftSelected = {id:draft.id, revision:draft.revision};
    unifiedLastSavedDraftState=unifiedDraftSnapshot();
    document.querySelector('#unifiedDraftTitle').textContent = 'Edit quotation draft';
    feedback.textContent = 'Loaded draft revision ' + draft.revision + '. Recalculate prices before generating a customer quote.';
    renderUnifiedEquipment();
    document.querySelector('#unifiedDraftPanel').scrollIntoView({behavior:'smooth',block:'start'});
    void unifiedPricePreview();
  } catch(error) {
    feedback.textContent = error.message;
  }
}

async function loadUnifiedLegacyQuotes() {
  const host = document.querySelector('#unifiedLegacyList');
  if (!host) return;
  try {
    const state = await api('/api/quoting/status');
    if (!state.smartquote_connected) {
      host.textContent = 'The original SmartQuote database has not been connected to this pilot. Existing quotes are unchanged; native draft creation above remains available.';
      return;
    }
    const result = await api('/api/quoting/quotes?limit=100');
    if (view !== 'quoting' || !document.querySelector('#unifiedLegacyList')) return;
    host.innerHTML = '<p>' + esc(result.total) + ' historical quotations in the configured read-only source.</p>' +
      '<div style="overflow-x:auto"><table class="data-table"><thead><tr><th>Quote</th><th>Customer</th><th>Site</th><th>Cover</th><th>Status</th><th>Contract setup</th></tr></thead><tbody>' +
      (result.items || []).map(q => '<tr><td><button class="button button-outline" type="button" data-quote-id="' +
        esc(q.id) + '">' + esc(q.quote_number) + '</button></td><td>' + esc(q.customer) +
        '</td><td>' + esc(q.site) + '</td><td>' + esc(q.tier) + '</td><td>' + esc(q.status) + '</td><td>' +
        (q.status === 'Accepted' ? '<button class="button button-outline" type="button" data-intake-preview="' + esc(q.id) + '">Review handover</button>' : 'Available after acceptance') +
        '</td></tr>').join('') +
      '</tbody></table></div>';
    host.querySelectorAll('[data-quote-id]').forEach(b => b.addEventListener('click', () => unifiedShowLegacyQuote(b.dataset.quoteId)));
    host.querySelectorAll('[data-intake-preview]').forEach(b => b.addEventListener('click', () => unifiedPreviewHandover(b.dataset.intakePreview)));
  } catch (error) {
    const target = document.querySelector('#unifiedLegacyList');
    if (target) target.innerHTML = '<p class="notice warning">' + esc(error.message) + '</p>';
  }
}

async function unifiedShowLegacyQuote(id) {
  const host = document.querySelector('#unifiedLegacyDetail');
  if (!host) return;
  host.textContent = 'Loading saved quotation…';
  try {
    const record = await api('/api/quoting/quotes/' + encodeURIComponent(id));
    if (view !== 'quoting' || !document.querySelector('#unifiedLegacyDetail')) return;
    const equipment = record.assets.map(item =>
      '<tr><td>' + esc(item.name) + '</td><td>' + esc(item.sku) +
      '</td><td>' + esc(item.serial) + '</td><td>' + esc(item.quantity ?? '—') + '</td></tr>'
    ).join('');
    const versions = record.pdf_versions.map(item =>
      '<tr><td>' + esc(item.version) + '</td><td>' + esc(item.created) +
      '</td><td>' + esc(item.status) + '</td><td><code>' + esc(item.pdf_sha256) + '</code></td></tr>'
    ).join('');
    host.innerHTML = '<section class="panel"><h4>' + esc(record.quote_number) + ' · ' + esc(record.customer) +
      '</h4><p>Site: ' + esc(record.site) + ' · ' + esc(record.tier) + ' · ' + esc(record.status) +
      '</p><h4>Equipment</h4><div style="overflow-x:auto"><table class="data-table"><tbody>' +
      (equipment || '<tr><td>No saved equipment.</td></tr>') +
      '</tbody></table></div><h4>Archived PDF references</h4><div style="overflow-x:auto"><table class="data-table"><tbody>' +
      (versions || '<tr><td>No archived PDFs.</td></tr>') +
      '</tbody></table></div><p>Read-only historical quotation. Editing and commercial issuance remain in the original controlled SmartQuote pilot.</p></section>';
  } catch(error) {
    const target = document.querySelector('#unifiedLegacyDetail');
    if (target) target.innerHTML = '<p class="notice warning">' + esc(error.message) + '</p>';
  }
}



function unifiedInvoiceCandidates(record) {
  // Code recognition is evidence only. Never infer equipment identity, count,
  // warranty start, ownership, serials or eligibility from text extraction.
  const raw=record?.evidence?.equipment_codes||[];
  if(!Array.isArray(raw))return [];
  const matched=record?.catalogue_matches||{};
  const seen=new Map();
  const candidates=[];
  for(const item of raw) {
    if(!item||typeof item!=='object')continue;
    const sku=String(item.value||'').trim().toUpperCase();
    if(!/^[A-Z0-9][A-Z0-9 ._/#*()&+\-]{0,99}$/.test(sku))continue;
    const product=matched[sku]||{};
    const pages=Array.isArray(item.pages)?[...new Set(item.pages.filter(
      n=>Number.isSafeInteger(n)&&n>0&&n<10000
    ))].sort((a,b)=>a-b):[];
    if(seen.has(sku)){
      const existing=seen.get(sku);
      existing.pages=[...new Set(existing.pages.concat(pages))].sort((a,b)=>a-b).slice(0,30);
      continue;
    }
    const evidence={
      sku,
      pages,
      description:String(product.name||'').slice(0,250),
      identity_not_verified:true,
      quantity_not_inferred:true,
      serials_not_inferred:true,
    };
    seen.set(sku,evidence);
    candidates.push(evidence);
  }
  return candidates;
}

function initUnifiedInvoiceDropzone(){
  const zone=document.querySelector('#unifiedInvoiceDropzone');
  const form=document.querySelector('#unifiedInvoiceImport');
  const input=form?.elements.files;
  if(!zone||!input)return;
  const originalBackground=zone.style.background;
  const highlight=(active)=>{
    zone.style.background=active?'#e6f1fb':originalBackground;
    zone.style.borderColor=active?'#1e6ba8':'#879bb3';
  };
  zone.addEventListener('click',()=>input.click());
  zone.addEventListener('keydown',event=>{
    if(event.key==='Enter'||event.key===' '){
      event.preventDefault();input.click();
    }
  });
  for(const name of ['dragenter','dragover']){
    zone.addEventListener(name,event=>{
      event.preventDefault();event.stopPropagation();
      if(event.dataTransfer)event.dataTransfer.dropEffect='copy';
      highlight(true);
    });
  }
  zone.addEventListener('dragleave',event=>{
    event.preventDefault();event.stopPropagation();highlight(false);
  });
  zone.addEventListener('drop',event=>{
    event.preventDefault();event.stopPropagation();highlight(false);
    const files=Array.from(event.dataTransfer?.files||[]);
    const feedback=document.querySelector('#unifiedInvoiceResults');
    if(!files.length)return;
    if(files.some(file=>!/\.pdf$/i.test(file.name))){
      if(feedback)feedback.textContent='Drop PDF invoices only. Other file types cannot be read.';
      return;
    }
    const upload=new DataTransfer();
    for(const file of files)upload.items.add(file);
    input.files=upload.files;
    if(feedback)feedback.textContent=files.length+' PDF invoice(s) selected. Analysing…';
    // Reuse the existing guarded PDF reader, rather than a second parser.
    form.requestSubmit();
  });
}

function unifiedApplyExactInvoiceMatches(matches){
  // One click to import; only exact positively-priced machine SKUs are added.
  // The backend independently rechecks this match on save. A second upload of
  // the same PDF cannot silently double-count existing invoice source codes.
  const existing=new Set(unifiedEquipment.filter(line=>line.source_import_id)
    .map(line=>String(line.source_import_id)+'/'+String(line.item_code||'').trim().toUpperCase()));
  let added=0,already=0,limitReached=0;
  for(const match of (matches||[])){
    if(!match.auto_add_equipment || match.status!=='matched_equipment')continue;
    const code=String(match.sku||'').trim().toUpperCase();
    if(!code || !Number.isSafeInteger(match.source_import_id) || match.source_import_id<1)continue;
    const key=String(match.source_import_id)+'/'+code;
    if(existing.has(key)){already++;continue;}
    if(unifiedEquipment.length>=500){limitReached++;continue;}
    const suggested=Number(match.quantity_suggested);
    const quantity=Number.isSafeInteger(suggested)&&suggested>0&&suggested<=10000?
      suggested:1;
    const serialNumbers=(Array.isArray(match.serial_numbers_suggested)?
      match.serial_numbers_suggested:[]).map(x=>String(x||'').trim())
      .filter(x=>x&&x.length<=120).slice(0,Math.min(quantity,500));
    // A delivery note and invoice may describe the same physical machine.
    // Repeated serial evidence across different files is not another sale.
    const sourceSerials=new Set(serialNumbers.map(x=>x.toUpperCase()));
    const alreadyRepresented=serialNumbers.length>0&&unifiedEquipment.some(line=>
      String(line.item_code||'').trim().toUpperCase()===code &&
      (Array.isArray(line.serial_numbers)?line.serial_numbers:[line.serial]).some(
        serial=>sourceSerials.has(String(serial||'').trim().toUpperCase())
      ));
    if(alreadyRepresented){already++;continue;}
    unifiedEquipment.push({
      item_code:code,
      description:String(match.master_description||code).slice(0,400),
      serial:serialNumbers[0]||'', serial_numbers:serialNumbers,
      cover_start:'', quantity,
      source_import_id:match.source_import_id,
      source_pages:Array.isArray(match.source_pages)?match.source_pages:[],
      invoice_match_confirmed:true,
      invoice_match_method:'auto_exact_master',
      quantity_verified:false
    });
    existing.add(key);
    added++;
  }
  if(added){
    unifiedClearPrice();
    renderUnifiedEquipment();
  }
  return {added,already,limitReached};
}


async function unifiedImportInvoiceEvidence(event) {
  event.preventDefault();
  const fileInput=event.currentTarget.elements.files;
  const feedback=document.querySelector('#unifiedInvoiceResults');
  const button=event.currentTarget.querySelector('[type="submit"]');
  if(!fileInput||!feedback||!button)return;
  const files=Array.from(fileInput.files||[]);
  if(!files.length||files.length>12||files.some(file=>
      !/\.pdf$/i.test(file.name)||file.size>20000000||file.size===0)||
      files.reduce((sum,file)=>sum+file.size,0)>60000000){
    feedback.textContent='Choose 1–12 non-empty PDF invoices, maximum 20 MB each and 60 MB in total.';
    return;
  }
  button.disabled=true;
  feedback.textContent='Reading invoices and matching exact codes to the unified Master…';
  try{
    const payload=new FormData();
    files.forEach(file=>payload.append('files',file));
    const uploaded=await api('/api/imports/batch',{method:'POST',body:payload});
    const ready=(uploaded.results||[]).filter(item=>
      Number.isSafeInteger(Number(item.id))&&Number(item.id)>0&&
      item.status!=='Upload failed'
    );
    if(!ready.length)throw Error((uploaded.results||[]).map(x=>x.message).join('; ')||
      'No PDF invoices could be read.');
    const analysed=await Promise.all(ready.map(async item=>{
      try{
        const details=await api('/api/imports/'+encodeURIComponent(String(item.id)));
        return {id:Number(item.id),filename:item.filename,
          unread:details?.evidence?.unread_pages||[],
          warnings:details?.evidence?.reading_warnings||[]};
      }catch(error){
        return {id:Number(item.id),filename:item.filename,
          unread:[],warnings:['Invoice text review unavailable: '+error.message]};
      }
    }));
    // The backend reads the uploaded invoice evidence directly from the DB
    // and exact-matches it to the one activated Master. No client-side SKU
    // guesses, V10 service matching or one-by-one coordinator approvals.
    const matching=await api('/api/quoting/invoice-auto-match',{
      method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({import_ids:ready.map(x=>Number(x.id))})
    });
    if(view!=='quoting'||!document.querySelector('#unifiedInvoiceResults'))return;
    const matches=matching.results||[];
    const {added,already,limitReached}=unifiedApplyExactInvoiceMatches(matches);
    const filesById=new Map(analysed.map(x=>[x.id,x]));
    const statusLabel={
      matched_equipment:'Matched — added to equipment draft',
      matched_inventory_not_machine:'Matched — spare part or other inventory (excluded)',
      matched_unpriced_or_held:'Matched — price needs administrator review',
      unmatched:'No exact Master match — coordinator review required'
    };
    feedback.innerHTML=
      '<p><strong>'+esc(added)+'</strong> equipment codes added automatically, '+
      esc(already)+' already in this draft, '+
      esc(matching.counts.matched_inventory_not_machine||0)+
      ' matched inventory/parts excluded, '+
      esc(matching.counts.matched_unpriced_or_held||0)+
      ' matched but without an approved reference price, and '+
      esc(matching.counts.unmatched||0)+' unmatched codes for review.</p>'+
      (limitReached?'<p class="notice warning">'+esc(limitReached)+
        ' machine lines exceed the 500-line draft limit; review before continuing.</p>':'')+
      '<p class="fine-print">Exact Master SKU matches are accepted automatically. '+
      'Coordinator input is required only for unmatched equipment codes. '+
      'Check quantities and serial numbers before issuing a quotation. '+
      'Spare parts are not added as maintenance machines.</p>'+
      '<div style="overflow-x:auto"><table class="data-table">'+
      '<thead><tr><th>Invoice</th><th>Code</th><th>Master description</th>'+
      '<th>Match result</th><th></th></tr></thead><tbody>'+
      matches.map((match,i)=>{
        const file=filesById.get(match.source_import_id);
        return '<tr><td>'+esc(file?.filename||String(match.source_import_id))+
          ' · page '+esc(match.source_pages.join(', ')||'not located')+'</td>'+
          '<td>'+esc(match.sku)+'</td><td>'+esc(match.master_description||'—')+
          '</td><td>'+esc(statusLabel[match.status]||'Needs review')+'</td>'+
          '<td>'+(match.status==='unmatched'?
            '<button type="button" class="button button-outline" '+
            'data-review-unmatched="'+i+'">Review unmatched code</button>':
            '')+'</td></tr>';
      }).join('')+'</tbody></table></div>'+
      analysed.map(file=>{
        const messages=(file.warnings||[]);
        return '<p class="fine-print"><a href="/api/imports/'+
          encodeURIComponent(String(file.id))+
          '/source" target="_blank" rel="noopener">Review original '+esc(file.filename||'PDF')+
          '</a>'+(file.unread.length?' — '+esc(file.unread.length)+
          ' pages need manual reading':'')+
          (messages.length?' — '+esc(messages.map(x=>String(x).slice(0,150)).join('; ')):'')+
          '</p>';
      }).join('');
    feedback.querySelectorAll('[data-review-unmatched]').forEach(review=>
      review.addEventListener('click',()=>{
        const candidate=matches[Number(review.dataset.reviewUnmatched)];
        const form=document.querySelector('#unifiedEquipmentAdd');
        if(!candidate||!form)return;
        if(unifiedEditingEquipmentIndex!==null){
          const note=document.querySelector('#unifiedDraftFeedback');
          if(note)note.textContent='Complete the current equipment edit before reviewing another code.';
          return;
        }
        // This invoice code has no Master identity. Keep the source PDF
        // for visual reference, but never claim it is a verified match.
        form.elements.item_code.value=candidate.sku;
        form.elements.description.value='';
        form.elements.serial.value='';
        form.elements.quantity.value='1';
        form.elements.cover_start.value='';
        delete form.dataset.invoiceSku;
        delete form.dataset.invoiceSourceId;
        delete form.dataset.invoicePages;
        delete form.dataset.invoiceMatchConfirmed;
        delete form.dataset.invoiceConfirmedDescription;
        const note=document.querySelector('#unifiedDraftFeedback');
        if(note)note.textContent='Unmatched invoice code '+candidate.sku+
          ': verify the correct item code and machine description before adding manually. '+
          'No invoice match has been claimed.';
        form.elements.item_code.focus();
      })
    );
    fileInput.value='';
    const note=document.querySelector('#unifiedDraftFeedback');
    if(note&&added)note.textContent=added+' exact machine code(s) added automatically. '+
      'Check the quantity review table and then save and calculate.';
    if(added && document.querySelector('#unifiedQuantityReview')?.innerHTML){
      document.querySelector('#unifiedQuantityReview').scrollIntoView({
        behavior:'smooth',block:'start'
      });
    }
  }catch(error){
    feedback.textContent='Invoice processing needs attention: '+error.message+
      '. No new price calculation has been issued.';
  }finally{
    button.disabled=false;
  }
}

async function unifiedSearchCatalogue(event) {
  event.preventDefault();
  const form=event.currentTarget;
  const host=document.querySelector('#unifiedCatalogueResults');
  if(!host)return;
  const q=String(new FormData(form).get('q')||'').trim();
  if(q.length<2)return;
  host.textContent='Searching one unified Master Price List (spare parts excluded)…';
  try{
    const response=await api('/api/quoting/quick-draft/search?q='+
      encodeURIComponent(q)+'&limit=50');
    if(view!=='quoting'||!document.querySelector('#unifiedCatalogueResults'))return;
    unifiedCatalogueMatches=response.results||[];
    host.innerHTML=unifiedCatalogueMatches.length?
      '<p><strong>'+esc(response.matching_equipment_codes)+
      '</strong> potential equipment matches in unified Master v'+
      esc(response.price_book_revision)+
      '. These are product and price references, not approved maintenance cover.</p>'+
      '<div style="overflow-x:auto"><table class="data-table">'+
      '<thead><tr><th>Exact item code</th><th>Machine</th><th>Group</th>'+
      '<th>Reference price</th><th></th></tr></thead><tbody>'+
      unifiedCatalogueMatches.map((item,i)=>
        '<tr><td>'+esc(item.sku)+'</td><td>'+esc(item.name)+'</td>'+
        '<td>'+esc(item.group||'')+'</td>'+
        '<td>£'+esc(item.equipment_price_gbp)+'</td>'+
        '<td><button type="button" class="button button-outline" '+
        'data-use-catalogue="'+i+'">Use machine</button></td></tr>'
      ).join('')+'</tbody></table></div>':
      '<p>No eligible machine priced under that name or code in the unified Master. '+
      'You can still enter a manually verified machine for review, but a '+
      'missing or held Master price cannot produce a customer quotation.</p>';
    host.querySelectorAll('[data-use-catalogue]').forEach(button=>
      button.addEventListener('click',()=>{
        const choice=unifiedCatalogueMatches[Number(button.dataset.useCatalogue)];
        if(!choice)return;
        const equipmentForm=document.querySelector('#unifiedEquipmentAdd');
        if(!equipmentForm)return;
        equipmentForm.elements.description.value=choice.name||choice.sku;
        equipmentForm.elements.item_code.value=choice.sku;
        equipmentForm.elements.serial.value='';
        equipmentForm.elements.quantity.value='1';
        equipmentForm.elements.cover_start.value='';
        for(const attr of ['invoiceSku','invoiceSourceId','invoicePages',
                           'invoiceMatchConfirmed','invoiceConfirmedDescription',
                           'invoiceMatchMethod']){
          delete equipmentForm.dataset[attr];
        }
        unifiedCoordinatorGuidance();
        const feedback=document.querySelector('#unifiedDraftFeedback');
        if(feedback)feedback.textContent='Current Master machine selected. '+
          'Enter the actual quantity and serial where known, then add the line. '+
          'No maintenance rate has been commercially approved by this selection.';
        equipmentForm.elements.quantity.focus();
      })
    );
  }catch(error){
    host.innerHTML='<p class="notice warning">'+esc(error.message)+
      '. Check that the unified Master Price List is active. '+
      'Manual equipment entry remains available but is unpriced until verified.</p>';
  }
}

async function unifiedPreviewHandover(id) {
  const host = document.querySelector('#unifiedLegacyDetail');
  if (!host) return;
  host.textContent = 'Verifying the original accepted quotation and archived PDF…';
  try {
    const preview = await api('/api/quoting/quotes/' + encodeURIComponent(id) + '/intake-preview');
    const current = document.querySelector('#unifiedLegacyDetail');
    if (!current || view !== 'quoting') return;
    const issues = preview.readiness.missing || [];
    current.innerHTML =
      '<section class="panel"><h4>Contract setup handover — ' + esc(preview.quote_number) + '</h4>' +
      '<p>The original archived PDF has been checked for integrity. Pricing and customer acceptance still require coordinator verification.</p>' +
      '<p><strong>' + esc(preview.equipment_lines) + '</strong> equipment lines. ' +
      (preview.already_imported_id ? 'Already in setup worklist.' : 'Not yet added to setup worklist.') + '</p>' +
      '<h5>Required review</h5><ul>' +
      issues.map(issue => '<li>' + esc(issue) + '</li>').join('') +
      '</ul><button type="button" class="button button-primary" id="unifiedConfirmHandover">' +
      (preview.already_imported_id ? 'Open existing setup worklist' : 'Add to contract setup review') + '</button></section>';
    current.querySelector('#unifiedConfirmHandover').addEventListener('click', async e => {
      const button = e.currentTarget;
      if (preview.already_imported_id) {
        setView('accepted_quotes');
        return;
      }
      button.disabled = true;
      try {
        const result = await api('/api/quoting/quotes/' + encodeURIComponent(id) + '/intake', {method:'POST'});
        current.innerHTML = '<p>Accepted quote added to contract setup review (intake ' +
          esc(result.intake_id) + '). No Sicon records have been changed.</p>' +
          '<button type="button" id="unifiedGoToSetups" class="button button-primary">Open accepted quotes</button>';
        current.querySelector('#unifiedGoToSetups').addEventListener('click', () => setView('accepted_quotes'));
      } catch(error) {
        button.disabled = false;
        const p = document.createElement('p');
        p.className = 'notice warning';
        p.textContent = error.message;
        current.append(p);
      }
    });
  } catch(error) {
    const current = document.querySelector('#unifiedLegacyDetail');
    if (current) current.innerHTML = '<p class="notice warning">' + esc(error.message) + '</p>';
  }
}


function unifiedClearPrice() {
  unifiedLatestPricePreview=null;
  const host = document.querySelector('#unifiedPricePanel');
  if (host) host.innerHTML = '';
  unifiedCoordinatorGuidance();
}

async function unifiedPricePreview() {
  const host = document.querySelector('#unifiedPricePanel');
  if (!host) return;
  if (!unifiedDraftSelected) {
    host.textContent = 'Save the quotation draft before checking customer-issue pricing.';
    return;
  }
  const form = document.querySelector('#unifiedDraftForm');
  const data = Object.fromEntries(new FormData(form).entries());
  const original = unifiedDraftRecords.find(q => q.id === unifiedDraftSelected.id);
  if (!original || original.revision !== unifiedDraftSelected.revision ||
      original.customer !== data.customer || original.site !== data.site ||
      Number(original.source_contract_id || 0) !== Number(data.source_contract_id || 0) ||
      original.contact !== data.contact || original.tier !== data.tier ||
      Number(original.term_years || 1) !== Number(data.term_years) ||
      Number(original.discount_percent || 0) !== Number(data.discount_percent) ||
      (original.contract_start || '') !== (data.contract_start || '') ||
      (original.contract_end || '') !== (data.contract_end || '') ||
      JSON.stringify(original.equipment.map(e => [e.item_code, e.description, e.serial, e.cover_start || '', e.quantity])) !==
      JSON.stringify(unifiedEquipment.map(e => [e.item_code, e.description, e.serial, e.cover_start || '', e.quantity]))) {
    host.textContent = 'Save any changes to this draft before requesting a price preview.';
    return;
  }
  host.textContent = 'Checking customer-release eligibility and approved maintenance tariffs…';
  try {
    const preview = await api('/api/quoting/drafts/' + encodeURIComponent(unifiedDraftSelected.id) + '/price-preview');
    if (view !== 'quoting' || !document.querySelector('#unifiedPricePanel')) return;
    if (preview.revision !== unifiedDraftSelected.revision || unifiedDraftHasUnsavedChanges()) {
      host.textContent = 'The draft changed while pricing. Save it again before calculating.';
      return;
    }
    unifiedLatestPricePreview=preview;
    unifiedCoordinatorGuidance();
    const comparisonLines=preview.lines.filter(line=>
      Boolean(line.source_price_comparison));
    const lines = preview.lines.map(line =>
      '<tr><td>' + esc(line.line) + '</td><td>' + esc(line.item_code) +
      '</td><td>' + esc(line.quantity) + '</td><td>' +
      (line.priced ? money(line.rrp) : '—') + '</td><td>' +
      esc((line.rrp_source || '').replaceAll('_',' ')) + '</td><td>' +
      (line.priced ? money(line.unit_annual) : '—') + '</td><td>' +
      (line.priced ? money(line.annual) : 'Not priced') + '</td><td>' +
      (line.sage_reference ? money(line.sage_reference.sage_sales_price) +
        ' · Sage source · ' + esc(line.sage_reference.source_date) +
        (line.sage_reference.review_overdue ? ' · Review overdue' : '') : '—') +
      '</td><td>' + esc(
        (line.source_price_comparison?
          'Master/Sage difference '+line.source_price_comparison.percentage_difference+
          '% (source comparison only); ':'')+
        (line.exception || (line.coverage_review || []).join('; ') || 'Review commercial terms')
      ) +
      '</td></tr>').join('');
    host.innerHTML =
      '<section class="panel"><h3>INTERNAL tariff preview · Not an approved quotation</h3>' +
      '<p><strong>Selected equipment price source:</strong> ' + esc(preview.rrp_source_priority) +
      '</p><p>Source tariff policy: ' + esc(preview.source_pricing_status) + ' · Snapshot ' +
      esc(preview.source_snapshot || 'not specified') + '</p>' +
      '<p><strong>' + esc(preview.priced_count) + ' of ' + esc(preview.line_count) +
      '</strong> lines priced from exact SKUs. ' +
      'Annual ' + money(preview.annual_partial) + '; monthly ' + money(preview.monthly_partial) +
      '; ' + (preview.staged.enabled ? 'staged cover period total ' :
        esc(preview.term_years) + '-year indicative total ') +
      (preview.term_partial === null ? 'Unavailable until both contract dates are set' : money(preview.term_partial)) +
      ' (partial if any line is unpriced).</p>' +
      (comparisonLines.length?
        '<p class="fine-print">'+esc(comparisonLines.length)+
        ' selected line(s) show both current Master and Sage item-code prices. '+
        'These sources can use different commercial bases; the stated Master '+
        'price remains the selected equipment basis for current SKUs. Sage '+
        'is the agreed price basis for older machines absent from the Master. '+
        'A difference does not require an additional percentage-based sign-off. '+
        'Maintain the normal tariff and customer-quote approval.</p>':'')+
      (preview.staged.enabled ?
        '<h4>Staged cover — inclusive calendar-year prorating</h4><div style="overflow-x:auto"><table class="data-table"><thead><tr><th>Start date</th><th>Units</th><th>Period charge</th></tr></thead><tbody>' +
        preview.staged.stages.map(stage => '<tr><td>' + esc(stage.start) + '</td><td>' + esc(stage.count) + '</td><td>' + money(stage.amount) + '</td></tr>').join('') +
        '</tbody></table></div>' : '') +
      '<div style="overflow-x:auto"><table class="data-table"><thead><tr>' +
      '<th>Line</th><th>SKU</th><th>Qty</th><th>Selected equipment price</th><th>RRP source/status</th><th>Annual/unit</th><th>Annual/line</th><th>Sage source price</th><th>Review</th>' +
      '</tr></thead><tbody>' + lines + '</tbody></table></div>' +
      '<h4>Commercial controls and exceptions</h4><ul>' +
      preview.issues.map(issue => '<li>' + esc(issue) + '</li>').join('') +
      '</ul><p>The preview is not itself customer-approved. Use the quotation controls below to check release readiness and obtain manager sign-off.</p></section>' +
      '<section class="panel" id="quoteTierComparison" aria-label="Silver Gold and Platinum comparison">'+
      '<p>Comparing Silver, Gold and Platinum for the same equipment…</p></section>';
    if (typeof showCustomerQuotePanel === 'function') showCustomerQuotePanel(preview);
    await unifiedShowTierComparison(preview);
  } catch(error) {
    const current = document.querySelector('#unifiedPricePanel');
    if (current) current.innerHTML = '<p class="notice warning">' + esc(error.message) + '</p>';
  }
}


async function unifiedShowTierComparison(quoted) {
  const holder=document.querySelector('#quoteTierComparison');
  if(!holder||!unifiedDraftSelected)return;
  const draftId=unifiedDraftSelected.id;
  try {
    const response=await api('/api/quoting/drafts/'+encodeURIComponent(draftId)+'/tier-comparison');
    if(view!=='quoting'||!document.querySelector('#quoteTierComparison')||
        !unifiedDraftSelected||unifiedDraftSelected.id!==draftId||
        response.revision!==unifiedDraftSelected.revision||
        quoted.revision!==response.revision)return;
    const options=(response.options||[]).filter(option=>
      ['Silver','Gold','Platinum'].includes(option.tier));
    const cells=options.map(option=>{
      const active=option.tier===response.selected_tier;
      const available=option.available&&option.complete_price;
      const details=available?
        '<p><strong>Annual '+money(option.annual_gbp)+
        '</strong> · Monthly '+money(option.monthly_gbp)+
        ' · Term '+(option.term_gbp===null?'Unavailable':money(option.term_gbp))+'</p>':
        '<p>Price requires review ('+esc(option.priced_lines)+' / '+
        esc(option.total_lines)+' lines priced). No complete totals shown.</p>'+
        ((option.blockers||[]).length?
          '<details><summary>What needs reviewing?</summary><ul>'+
          option.blockers.slice(0,8).map(item=>'<li>'+esc(item)+'</li>').join('')+
          '</ul></details>':'');
      const action=active?
        '<strong>Current selected cover</strong>':
        '<button class="button button-outline" type="button" '+
        'data-smartquote-tier="'+esc(option.tier)+'"'+
        (available?'':' disabled title="Resolve equipment pricing first"')+
        '>Use '+esc(option.tier)+' for this draft</button>';
      return '<div style="flex:1;min-width:180px;border:1px solid var(--border, #ccc);'+
        'border-radius:.5rem;padding:.8rem"><h4>'+esc(option.tier)+'</h4>'+
        details+action+'</div>';
    }).join('');
    holder.innerHTML='<h3>Compare maintenance cover options</h3>'+
      '<p>Same machines, quantities, discount and dates across all three '+
      'packages. Source tariff rules are not yet approved for customer issue.</p>'+
      '<div style="display:flex;flex-wrap:wrap;gap:.75rem">'+cells+'</div>'+
      '<p class="fine-print">Only complete pricing options show totals. '+
      'Selecting another package saves a new draft revision and recalculates '+
      'its price; it does not issue a customer quotation.</p>';
    holder.querySelectorAll('button[data-smartquote-tier]').forEach(button=>
      button.addEventListener('click',async ()=>{
        const selected=String(button.dataset.smartquoteTier||'');
        if(!['Silver','Gold','Platinum'].includes(selected))return;
        const field=document.querySelector('#unifiedDraftForm select[name="tier"]');
        if(!field)return;
        button.disabled=true;
        field.value=selected;
        await unifiedSaveAndPrice();
      }));
  } catch(error) {
    if(document.querySelector('#quoteTierComparison'))
      holder.textContent='The three-package comparison could not be loaded: '+
        error.message+'. The saved quotation preview above remains available.';
  }
}


async function unifiedSearchSites(event) {
  event.preventDefault();
  const host = document.querySelector('#unifiedSiteResults');
  if (!host) return;
  const phrase = String(new FormData(event.currentTarget).get('q') || '').trim();
  if (phrase.length < 2) return;
  host.textContent = 'Searching recorded sites — no legal customer names will be inferred.';
  try {
    const response = await api('/api/quoting/sites?q=' + encodeURIComponent(phrase) + '&limit=20');
    if (view !== 'quoting' || !document.querySelector('#unifiedSiteResults')) return;
    unifiedSiteMatches = response.items || [];
    if (!unifiedSiteMatches.length) {
      host.textContent = 'No recorded site matched. Enter details only from verified customer evidence.';
      return;
    }
    host.innerHTML = '<p>Confirm legal customer identity, cover and site references before quoting.</p>' +
      '<div style="overflow-x:auto"><table class="data-table"><thead><tr>' +
      '<th>Recorded site</th><th>Database status</th><th>Cover label</th>' +
      '<th>Contract ref</th><th>Source worksheet row</th><th></th></tr></thead><tbody>' +
      unifiedSiteMatches.map((item,i) => '<tr><td>' + esc(item.site_label) +
        '</td><td>' + esc(item.status) + '</td><td>' +
        esc(item.recorded_cover_label || 'Not recorded') + '</td><td>' +
        esc(item.recorded_contract_reference) + '</td><td>' +
        esc(item.source_sheet) + ' / ' + esc(item.source_row) +
        '</td><td><button type="button" class="button button-outline" data-site-index="' + i +
        '">Use recorded site</button></td></tr>').join('') + '</tbody></table></div>';
    host.querySelectorAll('[data-site-index]').forEach(button => button.addEventListener('click', () => {
      const item = unifiedSiteMatches[Number(button.dataset.siteIndex)];
      const form = document.querySelector('#unifiedDraftForm');
      if (!item || !form) return;
      form.elements.site.value = item.site_label;
      form.elements.source_contract_id.value = String(item.contract_id);
      host.textContent = 'Source link: ' + item.source_sheet + ' row ' + item.source_row +
        '. Legal customer and terms still need verification.';
      unifiedClearPrice();
      form.elements.customer.focus();
    }));
  } catch (error) {
    host.textContent = 'Source site lookup unavailable: ' + error.message +
      '. Do not substitute fictional customer data.';
  }
}

async function loadRrpPriorityStatus() {
  const host=document.querySelector('#rrpPriorityStatus');
  if (!host || view!=='quoting')return;
  host.textContent='Checking private August master and Sage source coverage…';
  try {
    const data=await api('/api/quoting/rrp-source/status');
    // A current master price alone is not a maintenance-quotable product.
    // The new summary also requires exact service identity, approved-source
    // eligibility and explicit console-variant evidence for the preview tier.
    const coverage=await api('/api/quoting/candidate-coverage').catch(()=>null);
    if(view!=='quoting'||!document.querySelector('#rrpPriorityStatus'))return;
    const labels={
      original_v10_catalogue_distinct_skus:'Original V10 distinct SKUs',
      august_2026_master_source_rows:'August 2026 master List Price rows',
      august_2026_master_distinct_skus:'August 2026 distinct SKUs',
      august_master_skus_not_in_v10:'August master SKUs not in V10',
      v10_skus_with_master_reference:'V10 SKUs covered by August List Price',
      v10_skus_with_conflicting_master_rows:'V10 SKUs with August conflicts',
      v10_skus_referred_to_sage:'V10 SKUs referred to Sage',
      v10_skus_absent_from_both_lists:'V10 SKUs absent from both sources'
    };
    const rows=Object.entries(labels).map(([key,label])=>
      '<tr><td>'+esc(label)+'</td><td>'+esc(data.counts[key]??'Not checked')+
      '</td></tr>').join('');
    host.innerHTML='<p>Verified master: '+esc(data.august_source_date)+
      ' · Sage snapshot '+(data.sage_loaded?'loaded':'not staged')+
      (data.sage_review_overdue?' · Sage review overdue':'')+'</p>'+
      '<div style="overflow-x:auto"><table class="data-table"><thead><tr>'+
      '<th>Source coverage</th><th>SKUs / rows</th></tr></thead><tbody>'+
      rows+'</tbody></table></div>'+
      (coverage?
        '<h4>Equipment candidates with unambiguous source-based maintenance pricing</h4>'+
        '<p><strong>'+esc(coverage.candidate_current_master_skus)+
        '</strong> current-master SKU candidates · <strong>'+
        esc(coverage.candidate_sage_fallback_skus)+
        '</strong> legacy Sage-fallback SKU candidates</p>'+
        '<p>'+esc(Object.entries(coverage.review_categories||{}).map(
          ([reason,count])=>count+' '+reason.replaceAll('_',' ')
        ).join(' · ')||'No additional source exceptions')+'</p>'+
        '<p class="fine-print">This count uses Gold, one unit, no discount. '+
        'It is NOT a quotation approval; every source, cover, customer, serial, '+
        'term and package still requires confirmation.</p>'
        :'<p class="fine-print">Quotable-equipment candidate count is unavailable.</p>')+
      '<p class="fine-print">The source precedence is confirmed. '+
      'Exact Sage prices are the business-approved equipment price basis for legacy '+
      'machines absent from the August Master. No extra Master-versus-Sage percentage '+
      'approval is needed. Approved maintenance rates and individual customer '+
      'quotation sign-off remain separate release gates.</p>';
    // The aggregate candidate count alone does not identify which SKUs
    // need administrator reconciliation. Expose the review-only CSV here;
    // the server independently enforces a named Admin and never exports
    // equipment prices, real customer data or issued quotations.
    const session=await api('/api/pilot/me').catch(()=>null);
    if(session?.pilot && session.role==='Admin' && view==='quoting' &&
       document.querySelector('#rrpPriorityStatus')===host){
      const link=document.createElement('a');
      link.href='/api/quoting/candidate-review.csv';
      link.download='Pulse_SmartQuote_Catalogue_Review.csv';
      link.className='button button-outline';
      link.textContent='Download SKUs requiring pricing and catalogue review';
      host.appendChild(link);
      if(data.sage_loaded){
        const equipment=document.createElement('a');
        equipment.href='/api/quoting/source-reconciliation/equipment.csv';
        equipment.download='Pulse_SmartQuote_Equipment_Reconciliation.csv';
        equipment.className='button button-outline';
        equipment.textContent='Review machine prices — Master, Sage and V10';
        equipment.title='Machine-focused source review; excludes unrelated Sage-only spare parts';
        host.appendChild(equipment);
        const full=document.createElement('a');
        full.href='/api/quoting/source-reconciliation.csv';
        full.download='Pulse_SmartQuote_Sage_Master_Full_Reconciliation.csv';
        full.className='button button-outline';
        full.textContent='Full Sage inventory audit (including spare parts)';
        full.title='Administrator reference only; not required for normal machine quotation review';
        host.appendChild(full);
        const caveat=document.createElement('p');
        caveat.className='fine-print';
        caveat.textContent='Most Sage item codes are parts or other inventory, not maintainable machines. '+
          'The machine report prioritises V10, Master and potential Sage equipment groups. '+
          'All new equipment still requires unique service mapping and commercial sign-off.';
        host.appendChild(caveat);
        const counts=await api('/api/quoting/source-reconciliation/summary').catch(()=>null);
        if(counts && view==='quoting' && document.querySelector('#rrpPriorityStatus')===host){
          const summary=document.createElement('p');
          summary.className='fine-print';
          summary.textContent=String(counts.equipment_review_skus)+' potential equipment-review codes; '+
            String(counts.sage_inventory_reference_only_skus)+' inventory-only codes kept out of the machine worklist.';
          host.appendChild(summary);
        }
      }
      // The historical quote workbook provides rate-band evidence only.
      // Do not treat matching percentages as approved Silver/Gold/Platinum.
      const parity=await api('/api/quoting/legacy-method-parity').catch(()=>null);
      if(parity && view==='quoting' && document.querySelector('#rrpPriorityStatus')===host){
        const audit=document.createElement('p');
        audit.className='fine-print';
        audit.textContent='Historical maintenance rate comparison: '+
          parity.matching_rate_patterns+' of '+
          parity.historical_rate_groups_tested+' group bands match the old quote workbook. '+
          (parity.rate_review_required?'Rate discrepancies need manager review. ':'')+
          'This does not approve tariffs, Stepmill exceptions or Silver/Gold/Platinum package factors.';
        host.appendChild(audit);
      }
    }
  } catch(error) {
    host.textContent='Source coverage unavailable: '+error.message+
      '. Stage and pin the original August 2026 source before relying on RRP prices.';
  }
}

async function showQuotePriceEditorIfAdmin() {
  const session=await api('/api/pilot/me');
  const panel=document.querySelector('#quoteAdminPricePanel');
  if(panel && view==='quoting' && session?.pilot && session.role==='Admin') {
    panel.hidden=false;
    const v10Panel=document.querySelector('#quoteV10SourcePanel');
    if(v10Panel && typeof initV10SourceSetup==='function'){
      v10Panel.hidden=false;
      initV10SourceSetup().catch(error=>{
        const host=document.querySelector('#quoteV10SourceHost');
        if(host)host.textContent=error.message;
      });
    }
    const commercialPanel=document.querySelector('#quoteCommercialSetupPanel');
    if(commercialPanel && typeof initQuoteCommercialSetup==='function'){
      commercialPanel.hidden=false;
      initQuoteCommercialSetup().catch(error=>{
        const host=document.querySelector('#quoteCommercialSetupHost');
        if(host)host.textContent=error.message;
      });
    }
    const priceBookPanel=document.querySelector('#quoteUnifiedBookPanel');
    if(priceBookPanel && typeof initQuotePriceBook==='function'){
      priceBookPanel.hidden=false;
      initQuotePriceBook().catch(error=>{
        const host=document.querySelector('#quoteUnifiedBookHost');
        if(host)host.textContent='Unified Master unavailable: '+error.message;
      });
    }
    const refreshPanel=document.querySelector('#quoteSageRefreshPanel');
    if(refreshPanel && typeof initQuoteSageRefresh === 'function'){
      refreshPanel.hidden=false;
      initQuoteSageRefresh().catch(error=>{
        const host=document.querySelector('#quoteSageRefreshHost');
        if(host)host.textContent=error.message;
      });
    }
  }
}

async function quotePriceLookup(event) {
  event.preventDefault();
  const code=String(new FormData(event.currentTarget).get('sku')||'').trim().toUpperCase();
  const host=document.querySelector('#quotePriceEditorDetail');
  if(!host||!code)return;
  host.textContent='Checking current source price and audit history…';
  quotePriceEditorSelection=null;
  try {
    const record=await api('/api/quoting/prices/'+encodeURIComponent(code));
    if(view!=='quoting'||!document.querySelector('#quotePriceEditorDetail'))return;
    quotePriceEditorSelection=record;
    renderQuotePriceEditor(record);
  } catch(error) {host.textContent=error.message;}
}

function renderQuotePriceEditor(record) {
  const host=document.querySelector('#quotePriceEditorDetail');
  if(!host)return;
  const history=(record.history||[]).map(event=>
    '<tr><td>'+esc(event.at)+'</td><td>'+esc(event.actor)+
    '</td><td>'+esc(event.action)+'</td><td>'+esc(
      event.before_gbp===null?'—':money(event.before_gbp))+'</td><td>'+
    esc(event.after_gbp===null?'—':money(event.after_gbp))+
    '</td><td>'+esc(event.reason)+'</td></tr>').join('');
  host.innerHTML=
    '<p><strong>'+esc(record.sku)+'</strong> · Source: '+esc(record.source_kind)+
    ' · Original: '+money(record.source_price_gbp)+
    ' · Current effective price: '+money(record.effective_price_gbp)+
    ' · Revision '+esc(record.revision)+
    (record.override_status==='source_changed_review_required'?
      ' · Source changed: reassess this amendment before quoting':'')+'</p>'+
    '<form id="quotePriceChangeForm"><div class="form-grid">'+
    '<label>New equipment price (£) <input name="price_gbp" type="number" '+
      'min="0.01" max="1000000" step="0.01" required value="'+
      esc(record.effective_price_gbp??record.source_price_gbp) +'"></label>'+
    '<label>Change reason <input name="reason" minlength="12" maxlength="500" required '+
      'placeholder="Why has the equipment price changed?"></label>'+
    '</div><button class="button button-primary" type="submit">Save price revision</button>'+
    (record.override_active?
      ' <button class="button button-outline" id="quotePriceRevert" type="button">Revert to source price</button>':'')+
    '</form><p class="fine-print">This is a local Contracts OS price revision only. '+
    'The Sage export, August master and existing issued quotations remain unchanged.</p>'+
    '<p id="quotePriceEditFeedback" role="status"></p>'+
    '<h4>Price amendment history</h4><div style="overflow-x:auto"><table class="data-table">'+
    '<thead><tr><th>Date</th><th>Admin</th><th>Action</th><th>Old price</th>'+
    '<th>New price</th><th>Reason</th></tr></thead><tbody>'+
    (history||'<tr><td colspan="6">No local amendments recorded.</td></tr>')+
    '</tbody></table></div>';
  host.querySelector('#quotePriceChangeForm').addEventListener('submit', quoteSavePriceRevision);
  const revert=host.querySelector('#quotePriceRevert');
  if(revert)revert.addEventListener('click', quoteRevertPriceRevision);
}

async function quoteSavePriceRevision(event) {
  event.preventDefault();
  const record=quotePriceEditorSelection;
  if(!record)return;
  const form=event.currentTarget;
  if(!form.reportValidity())return;
  const input=Object.fromEntries(new FormData(form).entries());
  const feedback=document.querySelector('#quotePriceEditFeedback');
  if(feedback)feedback.textContent='Recording price revision…';
  try {
    await api('/api/quoting/prices/'+encodeURIComponent(record.sku), {
      method:'PUT',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({
        price_gbp:input.price_gbp,
        reason:input.reason,expected_revision:record.revision
      })
    });
    const fresh=await api('/api/quoting/prices/'+encodeURIComponent(record.sku));
    quotePriceEditorSelection=fresh;
    renderQuotePriceEditor(fresh);
    unifiedClearPrice();
    const current=document.querySelector('#quotePriceEditFeedback');
    if(current)current.textContent='Saved. Existing quote drafts must be repriced before use.';
  } catch(error) {
    if(feedback)feedback.textContent=error.message;
  }
}

async function quoteRevertPriceRevision() {
  const record=quotePriceEditorSelection;
  if(!record)return;
  const form=document.querySelector('#quotePriceChangeForm');
  const reason=String(form?.elements.reason.value||'').trim();
  const feedback=document.querySelector('#quotePriceEditFeedback');
  if(reason.length<12) {
    if(feedback)feedback.textContent='Enter a reason (at least 12 characters) before reverting.';
    return;
  }
  try {
    await api('/api/quoting/prices/'+encodeURIComponent(record.sku)+'/revert',{
      method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({expected_revision:record.revision,reason})
    });
    const fresh=await api('/api/quoting/prices/'+encodeURIComponent(record.sku));
    quotePriceEditorSelection=fresh;
    renderQuotePriceEditor(fresh);
    unifiedClearPrice();
    const current=document.querySelector('#quotePriceEditFeedback');
    if(current)current.textContent='Price reverted to the current source. Audit history retained.';
  } catch(error) {
    if(feedback)feedback.textContent=error.message;
  }
}


async function loadQuoteGoLiveStatus(){
  const holder=document.querySelector('#quoteGoLiveStatus');
  if(!holder||view!=='quoting')return;
  holder.textContent='Checking original equipment, Master/Sage prices and commercial sign-off…';
  try{
    const session=await api('/api/pilot/me');
    if(view!=='quoting'||!document.querySelector('#quoteGoLiveStatus'))return;
    if(!session.pilot||!['Admin','Coordinator'].includes(session.role)){
      holder.textContent='Quotation release is available only in the protected pilot to named staff accounts.';
      return;
    }
    const result=await api('/api/quoting/release-check');
    if(view!=='quoting'||!document.querySelector('#quoteGoLiveStatus'))return;
    const steps=(result.items||[]).map(item=>
      '<tr><td>'+esc(item.title)+'</td><td>'+
      esc(item.ready?'Ready':item.required?'Action needed':'Optional — not loaded')+
      '</td><td>'+esc(item.ready?item.details:item.next_action+
         (item.details?' — '+item.details:''))+'</td></tr>'
    ).join('');
    holder.innerHTML=
      '<p><strong>'+
      (result.required_ready?
        'Core quotation setup is ready for individual quote review.':
        'Commercial setup is incomplete; see the outstanding actions below.')+
      '</strong> '+
      (result.sage_fallback_ready?'Sage fallback prices are loaded.':
        'Sage-only historical machines cannot use fallback prices until the Sage export is imported.')+
      '</p>'+
      '<div style="overflow-x:auto"><table class="data-table"><thead><tr>'+
      '<th>Requirement</th><th>Status</th><th>What to do</th></tr></thead><tbody>'+
      steps+'</tbody></table></div>'+
      '<p class="fine-print">A ready setup is not approval for every machine. '+
      'An Admin still checks exact equipment and its maintenance terms, then '+
      'authorises the specific customer PDF. Sending the email remains manual.</p>';
  }catch(error){
    const target=document.querySelector('#quoteGoLiveStatus');
    if(target)target.textContent='Cannot verify quotation setup: '+error.message;
  }
}
