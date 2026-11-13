/* Admin-only V10 and August source onboarding, no ERP writes. */
let v10SourceCandidate=null;
async function initV10SourceSetup(){
  const host=document.querySelector('#quoteV10SourceHost');
  if(!host||view!=='quoting')return;
  v10SourceCandidate=null;
  host.innerHTML=
    '<p>To price a real customer, first stage the authentic pricing sources '+
    'from the existing private SmartQuote V10 repository. Include exactly '+
    '<code>catalog.json</code>, <code>configs.json</code>, '+
    '<code>pricing.json</code> and <code>rrp_2026_source.json.gz</code> '+
    'in one ZIP. Do not include customer databases, invoices or accounts.</p>'+
    '<form id="quoteV10SourcePreviewForm">'+
    '<label>Original four-file V10 source ZIP '+
    '<input type="file" name="file" accept=".zip" required></label>'+
    '<button type="submit" class="button button-outline">Check original sources</button>'+
    '</form><p id="quoteV10SourceMessage" role="status"></p>'+
    '<div id="quoteV10SourceReview"></div><div id="quoteV10SourceCurrent"></div>';
  host.querySelector('#quoteV10SourcePreviewForm')
      .addEventListener('submit',quotePreviewV10Sources);
  await loadV10SourceStatus();
}
async function quotePreviewV10Sources(event){
  event.preventDefault();
  const form=event.currentTarget;
  if(!form.reportValidity())return;
  const feedback=document.querySelector('#quoteV10SourceMessage');
  const host=document.querySelector('#quoteV10SourceReview');
  const button=form.querySelector('button[type="submit"]');
  if(!feedback||!host)return;
  button.disabled=true;
  v10SourceCandidate=null;
  host.innerHTML='';
  feedback.textContent='Checking original V10 source identities and August master evidence…';
  try{
    const result=await api('/api/quoting/source-setup/preview',{
      method:'POST',body:new FormData(form)
    });
    if(view!=='quoting'||!document.querySelector('#quoteV10SourceReview'))return;
    v10SourceCandidate=result;
    const counts=result.counts||{};
    host.innerHTML=
      '<h4>Source intake preview — not active</h4>'+
      '<p>V10 catalogue: '+esc(counts.catalogue_rows)+
      ' equipment records · Service configurations: '+esc(counts.service_configs)+
      ' · August master price rows: '+esc(counts.august_list_price_rows)+
      ' · Tariff groups: '+esc(counts.tariff_groups)+'</p>'+
      '<p>Recorded source tariff status: '+esc(result.pricing_status)+
      '</p><p>Price rules SHA-256: <code>'+esc(result.hashes.pricing)+
      '</code></p>'+
      '<form id="quoteV10SourceActivateForm">'+
      '<label>Source verification / approval reference <input name="approval_reference" '+
      'minlength="8" maxlength="160" required></label>'+
      '<label>Explanation of original source evidence <input name="reason" '+
      'minlength="12" maxlength="500" required></label>'+
      '<label><input type="checkbox" name="confirm_original_v10_files" required> '+
      'These are the genuine original V10 source files, not demo/edited data</label>'+
      '<label><input type="checkbox" name="confirm_august_master_source" required> '+
      'The 24 August 2026 Master source is the approved current-equipment baseline</label>'+
      '<button type="submit" class="button button-primary">'+
      'Activate verified pricing source bundle</button></form>';
    host.querySelector('form').addEventListener('submit',quoteActivateV10Source);
    feedback.textContent='Four files verified by format. A named Administrator must confirm their authenticity.';
  }catch(error){feedback.textContent=error.message;}
  finally{button.disabled=false;}
}
async function quoteActivateV10Source(event){
  event.preventDefault();
  if(!v10SourceCandidate)return;
  const form=event.currentTarget;
  if(!form.reportValidity())return;
  const feedback=document.querySelector('#quoteV10SourceMessage');
  if(!feedback)return;
  const data=new FormData(form);
  const button=form.querySelector('button[type="submit"]');
  button.disabled=true;
  try{
    const result=await api('/api/quoting/source-setup/activate',{
      method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({
        token:v10SourceCandidate.token,
        approval_reference:String(data.get('approval_reference')||''),
        reason:String(data.get('reason')||''),
        confirm_original_v10_files:data.has('confirm_original_v10_files'),
        confirm_august_master_source:data.has('confirm_august_master_source')
      })
    });
    v10SourceCandidate=null;
    const review=document.querySelector('#quoteV10SourceReview');
    if(review)review.innerHTML='';
    feedback.textContent='V10 source bundle version '+result.version+
      ' activated. You must now approve the exact tariff and customer terms '+
      'before any customer PDF can be issued.';
    await loadV10SourceStatus();
    if(typeof initQuoteCommercialSetup==='function')await initQuoteCommercialSetup();
  }catch(error){feedback.textContent=error.message;}
  finally{button.disabled=false;}
}
async function loadV10SourceStatus(){
  const host=document.querySelector('#quoteV10SourceCurrent');
  if(!host)return;
  try{
    const data=await api('/api/quoting/source-setup/status');
    if(view!=='quoting'||!document.querySelector('#quoteV10SourceCurrent'))return;
    const active=data.active;
    host.innerHTML='<h4>Currently verified original pricing source</h4>'+
      (active?
        '<p>Source version '+esc(active.id)+' · Verified by '+esc(active.staged_by)+
        ' at '+esc(active.staged_at)+' · '+esc(active.counts.catalogue_rows)+
        ' catalogue rows · '+esc(active.counts.august_list_price_rows)+
        ' August price rows</p>'+
        '<p>Price policy SHA-256: <code>'+esc(active.hashes.pricing)+'</code></p>':
        '<p>No original V10 source bundle is activated in the protected app. '+
        'An existing IT-managed source installation can still be used.</p>');
  }catch(error){host.textContent='Source import status could not be read: '+error.message;}
}
