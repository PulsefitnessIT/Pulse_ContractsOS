/* Pulse Fitness SmartQuote: approval-controlled PDF quotations.
 * The browser never supplies monetary values or controls whether a PDF
 * is commercially authorised; all checks are made server-side.
 */
let customerQuotePreview=null;

function quotePdfUrl(id) {
  return '/api/quoting/drafts/'+encodeURIComponent(id)+'/customer-quote';
}

function showCustomerQuotePanel(preview) {
  customerQuotePreview=preview;
  const section=document.querySelector('#unifiedPricePanel');
  if(!section||!unifiedDraftSelected)return;
  const holder=document.createElement('section');
  holder.className='panel';
  holder.id='quoteCustomerIssuePanel';
  holder.innerHTML='<h3>Prepare a customer quotation</h3>'+
    '<p>Generate a clearly marked internal PDF first. A final customer PDF '+
    'requires all equipment resolved, authorised tariff/terms and a named '+
    'administrator commercial sign-off.</p>'+
    '<div style="display:flex;flex-wrap:wrap;gap:.65rem">'+
    '<button type="button" class="button button-outline" id="quoteInternalPdf">'+
    'Download internal draft PDF</button>'+
    '<button type="button" class="button button-primary" id="quoteIssueReadiness">'+
    'Check customer issue readiness</button></div>'+
    '<p id="quoteIssueFeedback" role="status" aria-live="polite"></p>'+
    '<div id="quoteIssueReadinessDetails"></div>'+
    '<div id="quoteApprovalFormHost"></div>'+
    '<div id="quoteIssuedHistory"></div>';
  section.appendChild(holder);
  const internalButton=holder.querySelector('#quoteInternalPdf');
  internalButton.disabled=!preview.complete_price;
  internalButton.title=preview.complete_price?
    'Review the marked internal quotation before commercial approval':
    'Resolve all missing equipment prices before generating a PDF';
  holder.querySelector('#quoteInternalPdf').addEventListener('click',()=>{
    if(!unifiedDraftSelected)return;
    window.open(quotePdfUrl(unifiedDraftSelected.id)+'/internal-preview.pdf',
                '_blank','noopener');
  });
  holder.querySelector('#quoteIssueReadiness').addEventListener('click',quoteCheckCustomerReadiness);
  quoteLoadIssuedHistory();
}

async function quoteCheckCustomerReadiness(){
  const selected=unifiedDraftSelected;
  const feedback=document.querySelector('#quoteIssueFeedback');
  const details=document.querySelector('#quoteIssueReadinessDetails');
  const formHost=document.querySelector('#quoteApprovalFormHost');
  if(!selected||!feedback||!details||!formHost)return;
  formHost.innerHTML='';
  feedback.textContent='Revalidating equipment, source pricing, tariff approval and commercial terms…';
  try{
    const data=await api(quotePdfUrl(selected.id)+'/readiness');
    if(view!=='quoting'||!document.querySelector('#quoteIssueFeedback'))return;
    if(data.revision!==selected.revision) {
      feedback.textContent='Draft changed. Open the latest revision and preview its prices.';
      return;
    }
    const gates=data.gates||{};
    const rows=[
      ['All equipment prices and configurations',gates.all_equipment_priced_and_unambiguous],
      ['V10 tariff fingerprint commercially approved',gates.approved_tariff_fingerprint_matches],
      ['Verified maintenance terms PDF staged',gates.approved_terms_available],
      ['Verified Pulse Fitness legal/company details staged',gates.verified_company_issuer_details],
      ['Customer issuance enabled by IT',gates.live_issuance_opted_in_by_it]
    ].map(([label,ready])=>'<tr><td>'+esc(label)+'</td><td>'+
      esc(ready?'Ready':'Required')+'</td></tr>').join('');
    details.innerHTML='<h4>Quotation release checks</h4>'+
      '<div style="overflow-x:auto"><table class="data-table">'+
      '<thead><tr><th>Requirement</th><th>Status</th></tr></thead><tbody>'+
      rows+'</tbody></table></div>'+
      ((data.issues||[]).length?
        '<ul>'+data.issues.map(message=>'<li>'+esc(message)+'</li>').join('')+'</ul>':'');
    if(!data.customer_issue_configured) {
      feedback.textContent='Internal draft can be reviewed, but customer issue is gated until all checks are satisfied.';
      return;
    }
    const session=await api('/api/pilot/me');
    if(!session.pilot||session.role!=='Admin') {
      feedback.textContent='Only an authenticated pilot Administrator can authorise customer PDFs.';
      return;
    }
    const today=new Date();
    const expiry=new Date(today.valueOf()+30*86400000).toISOString().slice(0,10);
    const varianceCount=Number(data.price_source_variances_requiring_ack||0);
    const opts=[
      ['confirm_customer_and_site','Customer legal name and delivery site verified'],
      ['confirm_equipment_and_serials','Equipment, quantities, console options and serials checked'],
      ['confirm_package_price_and_discount','All prices, tariff rates, minimums and discounts commercially approved'],
      ['confirm_maintenance_scope_and_terms','Silver/Gold/Platinum cover, exclusions and approved terms checked'],
      ['confirm_vat_basis','Quote VAT treatment and total value checked']
    ];
    formHost.innerHTML='<form id="quoteCustomerApprovalForm">'+
      '<h4>Authorise this customer quotation</h4>'+
      '<div class="form-grid">'+
      '<label>Quote valid until <input name="valid_until" type="date" required value="'+
        esc(expiry)+'"></label>'+
      '<label>Recorded commercial approval reference '+
        '<input name="commercial_approval_ref" minlength="8" maxlength="100" required '+
        'placeholder="Approved rate schedule / manager sign-off"></label></div>'+
      opts.map(([key,label])=>'<label style="display:block;margin:.6rem 0">'+
        '<input type="checkbox" name="'+esc(key)+'" required> '+
        esc(label)+'</label>').join('')+
      (varianceCount?
        '<label style="display:block;margin:.75rem 0">'+
        '<input type="checkbox" name="confirm_source_price_variances" required> '+
        'I reviewed the '+esc(varianceCount)+
        ' price-source difference(s) above 5% between the current August List Price '+
        'and Sage Sales Price, confirmed the appropriate source basis and accept '+
        'the final quoted equipment price.</label>':'')+
      '<button class="button button-primary" type="submit">'+
      'Approve and create customer PDF</button></form>'+
      '<p class="fine-print">The customer PDF is locked and archived by quote number. '+
      'This action creates a downloadable offer; it does not email the customer '+
      'or activate a maintenance agreement.</p>';
    formHost.querySelector('form').addEventListener('submit',quoteIssueCustomerPdf);
    feedback.textContent='The source and document gates are ready. An Administrator must complete the approval record.';
  }catch(error){
    feedback.textContent='Unable to check customer quote: '+error.message;
  }
}

