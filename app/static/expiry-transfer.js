/* Safe expired-register cut/paste replacement for the coordinator team.
 * Candidate dates are unverified until staff confirm them against an agreement.
 * Each selected contract is version-locked; no automatic archive on date.
 */
let expiryTransferItems=[];
let expiryTransferOffset=0;

async function showExpiredTransfer(){
  if(view!=='contracts')return;
  const old=document.querySelector('#expiredTransferHost');
  if(old){old.remove();return;}
  const bar=document.querySelector('.main-inner .toolbar');
  if(!bar)return;
  const panel=document.createElement('section');
  panel.id='expiredTransferHost';
  panel.className='card panel';
  panel.style.marginBottom='18px';
  panel.innerHTML=
    '<div class="section-head"><div><h2>Move expired contracts to history</h2>'+
    '<p>Select verified expired agreements and transfer them safely to the Expired register. '+
    'The 31 main columns stay aligned; additional historical columns are retained at the end.</p>'+
    '</div><button class="button button-outline" type="button" id="expiredTransferClose">'+
    'Close</button></div>'+
    '<div class="toolbar"><label>Source register '+
    '<select class="select" id="expiredTransferSource">'+
    '<option value="Maintenance Database">Maintenance Database</option>'+
    '<option value="MOD">MOD</option></select></label>'+
    '<button class="button button-outline" type="button" id="expiredTransferRefresh">'+
    'Refresh expired agreements</button></div>'+
    '<p class="fine-print">An expiry date alone does not prove that the customer has '+
    'cancelled or not renewed. Confirm each agreement before selecting it.</p>'+
    '<p id="expiredTransferMessage" role="status" aria-live="polite"></p>'+
    '<div id="expiredTransferSummary"></div>'+
    '<div id="expiredTransferRows"></div>'+
    '<div id="expiredTransferConfirmation"></div>';
  bar.parentNode.insertBefore(panel,bar);
  document.querySelector('#expiredTransferClose').onclick=()=>panel.remove();
  document.querySelector('#expiredTransferRefresh').onclick=()=>loadExpiryTransfer(0);
  document.querySelector('#expiredTransferSource').onchange=()=>loadExpiryTransfer(0);
  await loadExpiryTransfer(0);
}

async function loadExpiryTransfer(offset=0){
  if(view!=='contracts')return;
  const host=document.querySelector('#expiredTransferHost');
  if(!host)return;
  expiryTransferItems=[];
  expiryTransferOffset=offset;
  const source=host.querySelector('#expiredTransferSource').value;
  const message=host.querySelector('#expiredTransferMessage');
  const summary=host.querySelector('#expiredTransferSummary');
  const rows=host.querySelector('#expiredTransferRows');
  const confirmation=host.querySelector('#expiredTransferConfirmation');
  confirmation.innerHTML='';
  summary.innerHTML='';
  rows.innerHTML='';
  message.textContent='Checking verified Master headings and current agreement expiry dates…';
  try{
    const result=await api('/api/contracts/expiry-transfer/preview?'+qs({
      source_sheet:source,limit:40,offset
    }));
    if(view!=='contracts'||!document.querySelector('#expiredTransferHost'))return;
    expiryTransferItems=result.items||[];
    const fields=result.columns||{};
    summary.innerHTML=
      '<p><strong>'+esc(result.total_candidates)+'</strong> candidate expired agreements '+
      ' · '+esc(fields.shared)+' shared fields '+
      ' · '+esc(fields.historical_only)+' historical-only fields (retained)' +
      ' · '+esc(result.not_yet_expired)+' agreements not yet due '+
      ' · '+esc(result.missing_or_invalid_expiry)+' missing dates '+
      ' · '+esc(result.identity_exceptions)+' identity exceptions</p>';
    rows.innerHTML=
      '<div style="overflow-x:auto"><table class="data-table"><thead><tr>'+
      '<th><input type="checkbox" id="expirySelectAll" aria-label="Select all visible"></th>'+
      '<th>Customer / site</th><th>Contract</th><th>Cover</th>'+
      '<th>Sales manager</th><th>Expired</th><th>Days overdue</th></tr></thead><tbody>'+
      (expiryTransferItems.length?expiryTransferItems.map((item,index)=>
        '<tr><td><input type="checkbox" class="expiry-row-check" data-index="'+index+
        '" aria-label="Select '+esc(item.customer_site)+'"></td>'+
        '<td>'+esc(item.customer_site)+'</td>'+
        '<td>'+esc(item.contract_number||item.row_key)+'</td>'+
        '<td>'+esc(item.contract_type||'—')+'</td>'+
        '<td>'+esc(item.sales_manager||'—')+'</td>'+
        '<td>'+esc(formatDate(item.expiry_date))+'</td>'+
        '<td>'+esc(item.days_expired)+'</td></tr>').join(''):
        '<tr><td colspan="7">No overdue agreements in this register.</td></tr>')+
      '</tbody></table></div>'+
      '<div class="table-footer">'+
      '<span>Showing '+esc(expiryTransferItems.length?offset+1:0)+'–'+
      esc(offset+expiryTransferItems.length)+' of '+esc(result.total_candidates)+'</span>'+
      '<div class="pager"><button type="button" id="expiryPrev" '+(offset?'':'disabled')+
      '>← Previous</button><button type="button" id="expiryNext" '+
      (offset+expiryTransferItems.length<result.total_candidates?'':'disabled')+
      '>Next →</button></div></div>';
    rows.querySelector('#expiryPrev').onclick=()=>loadExpiryTransfer(Math.max(0,offset-40));
    rows.querySelector('#expiryNext').onclick=()=>loadExpiryTransfer(offset+40);
    const all=rows.querySelector('#expirySelectAll');
    all.onchange=()=>rows.querySelectorAll('.expiry-row-check').forEach(x=>x.checked=all.checked);
    rows.querySelectorAll('.expiry-row-check').forEach(x=>x.onchange=()=>{
      all.checked=Array.from(rows.querySelectorAll('.expiry-row-check')).every(c=>c.checked);
    });
    confirmation.innerHTML=
      '<form id="expiredTransferForm">'+
      '<label>Reason for the selected contracts being moved into history '+
      '<textarea name="reason" minlength="12" maxlength="500" rows="2" required '+
      'placeholder="Confirmed against agreements; no renewal recorded..."></textarea></label>'+
      '<label><input name="confirm_verified_expiry_and_no_renewal" type="checkbox" required> '+
      'I have checked every selected agreement and verified its expiry, '+
      'and confirmed that no renewal or extension should keep it active.</label>'+
      '<button type="submit" class="button button-primary">'+
      'Transfer selected agreements to Expired</button></form>'+
      '<p class="fine-print">The application creates a verified recovery backup, '+
      'preserves all record fields, attached equipment and contract history, '+
      'and records who confirmed the transfer. The Excel Master changes only '+
      'when you download the next export.</p>';
    confirmation.querySelector('form').addEventListener('submit',submitExpiryTransfers);
    message.textContent='Ready for individual review. No contracts have been transferred.';
  }catch(error){
    message.textContent='Transfer unavailable: '+error.message;
  }
}

