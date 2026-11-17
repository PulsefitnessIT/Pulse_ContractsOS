/* Pulse Fitness 15-tab source registers: deliberately read-only.
   Entries marked VERIFY are source evidence, not certified PPM obligations. */
let masterSourcePageOffset=0;
let masterSourcePageSheet='';
let masterSourcePageFilter='';

async function masterSourcesPage(){
  const listing=await api('/api/master-sources');
  if(view!=='master_sources')return;
  const available=listing.sheets||[];
  content.innerHTML=
    '<div class="page-heading"><div>'+
    '<p class="eyebrow">PULSE FITNESS / SOURCE DATA</p>'+
    '<h1>Service, MOD &amp; Sicon source registers</h1>'+
    '<p>Review the additional worksheets from the 15-tab Maintenance Master. '+
    'These are original evidence, not new live agreements or approved PPM entitlements.</p>'+
    '</div></div>'+
    '<section class="panel"><div class="notice warning">'+
    esc(listing.warning||'Source rows require review before contractual use.')+
    '</div>'+
    '<div class="kpi-grid">'+available.map(item=>
      '<div class="card kpi"><div class="kpi-label">'+esc(item.name)+'</div>'+
      '<div class="kpi-value">'+esc(item.records)+'</div>'+
      '<div class="kpi-footer">Original worksheet rows (source only)</div></div>'
    ).join('')+'</div></section>'+
    '<section class="panel"><h3>Find a source record</h3>'+
    '<div class="form-grid">'+
    '<label>Worksheet<select id="sourceReviewSheet" class="select">'+
    available.map(item=>'<option value="'+esc(item.name)+'">'+
      esc(item.name)+'</option>').join('')+
    '</select></label>'+
    '<label>Search site, contract, item or source note'+
    '<input id="sourceReviewQuery" class="input" maxlength="100" '+
    'placeholder="Search original worksheet contents"></label>'+
    '</div><div class="actions-row">'+
    '<button id="sourceReviewSearch" class="button button-primary" type="button">Search source records</button>'+
    '<button id="sourceReviewClear" class="button button-outline" type="button">Clear</button>'+
    '</div><div id="sourceReviewRecords" aria-live="polite"></div></section>';
  if(!listing.has_15_tab_source){
    document.querySelector('#sourceReviewRecords').textContent=
      'The 15-tab source snapshots have not been loaded on this PC. '+
      'Keep the original workbook intact and use the approved import process.';
    return;
  }
  const sheetSelect=document.querySelector('#sourceReviewSheet');
  if(masterSourcePageSheet&&available.some(x=>x.name===masterSourcePageSheet))
    sheetSelect.value=masterSourcePageSheet;
  document.querySelector('#sourceReviewQuery').value=masterSourcePageFilter;
  sheetSelect.addEventListener('change',()=>{
    masterSourcePageSheet=sheetSelect.value;
    masterSourcePageOffset=0;
    loadMasterSourceRows();
  });
  document.querySelector('#sourceReviewSearch').addEventListener('click',()=>{
    masterSourcePageSheet=sheetSelect.value;
    masterSourcePageFilter=document.querySelector('#sourceReviewQuery').value;
    masterSourcePageOffset=0;
    loadMasterSourceRows();
  });
  document.querySelector('#sourceReviewQuery').addEventListener('keydown',event=>{
    if(event.key==='Enter'){
      event.preventDefault();
      document.querySelector('#sourceReviewSearch').click();
    }
  });
  document.querySelector('#sourceReviewClear').addEventListener('click',()=>{
    masterSourcePageOffset=0;
    masterSourcePageFilter='';
    document.querySelector('#sourceReviewQuery').value='';
    loadMasterSourceRows();
  });
  if(!masterSourcePageSheet)masterSourcePageSheet=sheetSelect.value;
  await loadMasterSourceRows();
}

async function loadMasterSourceRows(){
  const host=document.querySelector('#sourceReviewRecords');
  if(!host||view!=='master_sources')return;
  const sheet=masterSourcePageSheet||
    document.querySelector('#sourceReviewSheet').value;
  host.textContent='Loading source register…';
  try{
    const record=await api('/api/master-sources/'+encodeURIComponent(sheet)+
      '?'+qs({q:masterSourcePageFilter,offset:masterSourcePageOffset,limit:50}));
    if(view!=='master_sources'||!document.querySelector('#sourceReviewRecords'))return;
    const choose=['Customer / site','Contract number','Contract start date',
      'Cover expiry','Service date','Next service due','Services / year',
      'Service year key (internal)','Entitlement status (internal)',
      'Match status','Register match (internal)','Sicon contract ID',
      'Sicon line ID','Sage unit price (£ ex VAT)'];
    const show=(record.rows||[]).flatMap(r=>Object.keys(r.fields||{}));
    const headers=choose.filter(h=>show.includes(h)).slice(0,6);
    if(!headers.length)headers.push(...[...new Set(show)].slice(0,6));
    host.innerHTML='<p class="fine-print">'+esc(record.total)+' rows matching · '+
      esc(record.sheet)+' · source evidence only. Never assume VERIFY means booked, '+
      'completed or owed service.</p>'+
      '<div class="scroll-table"><table class="data-table">'+
      '<thead><tr><th>Excel row</th>'+headers.map(h=>'<th>'+esc(h)+'</th>').join('')+
      '<th>Original fields</th></tr></thead><tbody>'+
      record.rows.map(item=>'<tr><td>'+esc(item.source_row)+'</td>'+
        headers.map(h=>'<td>'+esc(String(item.fields[h]??''))+'</td>').join('')+
        '<td><details><summary>All source fields</summary>'+
        '<dl>'+Object.entries(item.fields).filter(([k,v])=>
          String(v??'').trim()).map(([k,v])=>
          '<dt><strong>'+esc(k)+'</strong></dt><dd>'+esc(String(v))+'</dd>'
        ).join('')+'</dl></details></td></tr>'
      ).join('')+'</tbody></table></div>'+
      '<div class="actions-row"><button class="button button-outline" id="sourcePrevious" '+
      (masterSourcePageOffset===0?'disabled':'')+'>Previous 50</button>'+
      '<button class="button button-outline" id="sourceNext" '+
      (masterSourcePageOffset+record.rows.length>=record.total?'disabled':'')+
      '>Next 50</button></div>';
    document.querySelector('#sourcePrevious').addEventListener('click',()=>{
      masterSourcePageOffset=Math.max(0,masterSourcePageOffset-50);
      loadMasterSourceRows();
    });
    document.querySelector('#sourceNext').addEventListener('click',()=>{
      masterSourcePageOffset+=50;
      loadMasterSourceRows();
    });
  }catch(error){
    host.innerHTML='<div class="notice warning">'+esc(error.message)+'</div>';
  }
}
