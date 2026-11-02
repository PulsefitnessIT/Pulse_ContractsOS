/* Shared SmartQuote register: deliberately read-only until identity and data migration are approved. */
async function quotingWorkspacePage() {
  content.innerHTML = '<section class="panel"><h2>SmartQuote</h2><p>Loading quotation register…</p></section>';
  try {
    const [status, response] = await Promise.all([
      api('/api/quoting/status'), api('/api/quoting/quotes?limit=100')
    ]);
    if (view !== 'quoting') return;
    const rows = response.items.map(q =>
      '<tr><td><button type="button" class="quote-detail-open" data-id="'+encodeURIComponent(q.id)+'">'+esc(q.quote_number)+'</button></td><td>'+esc(q.customer)+'</td>'+
      '<td>'+esc(q.site)+'</td><td>'+esc(q.tier)+'</td>'+
      '<td>'+esc(q.status)+'</td><td>'+esc(q.updated)+'</td></tr>'
    ).join('');
    content.innerHTML =
      '<section class="panel"><div class="section-heading"><div><h2>SmartQuote</h2>'+
      '<p>Quotation register in the Contracts OS workspace · read-only development integration</p></div></div>'+
      '<p><strong>'+response.total+'</strong> quotations in the configured SmartQuote source. '+
      'Pricing and quotation history remain in the original protected database.</p>'+
      '<div style="overflow-x:auto"><table class="data-table"><thead><tr>'+
      '<th>Quote number</th><th>Customer</th><th>Site</th><th>Package</th><th>Status</th><th>Updated</th>'+
      '</tr></thead><tbody>'+(rows || '<tr><td colspan="6">No quotations found.</td></tr>')+
      '</tbody></table></div><div id="smartquoteDetail"></div>'
      '<p class="muted">Editing, approvals, PDF issuance and automatic handover will be enabled only after shared authentication and a tested migration are in place.</p></section>';
    const draftHost = document.createElement('section');
    draftHost.className = 'panel';
    draftHost.innerHTML = '<h3>Prepare quotation</h3><p>Create an unpriced draft within Contracts OS. Prices, approvals and PDFs are not generated here yet.</p>'+
      '<form id="unifiedDraftForm"><label>Customer <input name="customer" required maxlength="250"></label> '+
      '<label>Site <input name="site" required maxlength="250"></label> '+
      '<label>Contact <input name="contact" maxlength="250"></label> '+
      '<label>Cover <select name="tier"><option>Gold</option><option>Silver</option><option>Platinum</option></select></label> '+
      '<label>Equipment description <input name="description" maxlength="400"></label> '+
      '<label>Item code <input name="item_code" maxlength="100"></label> '+
      '<label>Serial <input name="serial" maxlength="120"></label> '+
      '<label>Quantity <input name="quantity" type="number" min="1" max="10000" step="1" value="1"></label> '+
      '<button class="button button-primary" type="submit">Save unpriced draft</button></form><div id="draftFeedback" role="status"></div>';
    content.prepend(draftHost);
    document.querySelector('#unifiedDraftForm').addEventListener('submit', createUnifiedDraft);
    content.querySelectorAll('.quote-detail-open').forEach(button => button.addEventListener('click', () => showUnifiedQuoteDetail(decodeURIComponent(button.dataset.id))));
  } catch (error) {
    if (view !== 'quoting') return;
    content.innerHTML = '<section class="panel"><h2>SmartQuote</h2>'+
      '<p>The shared quotation register is not yet connected. Existing SmartQuote data is unaffected.</p>'+
      '<p class="notice warning">'+esc(error.message)+'</p></section>';
  }
}

async function showUnifiedQuoteDetail(id) {
  const target = document.querySelector('#smartquoteDetail');
  if (!target || view !== 'quoting') return;
  target.textContent = 'Loading quotation details…';
  try {
    const q = await api('/api/quoting/quotes/' + encodeURIComponent(id));
    const current = document.querySelector('#smartquoteDetail');
    if (!current || view !== 'quoting') return;
    const equipment = q.assets.map(a => '<tr><td>'+esc(a.name)+'</td><td>'+esc(a.sku)+'</td><td>'+esc(a.serial)+'</td><td>'+esc(a.quantity ?? '—')+'</td></tr>').join('');
    const versions = q.pdf_versions.map(v => '<tr><td>'+esc(v.version)+'</td><td>'+esc(v.created)+'</td><td>'+esc(v.status)+'</td><td><code>'+esc(v.pdf_sha256)+'</code></td></tr>').join('');
    current.innerHTML = '<section class="panel"><h3>'+esc(q.quote_number)+' · '+esc(q.customer)+'</h3><p>Site: '+esc(q.site)+' · '+esc(q.tier)+' · '+esc(q.status)+' · Pricing approved: '+(q.pricing_approved?'Yes':'No')+'</p>'+
      '<h4>Equipment</h4><div style="overflow-x:auto"><table class="data-table"><thead><tr><th>Machine</th><th>SKU</th><th>Serial</th><th>Quantity</th></tr></thead><tbody>'+(equipment || '<tr><td colspan="4">No equipment.</td></tr>')+'</tbody></table></div>'+
      '<h4>Archived PDF versions (metadata)</h4><div style="overflow-x:auto"><table class="data-table"><thead><tr><th>Version</th><th>Created</th><th>Status</th><th>SHA-256</th></tr></thead><tbody>'+(versions || '<tr><td colspan="4">No archived PDFs.</td></tr>')+'</tbody></table></div></section>';
  } catch (error) { const current = document.querySelector('#smartquoteDetail'); if (current) current.innerHTML = '<p class="notice warning">'+esc(error.message)+'</p>'; }
}

async function createUnifiedDraft(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const values = Object.fromEntries(new FormData(form).entries());
  const desc = String(values.description || '').trim();
  const equipment = desc ? [{ description:desc, item_code:String(values.item_code || ''), serial:String(values.serial || ''), quantity:Number(values.quantity) }] : [];
  const feedback = document.querySelector('#draftFeedback');
  const button = form.querySelector('button[type="submit"]');
  button.disabled = true;
  try {
    const draft = await api('/api/quoting/drafts', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({customer:values.customer,site:values.site,contact:values.contact,tier:values.tier,equipment})});
    feedback.textContent = 'Saved unpriced quotation draft ' + draft.id + '. Pricing requires verified SmartQuote tariff integration.';
    form.reset();
  } catch (error) { feedback.textContent = error.message; }
  finally { button.disabled = false; }
}
