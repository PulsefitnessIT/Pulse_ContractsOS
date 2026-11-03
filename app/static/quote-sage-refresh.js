/* Admin-only Sage price-list refresh. All writes are secured server-side.
 * Original Sage and existing customer quotes stay untouched.
 */
let sageRefreshPreview=null;
let sageRefreshActiveSnapshot=null;
let sageRefreshChangesOffset=0;
let sageRefreshChangesKind='';

async function initQuoteSageRefresh(){
  const host=document.querySelector('#quoteSageRefreshHost');
  if(!host || view!=='quoting')return;
  sageRefreshPreview=null;
  host.innerHTML=
    '<form id="sageRefreshUpload" class="form-grid">'+
    '<label>Full Sage item price-list export (CSV or XLSX) '+
    '<input type="file" name="file" accept=".csv,.xlsx" required></label>'+
    '<label>Export price-list date '+
    '<input type="date" name="source_date" required></label>'+
    '<button class="button button-outline" type="submit">Compare with current Sage list</button>'+
    '</form><p id="sageRefreshFeedback" role="status"></p>'+
    '<div id="sageRefreshPreview"></div>'+
    '<div id="sageRefreshCurrent"></div>'+
    '<div id="sageRefreshChanges"></div>';
  host.querySelector('#sageRefreshUpload').addEventListener('submit',quoteStageSageList);
  host.querySelector('#sageRefreshUpload').addEventListener('change',()=>{
    sageRefreshPreview=null;
    const panel=document.querySelector('#sageRefreshPreview');
    if(panel)panel.textContent='';
  });
  await quoteLoadSageHistory();
}

function sageRefreshCount(counts,key){return esc(counts?.[key]??0);}
function sageRefreshSummaryTable(counts){
  const names=[
    ['added','New item codes'],['price_changed','Prices changed'],
    ['details_changed','Descriptions/groups changed'],['removed','Item codes removed'],
    ['unchanged','Unchanged item codes']
  ];
  return '<div style="overflow-x:auto"><table class="data-table"><thead>'+
    '<tr><th>Change category</th><th>Count</th></tr></thead><tbody>'+
    names.map(([key,label])=>'<tr><td>'+esc(label)+'</td><td>'+
      sageRefreshCount(counts,key)+'</td></tr>').join('')+
    '</tbody></table></div>';
}
function sageRefreshRows(items){
  return '<div style="overflow-x:auto"><table class="data-table"><thead>'+
    '<tr><th>Item code</th><th>Change</th><th>Previous Sage price</th>'+
    '<th>Replacement price</th><th>Previous equipment</th><th>Updated equipment</th></tr></thead><tbody>'+
    (items||[]).map(row=>
      '<tr><td>'+esc(row.sku)+'</td><td>'+esc(row.kind||row.change_kind)+
      '</td><td>'+esc(row.previous_price===null?'—':money(row.previous_price))+
      '</td><td>'+esc(row.current_price===null?'—':money(row.current_price))+
      '</td><td>'+esc([row.previous_name,row.previous_group].filter(Boolean).join(' · ')||'—')+
      '</td><td>'+esc([row.current_name,row.current_group].filter(Boolean).join(' · ')||'—')+
      '</td></tr>').join('')+
    ((!items||!items.length)?'<tr><td colspan="6">No changes recorded.</td></tr>':'')+
    '</tbody></table></div>';
}

async function quoteStageSageList(event){
  event.preventDefault();
  const form=event.currentTarget;
  if(!form.reportValidity())return;
  const feedback=document.querySelector('#sageRefreshFeedback');
  const area=document.querySelector('#sageRefreshPreview');
  const button=form.querySelector('[type="submit"]');
  if(!feedback||!area||!button)return;
  sageRefreshPreview=null;
  area.textContent='';
  button.disabled=true;
  feedback.textContent='Reading the Sage export and comparing exact item codes…';
  try{
    const preview=await api('/api/quoting/sage-refresh/preview',{
      method:'POST',body:new FormData(form)
    });
    if(view!=='quoting'||!document.querySelector('#sageRefreshPreview'))return;
    sageRefreshPreview=preview;
    const warning=preview.large_removal_warning?
      '<p class="notice warning">This export removes an unusually high number of '+
      'Sage item codes. Check it is the FULL price list, not a partial filter.</p>'+
      '<label><input type="checkbox" name="confirm_large_removal"> '+
      'I have checked the removed codes and confirm full-list replacement.</label>':'';
    area.innerHTML=
      '<h4>Price-list comparison — pending activation</h4>'+
      '<p>File: '+esc(preview.filename)+' · Export date: '+esc(preview.source_date)+
      ' · Usable item codes: '+esc(preview.usable_rows)+
      ' · Excluded groups: '+esc(preview.excluded_group_rows)+
      ' · Invalid equipment rows: '+esc(preview.invalid_equipment_rows)+'</p>'+
      sageRefreshSummaryTable(preview.change_counts)+
      '<h5>Sample of detected differences ('+esc(preview.changes_total)+' total)</h5>'+
      sageRefreshRows(preview.changes_preview)+
      '<form id="sageRefreshActivateForm">'+warning+
      '<label>Reason for replacing the active Sage price list '+
      '<input name="reason" minlength="12" maxlength="500" required '+
      'placeholder="e.g. Full Sage Sales Price export dated…"></label>'+
      '<button type="submit" class="button button-primary">'+
      'Activate reviewed Sage price list</button></form>'+
      '<p class="fine-print">This replaces only the local Contracts OS Sage '+
      'pricing snapshot, retaining the old snapshot and changes. An existing '+
      'administrator price correction will be flagged if its source fingerprint changes.</p>';
    area.querySelector('#sageRefreshActivateForm').addEventListener('submit',quoteActivateSageList);
    feedback.textContent='Preview ready. Nothing has been activated yet.';
  }catch(error){
    feedback.textContent=error.message;
  }finally{button.disabled=false;}
}