async function quoteIssueCustomerPdf(event){
  event.preventDefault();
  if(!unifiedDraftSelected)return;
  const form=event.currentTarget;
  if(!form.reportValidity())return;
  const selected={...unifiedDraftSelected};
  const values=new FormData(form);
  const feedback=document.querySelector('#quoteIssueFeedback');
  const button=form.querySelector('[type="submit"]');
  if(!feedback||!button)return;
  button.disabled=true;
  feedback.textContent='Archiving the approved quotation and original source evidence…';
  try {
    const keys=[
      'confirm_customer_and_site',
      'confirm_equipment_and_serials',
      'confirm_package_price_and_discount',
      'confirm_maintenance_scope_and_terms',
      'confirm_vat_basis'
    ];
    const payload={
      expected_revision:selected.revision,
      valid_until:String(values.get('valid_until')||''),
      commercial_approval_ref:String(values.get('commercial_approval_ref')||'').trim(),
      confirm_source_price_variances:values.has('confirm_source_price_variances')
    };
    for(const key of keys)payload[key]=values.has(key);
    const result=await api(quotePdfUrl(selected.id)+'/issue',{
      method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify(payload)
    });
    if(view!=='quoting'||!document.querySelector('#quoteIssueFeedback'))return;
    const box=document.querySelector('#quoteApprovalFormHost');
    box.innerHTML='<h4>Customer quote '+esc(result.quote_no)+' is ready</h4>'+
      '<p>Annual '+money(result.annual_gbp)+' · Term '+money(result.term_gbp)+
      ' · Valid until '+esc(result.valid_until)+'</p>'+
      '<p><a class="button button-primary" target="_blank" rel="noopener" '+
      'href="'+esc(result.download_url)+'">Download approved customer PDF</a></p>'+
      '<p class="fine-print">Download and email it using your normal customer '+
      'communications process. This application has not sent the email or '+
      'activated a contract.</p>';
    feedback.textContent='Quotation '+result.quote_no+' archived successfully.';
    await quoteLoadIssuedHistory();
  }catch(error) {
    feedback.textContent=error.message;
  }finally{button.disabled=false;}
}

async function quoteLoadIssuedHistory(){
  const selected=unifiedDraftSelected;
  const host=document.querySelector('#quoteIssuedHistory');
  if(!selected||!host)return;
  try{
    const session=await api('/api/pilot/me');
    if(!session.pilot||!['Admin','Coordinator'].includes(session.role))return;
    const data=await api('/api/quoting/drafts/'+encodeURIComponent(selected.id)+'/customer-quotes');
    if(view!=='quoting'||!document.querySelector('#quoteIssuedHistory'))return;
    if(!(data.items||[]).length)return;
    host.innerHTML='<h4>Previously issued PDFs (immutable)</h4>'+
      '<div style="overflow-x:auto"><table class="data-table"><thead>'+
      '<tr><th>Quotation</th><th>Draft revision</th><th>Issued</th>'+
      '<th>Approved by</th><th>Valid until</th><th>PDF</th></tr></thead><tbody>'+
      data.items.map(row=>'<tr><td>'+esc(row.quote_no)+'</td><td>'+
        esc(row.draft_revision)+'</td><td>'+esc(row.issued_at)+
        '</td><td>'+esc(row.issued_by)+'</td><td>'+esc(row.valid_until)+
        '</td><td><a target="_blank" rel="noopener" href="/api/quoting/customer-quotes/'+
        encodeURIComponent(row.quote_no)+'/download.pdf">Download</a></td></tr>').join('')+
      '</tbody></table></div>';
  }catch(error){
    host.textContent='Issued quotation history is unavailable: '+error.message;
  }
}
