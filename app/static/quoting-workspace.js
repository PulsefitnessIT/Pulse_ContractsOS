/* Pulse Fitness unified quoting: one workspace; separate, protected data sources.
   Native drafts never contain inferred commercial prices. */
let unifiedDraftSelected = null;
let unifiedEquipment = [];
let unifiedDraftRecords = [];
let unifiedCatalogueMatches = [];
let unifiedSiteMatches = [];
let quotePriceEditorSelection = null;

async function quotingWorkspacePage() {
  unifiedDraftSelected = null;
  unifiedEquipment = [];
  content.innerHTML =
    '<section class="panel"><h2>SmartQuote</h2>' +
    '<p>Create a maintenance quotation, select equipment, check prices, and download an approved PDF. '+ 
    'Existing SmartQuote records stay intact and read-only.</p></section>' +
    '<section class="panel" id="quoteGoLiveStatusPanel">' +
    '<div class="section-head"><div><h3>Customer quotation readiness</h3>' +
    '<p>See exactly what is still needed before the first approved customer PDF can be issued.</p></div>' +
    '<button type="button" class="button button-outline" id="quoteGoLiveRefresh">Check readiness</button></div>' +
    '<div id="quoteGoLiveStatus" aria-live="polite">Checking pricing and commercial setup…</div></section>' +
    '<section class="panel" id="unifiedDraftPanel">' +
    '<h3 id="unifiedDraftTitle">New quotation draft</h3>' +
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
    '<h4>Equipment lines</h4>' +
    '<form id="unifiedCatalogueSearch"><label>Find a SmartQuote product (SKU, model or name) ' +
    '<input name="q" minlength="2" maxlength="100" required placeholder="Search original product identity (not approval)"></label> ' +
    '<button type="submit" class="button button-outline">Find equipment</button></form>' +
    '<div id="unifiedCatalogueResults" aria-live="polite"></div>' +
    '<div id="unifiedEquipmentTable"></div>' +
    '<form id="unifiedEquipmentAdd">' +
    '<div class="form-grid">' +
    '<label>Equipment description <input name="description" maxlength="400" required></label>' +
    '<label>Product code <input name="item_code" maxlength="100"></label>' +
    '<label>Serial number <input name="serial" maxlength="120"></label>' +
    '<label>Equipment cover starts <input name="cover_start" type="date"></label>' +
    '<label>Quantity <input name="quantity" type="number" min="1" max="10000" step="1" value="1" required></label>' +
    '</div><button type="submit" class="button button-outline">Add equipment line</button></form>' +
    '<div style="display:flex;gap:0.6rem;flex-wrap:wrap;margin-top:1rem">' +
    '<button type="button" class="button button-primary" id="unifiedSaveAndPrice">Save &amp; calculate price</button>' +
    '<button type="button" class="button button-outline" id="unifiedDraftSave">Save draft only</button>' +
    '<button type="button" class="button button-outline" id="unifiedDraftNew">New draft</button>' +
    '<button type="button" class="button button-outline" id="unifiedDraftPrice">Recalculate saved price</button></div>' +
    '<p id="unifiedDraftFeedback" role="status" aria-live="polite"></p>' +
    '<div id="unifiedPricePanel" aria-live="polite"></div>' +
    '</section>' +
    '<section class="panel"><h3>Equipment RRP source priority</h3>' +
    '<p>August 2026 List Price covers current equipment. ' +
    'For exact codes absent from that master, the Sage price is the working pricing basis. ' +
    'Pricing administrators can make audited corrections without altering the source files.</p>' +
    '<button type="button" class="button button-outline" id="rrpPriorityStatusLoad">Check source coverage</button>' +
    '<div id="rrpPriorityStatus" aria-live="polite"></div></section>' +
    '<section class="panel" id="quoteV10SourcePanel" hidden>' +
    '<h3>Original V10 &amp; August Price Source Setup</h3>' +
    '<div id="quoteV10SourceHost"></div></section>' +
    '<section class="panel" id="quoteCommercialSetupPanel" hidden>' +
    '<h3>Customer Quotation — Commercial Setup</h3>' +
    '<div id="quoteCommercialSetupHost"></div></section>' +
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
  renderUnifiedEquipment();
  // Independent requests: a disconnected original SmartQuote must never hide draft creation.
  await Promise.allSettled([loadUnifiedDrafts(), loadUnifiedLegacyQuotes()]);
}

