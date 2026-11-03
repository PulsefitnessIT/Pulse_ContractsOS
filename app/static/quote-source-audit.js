/* Read-only SmartQuote catalogue identity and pricing-source reconciliation.
   No Master Price List or historic rates are declared approved by this UI. */
let quoteAuditSearchState={q:'',issue:'',offset:0,limit:30};
let quoteAuditIssues=[];

async function loadQuoteSourceAudit() {
  const host=document.querySelector('#quoteSourceAudit');
  if(!host || view!=='quoting')return;
  host.textContent='Reading the private source catalogue and legacy mapping evidence…';
  try {
    const r=await api('/api/quoting/catalogue/reconciliation');
    if(view!=='quoting'||!document.querySelector('#quoteSourceAudit'))return;
    const counts=r.summary||{};
    quoteAuditIssues=Object.keys(counts.flag_counts||{}).sort();
    const flagDescription={
      duplicate_sku:'Duplicate current SKU',
      missing_or_invalid_current_rrp:'No valid source RRP',
      missing_or_ambiguous_service_configuration:'Unverified service configuration',
      rate_group_unmapped:'Unmapped tariff group',
      source_rate_requires_review:'Source rate requires review',
      console_rule_unverified:'Unverified console rule',
      excluded_from_cover:'Excluded from maintenance cover',
      service_eligibility_not_confirmed:'Service eligibility not confirmed',
      price_list_only_coverage_review:'Price-list-only coverage review',
      invalid_sku:'Invalid SKU',
    };
    const rows=[
      ['Catalogue source rows',counts.catalogue_source_rows],
      ['Distinct current SKUs',counts.distinct_skus],
      ['Duplicate SKU groups',counts.duplicate_sku_groups],
      ['SKUs requiring review',counts.source_skus_requiring_review],
      ['Legacy source rows',counts.legacy_source_rows],
      ['Ambiguous legacy codes',counts.ambiguous_legacy_codes],
      ['Historical variants staged',counts.historical_source_variants]
    ].map(([label,value])=>'<tr><td>'+esc(label)+'</td><td>'+
      (value===null||value===undefined?'Source not staged':esc(value))+'</td></tr>').join('');
    const flags=Object.entries(counts.flag_counts||{}).sort((a,b)=>b[1]-a[1]);
    host.innerHTML=
      '<p><strong>Pricing policy as recorded:</strong> '+esc(r.commercial_policy_as_recorded)+
      '</p><p><strong>Source manifest:</strong> '+
      (r.manifest_status?.matches ? 'Source fingerprints match private IT manifest.' :
        'Not pinned / source identity not yet verified.') +
      ' This does not constitute commercial tariff approval.</p>'+
      '<p>These are source-file findings, not approved prices or proof of current equipment eligibility.</p>'+
      '<table class="data-table"><thead><tr><th>Catalogue evidence</th><th>Source count</th></tr></thead><tbody>'+
      rows+'</tbody></table>'+
      '<p><strong>Source fingerprints:</strong> <code>'+esc(JSON.stringify(r.source_sha256))+'</code></p>'+
      '<h4>Exception worklist</h4>'+
      '<div class="form-grid">'+
        '<label>Search model, code or description <input id="quoteAuditQuery" maxlength="100" value="'+
          esc(quoteAuditSearchState.q)+'" placeholder="Find source exception"></label>'+
        '<label>Issue <select id="quoteAuditIssue"><option value="">All source exceptions</option>'+
          flags.map(([id,n])=>'<option value="'+esc(id)+'">'+
            esc(flagDescription[id]||id)+' ('+esc(n)+')</option>').join('')+
        '</select></label>'+
        '<button class="button button-outline" id="quoteAuditSearch">Review exceptions</button>'+
      '</div><div id="quoteAuditRows"></div>'+
      '<h4>Exact historical-code check</h4>'+
      '<form id="quoteLegacyLookupForm"><label>Previously recorded code '+
        '<input name="code" maxlength="100" minlength="2" required placeholder="Enter entire old SKU"></label> '+
        '<button class="button button-outline" type="submit">Verify legacy mapping</button></form>'+
      '<div id="quoteLegacyEvidence" aria-live="polite"></div>'+
      '<h4>Historical equipment identities (2020–2026 evidence)</h4>'+
      '<form id="quoteHistoryLookupForm"><label>Old SKU, model or equipment description '+
        '<input name="q" maxlength="100" minlength="2" required placeholder="Search historical equipment"></label> '+
        '<button class="button button-outline" type="submit">Search historical index</button></form>'+
      '<div id="quoteHistoricalEvidence" aria-live="polite"></div>'+
      '<p class="fine-print">No customer name, quote or new RRP is inferred from a legacy code. '+
        'A missing historical source is not a complete historical reconciliation.</p>';
    host.querySelector('#quoteAuditIssue').value=quoteAuditSearchState.issue;
    host.querySelector('#quoteAuditSearch').addEventListener('click',()=>{
      quoteAuditSearchState.q=host.querySelector('#quoteAuditQuery').value.trim();
      quoteAuditSearchState.issue=host.querySelector('#quoteAuditIssue').value;
      quoteAuditSearchState.offset=0;
      loadQuoteAuditExceptions().catch(e=>quoteAuditError(e.message));
    });
    host.querySelector('#quoteLegacyLookupForm').addEventListener('submit',async e=>{
      e.preventDefault();
      const output=host.querySelector('#quoteLegacyEvidence');
      output.textContent='Checking privately staged V10 legacy references…';
      try {
        const code=new FormData(e.currentTarget).get('code');
        const result=await api('/api/quoting/catalogue/legacy/resolve?code='+
            encodeURIComponent(String(code||'').trim()));
        output.innerHTML='<p>'+esc(result.match_count)+' current SKU candidate(s). '+
          (result.ambiguous?'Ambiguous or not found — staff match review required.':
            'One candidate; identity still requires staff confirmation.')+'</p>'+
          (result.candidates||[]).map(c=>'<div>'+esc(c.sku)+' — '+
            esc(c.model)+' / '+esc(c.console)+'</div>').join('')+
          '<p class="fine-print">Historical evidence only. No current RRP or pricing approved.</p>';
      } catch(error){output.textContent=error.message}
    });
    host.querySelector('#quoteHistoryLookupForm').addEventListener('submit',async event=>{
      event.preventDefault();
      const output=host.querySelector('#quoteHistoricalEvidence');
      output.textContent='Searching the original historical identity index…';
      try {
        const query=String(new FormData(event.currentTarget).get('q')||'').trim();
        const result=await api('/api/quoting/catalogue/historical/search?q='+
          encodeURIComponent(query)+'&limit=30');
        output.innerHTML='<p>'+esc(result.total)+' historical variant(s) recorded. '+
          (result.ambiguous_or_multiple_variants ?
            'Multiple variants: confirm identity and console manually.' :
            'Historical identity only; no current price confirmed.')+'</p>'+
          '<div style="overflow-x:auto"><table class="data-table"><thead><tr>'+
          '<th>Recorded SKU</th><th>Model</th><th>Console</th><th>Recorded year</th>'+
          '</tr></thead><tbody>'+
          (result.results||[]).map(row=>'<tr><td>'+esc(row.historical_sku)+
            '</td><td>'+esc(row.model)+'</td><td>'+esc(row.console)+
            '</td><td>'+esc(row.year_as_recorded)+'</td></tr>').join('')+
          '</tbody></table></div><p class="fine-print">Historical identity never authorises a new maintenance RRP.</p>';
      } catch(error){output.textContent=error.message;}
    });
    await loadQuoteAuditExceptions();
  } catch(error) {
    host.textContent='Source reconciliation unavailable. '+error.message+
      ' Do not assume the equipment catalogue or price list has been approved.';
  }
}
function quoteAuditError(message) {
  const host=document.querySelector('#quoteAuditRows');
  if(host)host.textContent=message;
}
async function loadQuoteAuditExceptions() {
  const container=document.querySelector('#quoteAuditRows');
  if(!container)return;
  const response=await api('/api/quoting/catalogue/reconciliation/worklist?'+
    new URLSearchParams(quoteAuditSearchState));
  if(view!=='quoting'||!document.querySelector('#quoteAuditRows'))return;
  const listed=(response.items||[]).map(item=>
    '<tr><td><strong>'+esc(item.sku)+'</strong><div class="fine-print">'+
      esc(item.model)+' · '+esc(item.console)+'</div></td><td>'+esc(item.description)+
    '</td><td>'+esc(item.source_rows)+'</td><td>'+esc(item.issues.join(', '))+
    '</td></tr>').join('');
  container.innerHTML='<p>'+esc(response.total)+' source SKU groups require review.</p>'+
    '<div style="overflow-x:auto"><table class="data-table"><thead><tr>'+
      '<th>SKU/model</th><th>Product description</th><th>Rows</th><th>Unresolved issues</th>'+
      '</tr></thead><tbody>'+
      (listed||'<tr><td colspan="4">No records match these filters.</td></tr>')+
      '</tbody></table></div>'+
    '<div style="display:flex;gap:0.5rem;align-items:center">'+
      '<button class="button button-outline" id="quoteAuditPrevious" '+
      (response.offset?'':'disabled')+'>Previous</button>'+
      '<button class="button button-outline" id="quoteAuditNext" '+
      (response.offset+response.items.length<response.total?'':'disabled')+
      '>Next</button><span>'+esc(response.offset+1)+'–'+
      esc(Math.min(response.offset+response.items.length,response.total))+
      ' of '+esc(response.total)+'</span></div>';
  const previous=container.querySelector('#quoteAuditPrevious');
  const next=container.querySelector('#quoteAuditNext');
  previous.onclick=()=>{quoteAuditSearchState.offset=Math.max(0,quoteAuditSearchState.offset-
    quoteAuditSearchState.limit);loadQuoteAuditExceptions().catch(e=>quoteAuditError(e.message));};
  next.onclick=()=>{quoteAuditSearchState.offset+=quoteAuditSearchState.limit;
    loadQuoteAuditExceptions().catch(e=>quoteAuditError(e.message));};
}