async function submitExpiryTransfers(event){
  event.preventDefault();
  const form=event.currentTarget;
  if(!form.reportValidity())return;
  const host=document.querySelector('#expiredTransferHost');
  if(!host)return;
  const checked=Array.from(host.querySelectorAll('.expiry-row-check:checked'));
  const message=host.querySelector('#expiredTransferMessage');
  if(!checked.length){
    message.textContent='Select at least one agreement after verifying its expiry.';
    return;
  }
  if(checked.length>40){
    message.textContent='Select no more than 40 agreements per reviewed transfer.';
    return;
  }
  const selected=checked.map(box=>expiryTransferItems[Number(box.dataset.index)]);
  const inputs=new FormData(form);
  const source=host.querySelector('#expiredTransferSource').value;
  if(selected.some(x=>!x||x.source_sheet!==source)){
    message.textContent='The selection changed. Refresh the candidates and review again.';
    return;
  }
  if(!window.confirm('Transfer '+selected.length+
      ' selected and verified agreements to Expired? They will no longer be Active.')){
    return;
  }
  const button=form.querySelector('button[type="submit"]');
  button.disabled=true;
  message.textContent='Creating a verified backup and moving selected records atomically…';
  try{
    const request={
      items:selected.map(item=>({
        contract_id:item.contract_id,expected_revision:item.expected_revision,
        row_key:item.row_key,source_sheet:item.source_sheet,
        source_row:item.source_row,expiry_date:item.expiry_date
      })),
      reason:String(inputs.get('reason')||'').trim(),
      confirm_verified_expiry_and_no_renewal:inputs.has('confirm_verified_expiry_and_no_renewal')
    };
    const result=await api('/api/contracts/expiry-transfer/apply',{
      method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify(request)
    });
    message.textContent='Transferred '+result.transferred+
      ' contracts into Expired and recorded the source-to-destination row history. '+
      'A recovery backup was verified. Download the Excel Master to receive these changes.';
    await refreshMeta();
    await loadContracts();
    await loadExpiryTransfer(0);
    const target=document.querySelector('#expiredTransferMessage');
    if(target)target.textContent=result.transferred+
      ' verified agreements transferred. All other records and historic columns preserved.';
  }catch(error){
    message.textContent='No partial transfer: '+error.message;
  }finally{button.disabled=false;}
}
