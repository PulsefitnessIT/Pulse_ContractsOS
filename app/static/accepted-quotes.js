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
  const data=await api('/api/smartquote/intakes');const upcoming=await api('/api/smartquote/setups/upcoming?days=90');
  const box=$('#sqWorklist');if(!box)return;
  if(!data.items.length){box.innerHTML='<div class="notice">No accepted SmartQuote quotations have been staged. Existing Contracts OS records are unchanged.</div>';return}
  box.innerHTML=(upcoming.items.length?'<section class="sq-upcoming"><h3>Equipment coming into cover — next 90 days</h3><p class="mini-note">These dates are reminders for coordinator review, not automatic Sicon activation.</p><div class="sq-upcoming-list">'+upcoming.items.map(x=>'<div class="sq-upcoming-entry"><strong>'+esc(x.start_date)+'</strong><span>'+esc(x.site)+' · '+x.machine_units+' machine(s)</span><button class="button button-outline" type="button" data-sq-upcoming="'+x.intake_id+'">Review</button></div>').join('')+'</div></section>':'')+'<div class="scroll-table compact-table"><table class="data-table"><thead><tr><th>Quote</th><th>Readiness</th><th>Equipment</th><th>Staged dates</th><th>Linked record</th><th></th></tr></thead><tbody>'+
  data.items.map(x=>'<tr><td><strong>'+esc(x.quote_number)+'</strong><div class="mini-note">'+esc(x.imported_at?.slice(0,10)||'')+'</div></td><td>'+
  esc(x.review_status)+'</td><td>'+Number(x.readiness.equipment_units||0)+'</td><td>'+
  Number(x.readiness.staged_groups?.length||0)+'</td><td>'+
  (x.linked_contract_id?'Contract #'+x.linked_contract_id:'Not yet linked')+'</td><td><button class="button button-outline" type="button" data-sq-open="'+x.id+'">Review</button></td></tr>').join('')+'</tbody></table></div><div id="sqDetail"></div>';
  box.querySelectorAll('[data-sq-open]').forEach(button=>button.onclick=()=>sqOpenIntake(Number(button.dataset.sqOpen)));
  box.querySelectorAll('[data-sq-upcoming]').forEach(button=>button.onclick=()=>sqOpenIntake(Number(button.dataset.sqUpcoming)));
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
  '<p class="mini-note">Review-only: no Sage/Sicon contract, equipment record or invoice has been created.</p></section><div id="sqSetupWorkbench"></div>';
  box.querySelectorAll('[data-sq-link]').forEach(button=>button.onclick=async()=>{
   const c=Number(button.dataset.sqLink),reason=prompt('Evidence/reason for linking this quote to existing contract #'+c);
   if(!reason)return;
   try{
    await api('/api/smartquote/intakes/'+id+'/link',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({contract_id:c,note:reason})});
    toast('Existing contract linked. Original records remain unchanged.');
    await loadSQWorklist();
   }catch(err){toast(err.message)}
  });
  await sqShowSetup(id,q);
 }catch(err){toast(err.message)}
}


