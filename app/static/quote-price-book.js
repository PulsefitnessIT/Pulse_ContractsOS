/* Pulse single Master Price List. Administrator-only server endpoints.
 * New imports UPDATE matching codes; do not remove unmentioned items or rewrite
 * already issued quotations. Original Sage files remain reference archives.
 */
let priceBookPending=null;

async function initQuotePriceBook(){
  const panel=document.querySelector('#quoteUnifiedBookPanel');
  const host=document.querySelector('#quoteUnifiedBookHost');
  if(!panel||!host||view!=='quoting')return;
  panel.hidden=false;
  priceBookPending=null;
  host.innerHTML=
    '<p>The unified Master contains all Sage item codes and preferred Master prices. '+
    'New verified imports replace matching prices only. Unmentioned records stay in place.</p>'+
    '<div id="quotePriceBookStatus" role="status">Checking current price book…</div>'+
    '<form id="quotePriceBookUpload" class="form-grid">'+
    '<label>New price list or price updates (CSV) '+
    '<input name="file" type="file" accept=".csv,text/csv" required></label>'+
    '<button class="button button-outline" type="submit">Review price changes</button>'+
    '</form><div id="quotePriceBookFeedback" role="status"></div>'+
    '<div id="quotePriceBookCompare"></div>';
  host.querySelector('#quotePriceBookUpload').addEventListener('submit',quotePreviewUnifiedPriceBook);
  await quotePriceBookStatus();
}

async function quotePriceBookStatus(){
  const host=document.querySelector('#quotePriceBookStatus');
  if(!host)return;
  try{
    const data=await api('/api/quoting/price-book/status');
    if(view!=='quoting'||!document.querySelector('#quotePriceBookStatus'))return;
    host.innerHTML=data.active?
      '<p><strong>Active Master v'+esc(data.revision)+'</strong> — '+
      esc(data.distinct_codes)+' product codes · Last updated: '+
      esc(data.last_imported_at||'not recorded')+'.</p>'+
      '<p><a class="button button-outline" href="/api/quoting/price-book/export.csv" '+
      'download="Pulse_Unified_Master_Current.csv">Download current Master price list</a></p>'+
      '<p class="fine-print">Master prices are a reference basis only. '+
      'Equipment suitability, maintenance tariffs and customer quotations need separate checks.</p>'
      :'<p class="notice warning">No unified Master is active. Upload the combined price list '+
      'to establish one authoritative price reference before switching away from the source imports.</p>';
    // A single active book supersedes the old source-specific price editors.
    // Historical Sage and V10 equipment source evidence is not deleted.
    const oldSage=document.querySelector('#quoteSageRefreshPanel');
    const oldOverride=document.querySelector('#quoteAdminPricePanel');
    if(oldSage) oldSage.hidden=!!data.active;
    if(oldOverride) oldOverride.hidden=!!data.active;
  }catch(error){
    host.textContent='Unified Master status unavailable: '+error.message;
  }
}

async function quotePreviewUnifiedPriceBook(event){
  event.preventDefault();
  const form=event.currentTarget;
  if(!form.reportValidity())return;
  const submit=form.querySelector('[type="submit"]');
  const feedback=document.querySelector('#quotePriceBookFeedback');
  const area=document.querySelector('#quotePriceBookCompare');
  if(!submit||!feedback||!area)return;
  submit.disabled=true;
  feedback.textContent='Verifying exact item codes, source values and revisions…';
  area.textContent='';
  priceBookPending=null;
  try{
    const result=await api('/api/quoting/price-book/preview',{
      method:'POST',body:new FormData(form)
    });
    if(view!=='quoting'||!document.querySelector('#quotePriceBookCompare'))return;
    priceBookPending=result;
    const c=result.changes;
    area.innerHTML=
      '<h4>Proposed import — no prices changed yet</h4>'+
      '<p><strong>'+esc(c.uploaded_codes)+'</strong> imported codes · '+
      esc(c.updated_codes)+' updated · '+esc(c.new_codes)+' new · '+
      esc(c.unchanged_codes)+' unchanged · '+
      esc(c.retained_existing_codes)+' existing records retained.</p>'+
      '<p>'+esc(c.held_codes)+' held prices · '+esc(c.zero_price_codes)+
      ' zero-price items. No missing SKU will be deleted.</p>'+
      '<form id="quotePriceBookApproval" class="form-grid">'+
      '<label>Reason for this price update <input name="reason" minlength="12" '+
      'maxlength="500" required placeholder="e.g. November approved price update"></label>'+
      '<label><input type="checkbox" name="confirm_held"> '+
      'I have reviewed held and zero-price items and understand they cannot be quoted.</label>'+
      '<button class="button button-primary" type="submit">Activate updated Master prices</button>'+
      '</form>';
    area.querySelector('#quotePriceBookApproval').addEventListener(
      'submit',quoteActivateUnifiedPriceBook
    );
    feedback.textContent='Preview ready. No quotation or Master price has yet been changed.';
  }catch(error){
    feedback.textContent='Price-list import rejected: '+error.message+
      '. Correct duplicate, invalid, missing or unpriced item fields before retrying.';
  }finally{submit.disabled=false;}
}

async function quoteActivateUnifiedPriceBook(event){
  event.preventDefault();
  if(!priceBookPending)return;
  const form=event.currentTarget;
  if(!form.reportValidity())return;
  const feedback=document.querySelector('#quotePriceBookFeedback');
  const submit=form.querySelector('[type="submit"]');
  if(!feedback||!submit)return;
  submit.disabled=true;
  feedback.textContent='Recording the approved price-list version…';
  try{
    const formData=new FormData(form);
    const result=await api('/api/quoting/price-book/activate',{
      method:'POST',
      body:JSON.stringify({
        preview_token:priceBookPending.preview_token,
        reason:String(formData.get('reason')||''),
        confirm_zero_and_held_prices:formData.has('confirm_held')
      })
    });
    priceBookPending=null;
    feedback.textContent='Active Master version '+result.revision+' saved. '+
      result.changes.updated_codes+' prices updated; '+
      result.changes.new_codes+' new codes; no existing quotes changed.';
    const area=document.querySelector('#quotePriceBookCompare');
    if(area)area.textContent='';
    await quotePriceBookStatus();
  }catch(error){
    feedback.textContent='Price-book activation blocked: '+error.message;
  }finally{submit.disabled=false;}
}
