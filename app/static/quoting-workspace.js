/* Pulse Fitness unified quoting: one workspace; separate, protected data sources.
   Native drafts never contain inferred commercial prices. */
let unifiedDraftSelected = null;
let unifiedEquipment = [];
let unifiedDraftRecords = [];
let unifiedCatalogueMatches = [];

async function quotingWorkspacePage() {
  unifiedDraftSelected = null;
  unifiedEquipment = [];
  content.innerHTML =
    '<section class="panel"><h2>SmartQuote</h2>' +
    '<p>Prepare quotations in Contracts OS. Existing issued SmartQuote records remain read-only while commercial pricing is integrated.</p></section>' +
    '<section class="panel" id="unifiedDraftPanel">' +
    '<h3 id="unifiedDraftTitle">New quotation draft</h3>' +
    '<p>This draft is not priced or approved; it cannot be sent to a customer.</p>' +
    '<form id="unifiedDraftForm">' +
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
    '<input name="q" minlength="2" maxlength="100" required placeholder="Search approved product identity"></label> ' +
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
    '<button type="button" class="button button-primary" id="unifiedDraftSave">Save unpriced draft</button>' +
    '<button type="button" class="button button-outline" id="unifiedDraftNew">New draft</button>' +
    '<button type="button" class="button button-outline" id="unifiedDraftPrice">Preview V10 price</button></div>' +
    '<p id="unifiedDraftFeedback" role="status" aria-live="polite"></p>' +
    '<div id="unifiedPricePanel" aria-live="polite"></div>' +
    '</section>' +
    '<section class="panel"><h3>Quotation drafts</h3><div id="unifiedDraftList">Loading saved drafts…</div></section>' +
    '<section class="panel"><h3>Existing SmartQuote quotations</h3>' +
    '<div id="unifiedLegacyList">Checking the original SmartQuote source…</div>' +
    '<div id="unifiedLegacyDetail" aria-live="polite"></div></section>';
  document.querySelector('#unifiedEquipmentAdd').addEventListener('submit', unifiedAddEquipment);
  document.querySelector('#unifiedCatalogueSearch').addEventListener('submit', unifiedSearchCatalogue);
  document.querySelector('#unifiedDraftSave').addEventListener('click', unifiedSaveDraft);
  document.querySelector('#unifiedDraftNew').addEventListener('click', unifiedNewDraft);
  document.querySelector('#unifiedDraftPrice').addEventListener('click', unifiedPricePreview);
  document.querySelector('#unifiedDraftForm').addEventListener('input', unifiedClearPrice);
  document.querySelector('#unifiedDraftForm').addEventListener('change', unifiedClearPrice);
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
  if (!form || !form.reportValidity() || !feedback || !button) return;
  const data = Object.fromEntries(new FormData(form).entries());
  const payload = {
    customer:data.customer, site:data.site, contact:data.contact,
    tier:data.tier, term_years:Number(data.term_years), discount_percent:Number(data.discount_percent),
    contract_start:data.contract_start, contract_end:data.contract_end, equipment:unifiedEquipment
  };
  let url = '/api/quoting/drafts', method = 'POST';
  if (unifiedDraftSelected) {
    url += '/' + encodeURIComponent(unifiedDraftSelected.id);
    method = 'PUT';
    payload.revision = unifiedDraftSelected.revision;
  }
  button.disabled = true;
  feedback.textContent = 'Saving…';
  try {
    const saved = await api(url, {method, headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)});
    unifiedDraftSelected = {id:saved.id, revision:saved.revision};
    unifiedClearPrice();
    feedback.textContent = 'Saved. This quotation remains unpriced and cannot be issued yet.';
    document.querySelector('#unifiedDraftTitle').textContent = 'Edit quotation draft';
    await loadUnifiedDrafts();
  } catch (error) {
    feedback.textContent = error.message + ' If another user saved changes, reload the draft.';
  } finally {
    button.disabled = false;
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
  if (!feedback) return;
  try {
    // Fetch current revision, not the potentially stale paginated register snapshot.
    const draft = await api('/api/quoting/drafts/' + encodeURIComponent(id));
    if (view !== 'quoting' || !document.querySelector('#unifiedDraftForm')) return;
    const form = document.querySelector('#unifiedDraftForm');
    form.elements.customer.value = draft.customer;
    form.elements.site.value = draft.site;
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
    feedback.textContent = 'Loaded draft revision ' + draft.revision + '. Pricing and approval are not enabled.';
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
  host.textContent = 'Searching the privately configured SmartQuote product catalogue…';
  try {
    const response = await api('/api/quoting/catalogue/search?q=' + encodeURIComponent(q));
    if (view !== 'quoting' || !document.querySelector('#unifiedCatalogueResults')) return;
    unifiedCatalogueMatches = response.results || [];
    host.innerHTML = unifiedCatalogueMatches.length
      ? '<p>Identity suggestions only. A product match does not establish an approved tariff.</p>' +
        '<div style="overflow-x:auto"><table class="data-table"><thead><tr><th>SKU</th><th>Equipment</th><th>Model</th><th>Review</th><th></th></tr></thead><tbody>' +
        unifiedCatalogueMatches.map((p,i) => '<tr><td>' + esc(p.sku) + '</td><td>' + esc(p.name) +
          '</td><td>' + esc(p.model) + '</td><td>' + (p.duplicate_sku ? 'Duplicate code — manual review' : 'Identity suggestion') +
          '</td><td><button class="button button-outline" type="button" data-use-catalogue="' + i + '"' +
          (p.duplicate_sku ? ' disabled' : '') + '>Use identity</button></td></tr>').join('') +
        '</tbody></table></div>'
      : '<p>No matching product identity. You can still enter equipment details manually.</p>';
    host.querySelectorAll('[data-use-catalogue]').forEach(button => button.addEventListener('click', () => {
      const choice = unifiedCatalogueMatches[Number(button.dataset.useCatalogue)];
      if (!choice || choice.duplicate_sku) return;
      const equipmentForm = document.querySelector('#unifiedEquipmentAdd');
      equipmentForm.elements.description.value = choice.name || choice.model || choice.sku;
      equipmentForm.elements.item_code.value = choice.sku;
      equipmentForm.elements.serial.focus();
      const feedback = document.querySelector('#unifiedDraftFeedback');
      if (feedback) feedback.textContent = 'Product identity selected. Confirm serial and quantity; no price has been approved.';
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
    const lines = preview.lines.map(line =>
      '<tr><td>' + esc(line.line) + '</td><td>' + esc(line.item_code) +
      '</td><td>' + esc(line.quantity) + '</td><td>' +
      (line.priced ? money(line.rrp) : '—') + '</td><td>' +
      (line.priced ? money(line.unit_annual) : '—') + '</td><td>' +
      (line.priced ? money(line.annual) : 'Not priced') + '</td><td>' +
      (line.sage_reference ? money(line.sage_reference.sage_sales_price) +
        ' · Sales Price only · ' + esc(line.sage_reference.source_date) +
        (line.sage_reference.review_overdue ? ' · Review overdue' : '') : '—') +
      '</td><td>' + esc(line.exception || (line.coverage_review || []).join('; ') || 'Review commercial terms') +
      '</td></tr>').join('');
    host.innerHTML =
      '<section class="panel"><h3>INTERNAL tariff preview · Not an approved quotation</h3>' +
      '<p>Source: ' + esc(preview.source_pricing_status) + ' · Snapshot ' +
      esc(preview.source_snapshot || 'not specified') + '</p>' +
      '<p><strong>' + esc(preview.priced_count) + ' of ' + esc(preview.line_count) +
      '</strong> lines priced from exact SKUs. ' +
      'Annual ' + money(preview.annual_partial) + '; monthly ' + money(preview.monthly_partial) +
      '; ' + esc(preview.term_years) + '-year indicative total ' +
      (preview.term_partial === null ? 'Unavailable until both contract dates are set' : money(preview.term_partial)) +
      ' (partial if any line is unpriced).</p>' +
      (preview.staged.enabled ?
        '<h4>Staged cover — inclusive calendar-year prorating</h4><div style="overflow-x:auto"><table class="data-table"><thead><tr><th>Start date</th><th>Units</th><th>Period charge</th></tr></thead><tbody>' +
        preview.staged.stages.map(stage => '<tr><td>' + esc(stage.start) + '</td><td>' + esc(stage.count) + '</td><td>' + money(stage.amount) + '</td></tr>').join('') +
        '</tbody></table></div>' : '') +
      '<div style="overflow-x:auto"><table class="data-table"><thead><tr>' +
      '<th>Line</th><th>SKU</th><th>Qty</th><th>RRP</th><th>Annual/unit</th><th>Annual/line</th><th>Sage reference (not RRP)</th><th>Review</th>' +
      '</tr></thead><tbody>' + lines + '</tbody></table></div>' +
      '<h4>Commercial controls and exceptions</h4><ul>' +
      preview.issues.map(issue => '<li>' + esc(issue) + '</li>').join('') +
      '</ul><p>Customer PDF issuance, tariff approval and contract activation are disabled for this preview.</p></section>';
  } catch(error) {
    const current = document.querySelector('#unifiedPricePanel');
    if (current) current.innerHTML = '<p class="notice warning">' + esc(error.message) + '</p>';
  }
}