/* An accepted quote automatically owns one setup case: no second case-creation click. */
async function sqShowSetup(id,quote){
 let setup,plans;
 try{
  [setup,plans]=await Promise.all([
   api('/api/smartquote/setups/'+id),api('/api/smartquote/setups/'+id+'/plans')
  ]);
 }catch(err){toast(err.message);return}
 const target=$('#sqSetupWorkbench');if(!target)return;
 const r=setup.readiness,v=setup.verified,original=setup.source,contact=quote.customer;
 const field=(key,label,type='text')=>{
  const current=v[key]??original[key]??'';
  return '<label class="sq-field"><span>'+esc(label)+'</span><input class="input" type="'+type+'" data-sq-setup-field="'+key+'" value="'+esc(current)+'" '+(r.contract_import_confirmed?'disabled':'')+'></label>';
 };
 const steps=[
  ['Equipment & account details',!r.missing.length],
  ['Agreement signed',r.agreement_signed],
  ['Sicon contract imported',r.contract_import_confirmed],
  ['Sicon equipment imported',r.equipment_import_confirmed],
 ];
 target.innerHTML='<section class="card panel sq-setup-panel"><div class="section-head"><h2>Contract Setup Workbench</h2><span class="pill">'+esc(r.workflow_status)+'</span></div>'+
 '<p class="mini-note">Source quotation remains unchanged. Verified corrections, signatures and Sicon confirmation are recorded separately with an audit trail.</p>'+
 '<div class="sq-stage-flow">'+steps.map(([name,done],i)=>'<div class="sq-stage-item '+(done?'is-done':'')+'"><span class="sq-stage-number">'+(done?'✓':i+1)+'</span><span>'+esc(name)+'</span></div>').join('')+'</div>'+
 (r.missing.length?'<div class="sq-exceptions"><strong>'+r.missing.length+' item(s) requiring confirmation</strong><ul>'+r.missing.map(x=>'<li>'+esc(x)+'</li>').join('')+'</ul></div>':'<p class="notice">Required setup details complete. Ready for customer signature.</p>')+
 '<details class="sq-setup-section" '+(r.missing.length?'open':'')+'><summary>Customer, Sage and billing details</summary>'+
 '<div class="sq-setup-grid">'+
 field('sage_account_ref','Verified Sage account')+field('sicon_site_ref','Verified Sicon site')+
 field('contract_reference','Contract reference')+
 field('billing_frequency','Billing frequency')+
 field('purchase_order','Purchase order (where required)')+
 field('billing_email','Billing email','email')+
 field('billing_stock_code','Sicon maintenance billing stock code')+
 field('warehouse_name','Sicon warehouse')+
 field('sicon_delivery_address','Sicon delivery address reference')+
 field('sicon_customer_ref','Sicon customer reference')+
 field('sicon_location_description','Sicon location description')+
 field('sla_name','Approved Sicon SLA name')+
 field('equipment_make','Verified equipment manufacturer (if shared)')+
 '</div><button type="button" id="sqVerifyDetails" class="button button-primary" '+(r.contract_import_confirmed?'disabled':'')+'>Save verified details</button></details>'+
 (quote.equipment.some(a=>a.quantity>(v.verified_serials?.[a.source_line_id]||a.serial_numbers).filter(Boolean).length)?
 '<details class="sq-setup-section" open><summary>Verify missing machine serial numbers</summary>'+
 '<p class="mini-note">One serial per machine. Verified corrections remain separate from the accepted quotation.</p>'+
 quote.equipment.filter(a=>a.quantity>(v.verified_serials?.[a.source_line_id]||a.serial_numbers).filter(Boolean).length).map(a=>
 '<div class="sq-serial-row"><strong>'+esc(a.item_code)+'</strong><span>Qty '+a.quantity+'</span>'+
 '<input class="input" data-sq-serial="'+esc(a.source_line_id)+'" placeholder="Serial numbers, separated by commas" value="'+esc((v.verified_serials?.[a.source_line_id]||a.serial_numbers).join(', '))+'">'+
 '<button class="button button-outline" data-sq-serial-verify="'+esc(a.source_line_id)+'" type="button">Verify</button></div>').join('')+
 '<label class="sq-field"><span>Where the serial information was confirmed</span><input class="input" id="sqSerialEvidence" placeholder="e.g. Service visit or verified asset register"></label></details>':'')+
 '<details class="sq-setup-section" '+(r.agreement_ready&&!r.agreement_signed?'open':'')+'><summary>Signed customer maintenance agreement</summary>'+
 '<p class="mini-note">Generate an internal agreement draft from the approved source template, check it with the customer, then record the signed copy. Never send the watermarked draft for signature.</p>'+
 '<div class="actions-row"><button type="button" class="button button-outline" id="sqAgreementPreview" '+(!r.agreement_ready?'disabled':'')+'>Preview populated agreement</button></div>'+
 (setup.signed_document?'<p class="notice">Signed agreement recorded: '+esc(setup.signed_filename)+' · '+esc(setup.signed_sha256.slice(0,12))+'… <a href="/api/smartquote/setups/'+id+'/signed-agreement">Open verified signed PDF</a></p>':
 '<div class="actions-row"><input type="file" id="sqSignedPdf" class="input" accept=".pdf,application/pdf"><label><input type="checkbox" id="sqSignatureChecked"> I have checked the required signatures</label><button class="button button-primary" id="sqSaveSigned" type="button" '+(!r.agreement_ready?'disabled':'')+'>Record signed agreement</button></div>')+
 '</details>'+
 '<details class="sq-setup-section" '+(r.contract_import_ready?'open':'')+'><summary>Sicon contract import — first</summary>'+
 '<p class="mini-note">The structured preview is not a Sicon-ready Excel import. Generate the contract import using the approved mapping, complete the Sicon upload, then record its confirmed reference here.</p>'+
 '<p>'+plans.contract_import.staged_billing_groups.length+' contract commencement group(s) · '+plans.contract_import.staged_billing_groups.reduce((n,x)=>n+x.machine_units,0)+' equipment units</p>'+
 '<div class="actions-row"><button type="button" class="button button-outline" id="sqContractExcel" '+(!r.contract_import_ready?'disabled':'')+'>Prepare contract Excel (review only)</button></div>'+
 (r.contract_import_confirmed?'<p class="notice">Sicon contract '+esc(setup.sicon_contract_reference)+' verified.</p>':
 '<div class="sq-setup-grid">'+
 '<label class="sq-field"><span>Confirmed Sicon contract number</span><input id="sqSiconContract" class="input" placeholder="Sicon contract reference"></label>'+
 '<label class="sq-field"><span>Import confirmation or evidence</span><input id="sqSiconContractProof" class="input" placeholder="Import log / reviewed Sicon entry"></label></div>'+
 '<button class="button button-primary" id="sqConfirmContract" type="button" '+(!r.contract_import_ready?'disabled':'')+'>Confirm contract imported</button>')+'</details>'+
 '<details class="sq-setup-section" '+(r.equipment_import_ready?'open':'')+'><summary>Sicon equipment import — second</summary>'+
 '<p class="mini-note">Equipment should be linked to the confirmed Sicon contract. Future cover dates remain scheduled and must not be treated as already activated.</p>'+
 '<p>'+plans.equipment_import.individual_machine_records.length+' individual equipment record(s) prepared for mapping verification.</p>'+
 '<div class="actions-row"><button type="button" class="button button-outline" id="sqEquipmentExcel" '+(!r.equipment_import_ready?'disabled':'')+'>Prepare due equipment Excel (review only)</button></div>'+
 '<p class="mini-note">'+r.imported_equipment_groups.length+' start-date group(s) recorded; '+r.future_equipment_groups.length+' future group(s) still to commence. Each group requires its own confirmed import.</p>'+
 (r.equipment_import_confirmed?'<p class="notice">Equipment batch '+esc(setup.sicon_equipment_batch_reference)+' confirmed.</p>':
 '<div class="sq-setup-grid"><label class="sq-field"><span>Machines starting</span><select id="sqEquipmentDate" class="input">'+r.due_equipment_groups.map(d=>'<option value="'+esc(d)+'">'+esc(d)+'</option>').join('')+'</select></label><label class="sq-field"><span>Equipment import batch reference</span><input id="sqSiconEquipment" class="input" placeholder="Batch reference"></label>'+
 '<label class="sq-field"><span>Import confirmation or evidence</span><input id="sqSiconEquipmentProof" class="input" placeholder="Sicon equipment import log"></label></div>'+
 '<button class="button button-primary" id="sqConfirmEquipment" type="button" '+(!r.equipment_import_ready?'disabled':'')+'>Confirm equipment imported</button>')+'</details>'+
 '<details class="sq-setup-section"><summary>Audit history</summary>'+
 (setup.events.length?'<ul class="sq-events">'+setup.events.map(e=>'<li>'+esc(e.at.slice(0,16))+' · '+esc(e.action)+' · '+esc(e.actor)+'</li>').join('')+'</ul>':'<p class="mini-note">No setup changes recorded yet.</p>')+
 '</details></section>';
 const send=async(url,body)=>{
   const response=await api(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
   toast('Contract setup updated');await sqShowSetup(id,quote);return response;
 };
 const documentLink=async(path)=>{
  // Same-origin authenticated fetch keeps validation errors inside the workbench.
  try{
   const res=await fetch(path,{credentials:'same-origin',cache:'no-store'});
   if(!res.ok){let message='Unable to prepare document';try{const body=await res.json();message=body.detail||message}catch(_){}throw new Error(message)}
   const content=await res.blob(),header=res.headers.get('Content-Disposition')||'';
   const match=/filename="?([^";]+)"?/i.exec(header);
   const filename=match?match[1]:'contract_handover_review';
   const link=document.createElement('a'),url=URL.createObjectURL(content);
   link.href=url;link.download=filename;document.body.appendChild(link);link.click();link.remove();
   setTimeout(()=>URL.revokeObjectURL(url),5000);
   toast('Review-only document prepared. Check against the approved Sicon mapping.');
  }catch(e){toast(e.message,true)}
 };
 if($('#sqAgreementPreview'))$('#sqAgreementPreview').onclick=()=>documentLink('/api/smartquote/setups/'+id+'/agreement-preview');
 if($('#sqContractExcel'))$('#sqContractExcel').onclick=()=>documentLink('/api/smartquote/setups/'+id+'/sicon-contract-draft');
 if($('#sqEquipmentExcel'))$('#sqEquipmentExcel').onclick=()=>{
  const selected=$('#sqEquipmentDate')?.value||r.due_equipment_groups[0];
  if(!selected){toast('No equipment start date is due for import',true);return}
  documentLink('/api/smartquote/setups/'+id+'/sicon-equipment-draft?start_date='+encodeURIComponent(selected));
 };
 const save=$('#sqVerifyDetails');
 if(save)save.onclick=async()=>{
  const payload={revision:setup.revision};
  target.querySelectorAll('[data-sq-setup-field]').forEach(f=>payload[f.dataset.sqSetupField]=f.value.trim());
  try{await send('/api/smartquote/setups/'+id+'/details',payload)}catch(e){toast(e.message)}
 };
 target.querySelectorAll('[data-sq-serial-verify]').forEach(button=>button.onclick=async()=>{
  const source_line_id=button.dataset.sqSerialVerify,box=[...target.querySelectorAll('[data-sq-serial]')].find(x=>x.dataset.sqSerial===source_line_id);
  const serial_numbers=box.value.split(',').map(x=>x.trim()).filter(Boolean);
  try{await send('/api/smartquote/setups/'+id+'/verify-serials',{revision:setup.revision,source_line_id,serial_numbers,evidence:$('#sqSerialEvidence')?.value||''})}catch(e){toast(e.message)}
 });
 if($('#sqSaveSigned'))$('#sqSaveSigned').onclick=async()=>{
  const file=$('#sqSignedPdf').files?.[0];if(!file){toast('Choose the signed agreement PDF');return}
  if(file.size>15*1024*1024){toast('PDF must be under 15 MB');return}
  try{
   const bytes=new Uint8Array(await file.arrayBuffer());let binary='';
   for(let i=0;i<bytes.length;i+=16384)binary+=String.fromCharCode(...bytes.subarray(i,i+16384));
   await send('/api/smartquote/setups/'+id+'/signed-agreement',{filename:file.name,pdf_base64:btoa(binary),signatures_checked:$('#sqSignatureChecked').checked});
  }catch(err){toast(err.message)}
 };
 if($('#sqConfirmContract'))$('#sqConfirmContract').onclick=async()=>{
  try{await send('/api/smartquote/setups/'+id+'/confirm-sicon-contract',{sicon_contract_reference:$('#sqSiconContract').value,evidence:$('#sqSiconContractProof').value})}catch(err){toast(err.message)}
 };
 if($('#sqConfirmEquipment'))$('#sqConfirmEquipment').onclick=async()=>{
  try{await send('/api/smartquote/setups/'+id+'/confirm-sicon-equipment',{start_date:$('#sqEquipmentDate').value,sicon_equipment_batch_reference:$('#sqSiconEquipment').value,evidence:$('#sqSiconEquipmentProof').value})}catch(err){toast(err.message)}
 };
}
