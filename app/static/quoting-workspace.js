/* Shared SmartQuote register: deliberately read-only until identity and data migration are approved. */
async function quotingWorkspacePage() {
  content.innerHTML = '<section class="panel"><h2>SmartQuote</h2><p>Loading quotation register…</p></section>';
  try {
    const [status, response] = await Promise.all([
      api('/api/quoting/status'), api('/api/quoting/quotes?limit=100')
    ]);
    if (view !== 'quoting') return;
    const rows = response.items.map(q =>
      '<tr><td>'+esc(q.quote_number)+'</td><td>'+esc(q.customer)+'</td>'+
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
      '</tbody></table></div>'+
      '<p class="muted">Editing, approvals, PDF issuance and automatic handover will be enabled only after shared authentication and a tested migration are in place.</p></section>';
  } catch (error) {
    if (view !== 'quoting') return;
    content.innerHTML = '<section class="panel"><h2>SmartQuote</h2>'+
      '<p>The shared quotation register is not yet connected. Existing SmartQuote data is unaffected.</p>'+
      '<p class="notice warning">'+esc(error.message)+'</p></section>';
  }
}