async function quoteActivateSageList(event){
  event.preventDefault();
  const form=event.currentTarget;
  const feedback=document.querySelector('#sageRefreshFeedback');
  if(!sageRefreshPreview||!form.reportValidity()||!feedback)return;
  const data=new FormData(form);
  if(sageRefreshPreview.large_removal_warning&&!data.has('confirm_large_removal')){
    feedback.textContent='Confirm the large item-code removal risk before activation.';
    return;
  }
  const button=form.querySelector('[type="submit"]');
  button.disabled=true;
  feedback.textContent='Checking source version and committing reviewed price-list snapshot…';
  try{
    const result=await api('/api/quoting/sage-refresh/activate',{
      method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({
        preview_token:sageRefreshPreview.preview_token,
        reason:String(data.get('reason')||'').trim(),
        confirm_large_removal:data.has('confirm_large_removal')
      })
    });
    sageRefreshPreview=null;
    document.querySelector('#sageRefreshPreview').textContent='';
    unifiedClearPrice();
    feedback.textContent='Sage price-list snapshot '+result.snapshot_id+
      ' activated. Historical quotations are unchanged. Review source-bound '+
      'administrator price overrides before issuing any future quotations.';
    await quoteLoadSageHistory();
  }catch(error){feedback.textContent=error.message;}
  finally{button.disabled=false;}
}

async function quoteLoadSageHistory(){
  const host=document.querySelector('#sageRefreshCurrent');
  if(!host || view!=='quoting')return;
  try{
    const result=await api('/api/quoting/sage-refresh/status');
    if(view!=='quoting'||!document.querySelector('#sageRefreshCurrent'))return;
    sageRefreshActiveSnapshot=result.local_active?.id||null;
    const active=result.local_active;
    const rows=(result.history||[]).map(entry=>
      '<tr><td>'+esc(entry.id)+'</td><td>'+esc(entry.source_date)+
      '</td><td>'+esc(entry.usable_rows)+'</td><td>'+esc(entry.imported_by)+
      '</td><td>'+esc(entry.active?'Active':'Archived')+'</td><td>'+
      '<button type="button" class="button button-outline" data-sage-snapshot="'+
      esc(entry.id)+'">Review changes</button></td></tr>').join('');
    host.innerHTML='<h4>Local Sage source history</h4>'+
      '<p>'+(active?'Active snapshot '+esc(active.id)+
        ' · Effective '+esc(active.source_date)+
        ' · Imported '+esc(active.imported_at)+
        ' · '+esc(active.usable_rows)+' equipment codes':
        'No local Sage refresh activated yet. The original read-only V10 Sage '+
        'snapshot may still provide the current starting source.')+'</p>'+
      '<div style="overflow-x:auto"><table class="data-table"><thead>'+
      '<tr><th>Snapshot</th><th>Source date</th><th>Codes</th>'+
      '<th>Imported by</th><th>Status</th><th></th></tr></thead><tbody>'+
      (rows||'<tr><td colspan="6">No locally imported Sage price lists.</td></tr>')+
      '</tbody></table></div>';
    host.querySelectorAll('[data-sage-snapshot]').forEach(button=>
      button.addEventListener('click',()=>quoteShowSageChanges(Number(button.dataset.sageSnapshot))));
  }catch(error){host.textContent='Sage source history unavailable: '+error.message;}
}

async function quoteShowSageChanges(snapshotId,offset=0){
  const host=document.querySelector('#sageRefreshChanges');
  if(!host)return;
  sageRefreshChangesOffset=offset;
  host.textContent='Loading previous and replacement price evidence…';
  try{
    const result=await api('/api/quoting/sage-refresh/changes?'+new URLSearchParams({
      snapshot_id:snapshotId,kind:sageRefreshChangesKind,
      offset,limit:50
    }));
    if(view!=='quoting'||!document.querySelector('#sageRefreshChanges'))return;
    const next=offset+result.items.length;
    host.innerHTML='<h4>Snapshot '+esc(snapshotId)+' — recorded price-list changes</h4>'+
      '<label>Filter changes <select id="sageChangeKind">'+
      [['','All changes'],['price_changed','Prices changed'],
       ['added','Added codes'],['removed','Removed codes'],
       ['details_changed','Names or groups changed']]
        .map(([k,label])=>'<option value="'+esc(k)+'"'+
          (k===sageRefreshChangesKind?' selected':'')+'>'+esc(label)+'</option>').join('')+
      '</select></label>'+
      sageRefreshRows(result.items)+
      '<div style="display:flex;align-items:center;gap:0.5rem">'+
      '<button class="button button-outline" id="sagePrevChanges" type="button" '+
      (offset>0?'':'disabled')+'>Previous</button>'+
      '<button class="button button-outline" id="sageNextChanges" type="button" '+
      (next<result.total?'':'disabled')+'>Next</button>'+
      '<span>'+esc(offset?offset+1:result.total?1:0)+'–'+esc(next)+
      ' of '+esc(result.total)+'</span></div>';
    host.querySelector('#sageChangeKind').addEventListener('change',e=>{
      sageRefreshChangesKind=e.target.value;
      quoteShowSageChanges(snapshotId,0);
    });
    host.querySelector('#sagePrevChanges').addEventListener('click',()=>{
      quoteShowSageChanges(snapshotId,Math.max(0,offset-50));
    });
    host.querySelector('#sageNextChanges').addEventListener('click',()=>{
      quoteShowSageChanges(snapshotId,next);
    });
  }catch(error){host.textContent='Price-list changes unavailable: '+error.message;}
}