function renderUnifiedEquipment() {
  const host = document.querySelector('#unifiedEquipmentTable');
  if (!host || view !== 'quoting') return;
  const rows = unifiedEquipment.map((item, i) =>
    '<tr><td>' + esc(item.description) + '</td><td>' + esc(item.item_code) +
    '</td><td>' + esc(item.serial || 'Not confirmed') + '</td><td>' +
    esc(item.cover_start || 'Contract start') + '</td><td>' +
    esc(item.quantity) + '</td><td><button class="button button-outline" type="button" data-remove-line="' +
    i + '">Remove</button></td></tr>'
  ).join('');
  host.innerHTML =
    '<div style="overflow-x:auto"><table class="data-table"><thead><tr><th>Machine</th><th>Code</th><th>Serial</th><th>Cover starts</th><th>Qty</th><th></th></tr></thead><tbody>' +
    (rows || '<tr><td colspan="6">No equipment added yet.</td></tr>') +
    '</tbody></table></div>';
  host.querySelectorAll('[data-remove-line]').forEach(b => b.addEventListener('click', () => {
    unifiedEquipment.splice(Number(b.dataset.removeLine), 1);
    unifiedClearPrice();
    renderUnifiedEquipment();
  }));
}

function unifiedAddEquipment(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const data = Object.fromEntries(new FormData(form).entries());
  const quantity = Number(data.quantity);
  const feedback = document.querySelector('#unifiedDraftFeedback');
  if (!Number.isSafeInteger(quantity) || quantity < 1 || quantity > 10000) {
    feedback.textContent = 'Enter a positive whole-number equipment quantity.';
    return;
  }
  if (!String(data.description || '').trim()) {
    feedback.textContent = 'Enter an equipment description.';
    return;
  }
  if (unifiedEquipment.length >= 500) {
    feedback.textContent = 'Maximum 500 equipment lines per draft.';
    return;
  }
  unifiedClearPrice();
  unifiedEquipment.push({
    description: String(data.description).trim(),
    item_code: String(data.item_code || '').trim(),
    serial: String(data.serial || '').trim(),
    cover_start: String(data.cover_start || ''),
    quantity
  });
  form.reset();
  feedback.textContent = 'Equipment line added. Save the quotation draft to retain it.';
  renderUnifiedEquipment();
}

function unifiedNewDraft() {
  unifiedDraftSelected = null;
  unifiedEquipment = [];
  unifiedClearPrice();
  const form = document.querySelector('#unifiedDraftForm');
  if (form) form.reset();
  const heading = document.querySelector('#unifiedDraftTitle');
  if (heading) heading.textContent = 'New quotation draft';
  const feedback = document.querySelector('#unifiedDraftFeedback');
  if (feedback) feedback.textContent = '';
  renderUnifiedEquipment();
}

async function unifiedSaveDraft() {
  const form = document.querySelector('#unifiedDraftForm');
  const feedback = document.querySelector('#unifiedDraftFeedback');
  const button = document.querySelector('#unifiedDraftSave');
  const combined = document.querySelector('#unifiedSaveAndPrice');
  if (!form || !form.reportValidity() || !feedback || !button) return null;
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
  button.disabled = true;
  if (combined) combined.disabled = true;
  feedback.textContent = 'Saving…';
  try {
    const saved = await api(url, {method, headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)});
    unifiedDraftSelected = {id:saved.id, revision:saved.revision};
    unifiedClearPrice();
    feedback.textContent = 'Saved. This quotation remains unpriced and cannot be issued yet.';
    document.querySelector('#unifiedDraftTitle').textContent = 'Edit quotation draft';
    await loadUnifiedDrafts();
    return saved;
  } catch (error) {
    feedback.textContent = error.message + ' If another user saved changes, reload the draft.';
    return null;
  } finally {
    button.disabled = false;
    if (combined) combined.disabled = false;
  }
}

