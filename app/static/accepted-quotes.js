/* Accepted SmartQuote intake: one file, one review, and zero silent Sicon writes.
   Uses the existing Contracts OS session, CSRF helper and escaped UI helpers. */
let sqCandidateFile=null,sqCandidatePayload=null,sqDraftPreview=null;
async function acceptedQuotesPage(){
 content.innerHTML='<div class="main-inner">'+heading('Accepted quotes','Bring accepted SmartQuote work into the contract setup queue. The original register and equipment records are never overwritten.')+
 '<section class="card panel"><div class="section-head"><h2>Prepare accepted quote</h2><span class="pill">Protected pilot</span></div>'+
 '<p class="mini-note">Select a SmartQuote handoff JSON exported from an accepted, saved quotation. The preview checks machine values, references and missing setup details before you add anything.</p>'+
 '<div class="actions-row"><input id="sqHandoffFile" class="input" type="file" accept=".json,application/json" aria-label="SmartQuote accepted quote handoff JSON"><button id="sqPreviewBtn" class="button button-outline" type="button">Check quotation</button></div>'+
 '<div id="sqPreview" class="sq-preview"></div></section>'+
 '<section class="card panel"><div class="section-head"><h2>Contract setup worklist</h2><button class="button button-outline" id="sqReload">↻ Refresh</button></div><div id="sqWorklist" class="sq-worklist"><p class="mini-note">Loading...</p></div></section></div>';
 $('#sqHandoffFile').onchange=()=>{sqCandidateFile=$('#sqHandoffFile').files?.[0]||null;sqCandidatePayload=null;sqDraftPreview=null;$('#sqPreview').innerHTML=''};
 $('#sqPreviewBtn').onclick=async()=>{
  try{
   const file=sqCandidateFile;
   if(!file)throw Error('Choose the SmartQuote JSON export.');
   if(file.size>2*1024*1024)throw Error('This file exceeds the 2 MB pilot limit.');
   const payload=JSON.parse(await file.text());
   const result=await api('/api/smartquote/intakes/preview',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
   sqCandidatePayload=payload;sqDraftPreview=result;
   renderSQPreview(result);
  }catch(err){sqCandidatePayload=null;sqDraftPreview=null;$('#sqPreview').innerHTML='<div class="notice warning">'+esc(err.message)+'</div>'}
 };
 $('#sqReload').onclick=loadSQWorklist;
 await loadSQWorklist();
}
function sqMissing(readiness){
 if(!readiness.missing?.length)return '<span class="badge-status status-ok">All basic setup fields supplied</span>';
 return '<div class="sq-exceptions"><strong>Information to verify before Sicon setup</strong><ul>'+
 readiness.missing.map(x=>'<li>'+esc(x)+'</li>').join('')+'</ul></div>';
}
function sqCandidates(items,selectable=false){
 if(!items?.length)return '<p class="mini-note">No verified contract-number or account/site match yet. The quotation remains a separate intake; no duplicate contract is created.</p>';
 return '<div class="sq-candidate-list">'+items.map(m=>'<div class="sq-candidate"><strong>'+esc(m.customer_site)+'</strong> · '+esc(m.status)+' · Record '+m.contract_id+
 '<div class="mini-note">'+m.match_reasons.map(x=>esc(x)).join(' · ')+'</div>'+
 (selectable?'<button class="button button-outline" type="button" data-sq-link="'+m.contract_id+'">Link verified contract</button>':'')+'</div>').join('')+'</div>';
}
function renderSQPreview(result){
 let q=result.canonical,r=result.readiness;
 $('#sqPreview').innerHTML='<div class="sq-preview-card"><h3>'+esc(q.quote_number)+' · '+esc(q.customer.site_name)+'</h3>'+
 '<p class="mini-note">Customer: '+esc(q.customer.legal_name)+' · '+esc(q.contract.package)+
 ' · '+r.equipment_units+' machines · '+money(r.annual_amount)+' annual maintenance value (as recorded in SmartQuote)</p>'+
 '<p class="mini-note">Contract value: '+money(r.term_amount)+
 ' · Dates: '+esc(q.contract.start_date||'Not recorded')+' to '+esc(q.contract.end_date||'Not recorded')+'</p>'+
 sqMissing(r)+'<h3>Possible existing contract matches</h3>'+sqCandidates(result.exact_candidates)+
 (result.already_imported_id?'<p class="notice">This exact quote revision is already on the worklist. Nothing needs importing again.</p>':
 '<div class="actions-row"><button class="button button-primary" type="button" id="sqAddToWorklist">Add to setup worklist</button></div>')+'</div>';
 if($('#sqAddToWorklist'))$('#sqAddToWorklist').onclick=async()=>{
  try{
   const response=await api('/api/smartquote/intakes',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(sqCandidatePayload)});
   toast(response.already_imported?'That exact version is already recorded':'Accepted quote added for coordinator review');
   sqCandidatePayload=null;sqDraftPreview=null;$('#sqPreview').innerHTML='';
   await loadSQWorklist();
  }catch(error){toast(error.message)}
 };
}
async function loadSQWorklist(){
 try{
  const data=await api('/api/smartquote/intakes');
  const box=$('#sqWorklist');if(!box)return;
  if(!data.items.length){box.innerHTML='<div class="notice">No accepted SmartQuote quotations have been staged. Existing Contracts OS records are unchanged.</div>';return}
  box.innerHTML='<div class="scroll-table compact-table"><table class="data-table"><thead><tr><th>Quote</th><th>Readiness</th><th>Equipment</th><th>Staged dates</th><th>Linked record</th><th></th></tr></thead><tbody>'+
  data.items.map(x=>'<tr><td><strong>'+esc(x.quote_number)+'</strong><div class="mini-note">'+esc(x.imported_at?.slice(0,10)||'')+'</div></td><td>'+
  esc(x.review_status)+'</td><td>'+Number(x.readiness.equipment_units||0)+'</td><td>'+
  Number(x.readiness.staged_groups?.length||0)+'</td><td>'+
  (x.linked_contract_id?'Contract #'+x.linked_contract_id:'Not yet linked')+'</td><td><button class="button button-outline" type="button" data-sq-open="'+x.id+'">Review</button></td></tr>').join('')+'</tbody></table></div><div id="sqDetail"></div>';
  box.querySelectorAll('[data-sq-open]').forEach(button=>button.onclick=()=>sqOpenIntake(Number(button.dataset.sqOpen)));
 }catch(err){const box=$('#sqWorklist');if(box)box.innerHTML='<div class="notice warning">'+esc(err.message)+'</div>'}
}
async function sqOpenIntake(id){
 try{
  const entry=await api('/api/smartquote/intakes/'+id);
  const q=entry.quote,r=entry.readiness,box=$('#sqDetail');
  if(!box)return;
  box.innerHTML='<section class="sq-detail"><div class="section-head"><h2>Setup review: '+esc(q.quote_number)+'</h2><span class="pill">'+esc(entry.review_status)+'</span></div>'+
  '<p><strong>'+esc(q.customer.legal_name)+'</strong> · '+esc(q.customer.site_name)+'</p>'+
  '<p class="mini-note">Sage account: '+esc(q.customer.sage_account_ref||'To confirm')+
  ' · Sicon site: '+esc(q.customer.sicon_site_ref||'To confirm')+
  ' · Common end: '+esc(q.contract.end_date||'To confirm')+'</p>'+
  sqMissing(r)+'<h3>Evidence-based matches</h3>'+sqCandidates(entry.candidates,entry.linked_contract_id===null)+
  '<h3>Equipment schedule</h3><div class="scroll-table"><table class="data-table"><thead><tr><th>Machine</th><th>Description</th><th>Qty</th><th>Start</th><th>End</th></tr></thead><tbody>'+
  q.equipment.map(a=>'<tr><td>'+esc(a.item_code)+'</td><td>'+esc(a.description)+'</td><td>'+a.quantity+'</td><td>'+esc(a.cover_start)+'</td><td>'+esc(a.cover_end)+'</td></tr>').join('')+'</tbody></table></div>'+
  '<p class="mini-note">Review-only: no Sage/Sicon contract, equipment record or invoice has been created.</p></section>';
  box.querySelectorAll('[data-sq-link]').forEach(button=>button.onclick=async()=>{
   const c=Number(button.dataset.sqLink),reason=prompt('Evidence/reason for linking this quote to existing contract #'+c);
   if(!reason)return;
   try{
    await api('/api/smartquote/intakes/'+id+'/link',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({contract_id:c,note:reason})});
    toast('Existing contract linked. Original records remain unchanged.');
    await loadSQWorklist();
   }catch(err){toast(err.message)}
  });
 }catch(err){toast(err.message)}
}