async function unifiedSaveAndPrice(){
  const result=await unifiedSaveDraft();
  // Never call the calculator when a save failed: otherwise the old
  // revision might appear priced for a changed site or equipment list.
  if (result) await unifiedPricePreview();
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
  if (!feedback) return;
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
    unifiedClearPrice();
    unifiedDraftSelected = {id:draft.id, revision:draft.revision};
    document.querySelector('#unifiedDraftTitle').textContent = 'Edit quotation draft';
    feedback.textContent = 'Loaded draft revision ' + draft.revision + '. Recalculate prices before generating a customer quote.';
    renderUnifiedEquipment();
    document.querySelector('#unifiedDraftPanel').scrollIntoView({behavior:'smooth',block:'start'});
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


async function unifiedSearchCatalogue(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const host = document.querySelector('#unifiedCatalogueResults');
  if (!host) return;
  const q = String(new FormData(form).get('q') || '').trim();
  if (q.length < 2) return;
  host.textContent = 'Searching SmartQuote equipment and the full Sage item price list…';
  try {
    const encoded=encodeURIComponent(q);
    const responses=await Promise.allSettled([
      api('/api/quoting/catalogue/search?q='+encoded+'&limit=40'),
      api('/api/quoting/sage/search?q='+encoded+'&limit=40')
    ]);
    if (view !== 'quoting' || !document.querySelector('#unifiedCatalogueResults')) return;
    if(responses.every(reply=>reply.status==='rejected')){
      throw new Error('Neither the original equipment catalogue nor Sage list is staged in this pilot.');
    }
    const originals=responses[0].status==='fulfilled'?(responses[0].value.results||[]):[];
    const sage=responses[1].status==='fulfilled'?(responses[1].value.results||[]):[];
    const known=new Set(originals.map(row=>String(row.sku||'').toUpperCase()));
    unifiedCatalogueMatches=[...originals,
      ...sage.filter(row=>!known.has(String(row.sku||'').toUpperCase()))];
    host.innerHTML = unifiedCatalogueMatches.length
      ? '<p>Find the exact SKU from the V10 equipment database or Sage. '+
        'Sage price presence alone does not confirm an approved maintenance rate. '+
        'Unmapped older machines must be reviewed before issuing a customer quote.</p>' +
        '<div style="overflow-x:auto"><table class="data-table"><thead><tr>'+
        '<th>SKU</th><th>Equipment</th><th>Model / group</th>'+
        '<th>Source</th><th>Review</th><th></th></tr></thead><tbody>' +
        unifiedCatalogueMatches.map((p,i) => '<tr><td>' + esc(p.sku) +
          '</td><td>'+esc(p.name)+'</td><td>'+esc(p.model||p.group||'')+
          '</td><td>'+esc(p.source||'V10 catalogue')+
          '</td><td>'+(p.duplicate_sku?'Duplicate code — manual review':
            p.requires_service_mapping?
              'Sage reference — service mapping must be verified':
              'Original V10 identity')+
          '</td><td><button class="button button-outline" type="button" '+
          'data-use-catalogue="'+i+'"'+(p.duplicate_sku?' disabled':'')+
          '>Use item code</button></td></tr>').join('') +
        '</tbody></table></div>'
      : '<p>No exact catalogue or Sage item matched. You can still enter '+
        'equipment details manually for review.</p>';
    host.querySelectorAll('[data-use-catalogue]').forEach(button => button.addEventListener('click', () => {
      const choice = unifiedCatalogueMatches[Number(button.dataset.useCatalogue)];
      if (!choice || choice.duplicate_sku) return;
      const equipmentForm = document.querySelector('#unifiedEquipmentAdd');
      equipmentForm.elements.description.value = choice.name || choice.model || choice.sku;
      equipmentForm.elements.item_code.value = choice.sku;
      equipmentForm.elements.serial.focus();
      const feedback = document.querySelector('#unifiedDraftFeedback');
      if (feedback) feedback.textContent = choice.requires_service_mapping
        ? 'Sage item selected. Confirm its equipment configuration and maintenance eligibility before quoting.'
        : 'V10 equipment selected. Confirm serial and quantity, then preview pricing.';
    }));
  } catch (error) {
    const target = document.querySelector('#unifiedCatalogueResults');
    if (target) target.innerHTML = '<p class="notice warning">' + esc(error.message) +
      ' Manual equipment entry is still available.</p>';
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
  const host = document.querySelector('#unifiedPricePanel');
  if (host) host.innerHTML = '';
}

async function unifiedPricePreview() {
  const host = document.querySelector('#unifiedPricePanel');
  if (!host) return;
  if (!unifiedDraftSelected) {
    host.textContent = 'Save the quotation draft before calculating a tariff preview.';
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
  host.textContent = 'Checking exact product identities against the staged V10 pricing rules…';
  try {
    const preview = await api('/api/quoting/drafts/' + encodeURIComponent(unifiedDraftSelected.id) + '/price-preview');
    if (view !== 'quoting' || !document.querySelector('#unifiedPricePanel')) return;
    if (preview.revision !== unifiedDraftSelected.revision) {
      host.textContent = 'The draft has changed. Reopen it before pricing.';
      return;
    }
    const varianceLines=preview.lines.filter(line=>
      Boolean(line.source_price_comparison?.requires_explicit_ack));
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
          '%'+(line.source_price_comparison.requires_explicit_ack?
            ' — manager must acknowledge':'')+'; ':'')+
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
      (varianceLines.length?
        '<p class="notice warning">'+esc(varianceLines.length)+
        ' selected line(s) have a Sage Sales Price differing by more than 5% '+
        'from the August List Price. These prices may have different source '+
        'meanings. An Administrator must review and explicitly attest the chosen '+
        'quote basis before issuing the customer PDF. Use an audited price '+
        'revision if the equipment price itself needs correcting.</p>':'')+
      (preview.staged.enabled ?
        '<h4>Staged cover — inclusive calendar-year prorating</h4><div style="overflow-x:auto"><table class="data-table"><thead><tr><th>Start date</th><th>Units</th><th>Period charge</th></tr></thead><tbody>' +
        preview.staged.stages.map(stage => '<tr><td>' + esc(stage.start) + '</td><td>' + esc(stage.count) + '</td><td>' + money(stage.amount) + '</td></tr>').join('') +
        '</tbody></table></div>' : '') +
      '<div style="overflow-x:auto"><table class="data-table"><thead><tr>' +
      '<th>Line</th><th>SKU</th><th>Qty</th><th>Selected equipment price</th><th>RRP source/status</th><th>Annual/unit</th><th>Annual/line</th><th>Sage source price</th><th>Review</th>' +
      '</tr></thead><tbody>' + lines + '</tbody></table></div>' +
      '<h4>Commercial controls and exceptions</h4><ul>' +
      preview.issues.map(issue => '<li>' + esc(issue) + '</li>').join('') +
      '</ul><p>The preview is not itself customer-approved. Use the quotation controls below to check release readiness and obtain manager sign-off.</p></section>';
    if (typeof showCustomerQuotePanel === 'function') showCustomerQuotePanel(preview);
  } catch(error) {
    const current = document.querySelector('#unifiedPricePanel');
    if (current) current.innerHTML = '<p class="notice warning">' + esc(error.message) + '</p>';
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
      'Sage prices may calculate internal previews for legacy equipment. '+
      'Maintenance tariffs and customer quotation issuance are still separate release gates.</p>';
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
