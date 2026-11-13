/* Source-backed action list. Excel remains authoritative during the pilot. */
let actionFilter={search:'',sheet:'',status:'',kind:'',offset:0,limit:100};
let actionUserCanWrite=false;
const ACTION_STATUSES=['Open','In progress','Awaiting Customer','Awaiting PO',
  'Blocked','Completed','Not Applicable'];
const ACTION_KIND_LABEL={
  follow_up:'Next action',renewal_review:'Renewal review',missing_expiry:'Missing expiry'
};

async function actionCentrePage() {
  content.innerHTML='<div class="main-inner">' +
    heading('Coordinator Action Centre',
      'Daily actions sourced from the latest imported Maintenance Database and MOD records.') +
    '<div class="notice">A date in the past does not prove that an action is incomplete. ' +
    'Record the result here, and continue updating the working Excel Master during the transition.</div>' +
    '<div class="toolbar">' +
    '<input id="actionSearch" class="input search" placeholder="Search site, contract, task or sales manager" ' +
      'value="'+esc(actionFilter.search)+'">' +
    '<select id="actionSheet" class="select"><option value="">All current registers</option>' +
      '<option value="Maintenance Database">Maintenance Database</option><option value="MOD">MOD</option></select>' +
    '<select id="actionStatus" class="select"><option value="">All statuses</option>' +
      ACTION_STATUSES.map(s=>'<option value="'+esc(s)+'">'+esc(s)+'</option>').join('') +
    '</select><select id="actionKind" class="select"><option value="">All actions</option>' +
      Object.entries(ACTION_KIND_LABEL).map(([key,label])=>
        '<option value="'+esc(key)+'">'+esc(label)+'</option>').join('') +
    '</select></div><div id="actionSummary" class="kpi-grid"></div>' +
    '<div id="actionResults"><div class="loading">Reading recorded actions…</div></div>' +
    '<div id="actionPager" class="table-footer"></div></div>';
  const user=await api('/api/pilot/me');
  actionUserCanWrite=Boolean(user?.pilot && ['Admin','Coordinator'].includes(user.role));
  if(view!=='action_centre')return;
  for(const [id,key] of [['actionSheet','sheet'],['actionStatus','status'],['actionKind','kind']]) {
    const el=document.getElementById(id);
    el.value=actionFilter[key];
    el.addEventListener('change',()=>{
      actionFilter[key]=el.value;actionFilter.offset=0;loadActionCentre().catch(e=>toast(e.message));
    });
  }
  let debounce;
  document.getElementById('actionSearch').addEventListener('input',e=>{
    clearTimeout(debounce);
    actionFilter.search=e.target.value;actionFilter.offset=0;
    debounce=setTimeout(()=>loadActionCentre().catch(x=>toast(x.message)),250);
  });
  return loadActionCentre();
}
async function loadActionCentre() {
  const query=qs(actionFilter);
  const data=await api('/api/action-centre?'+query);
  if(view!=='action_centre')return;
  const counts=data.summary||{};
  const countsToShow=[
    ['Overdue review',counts['Overdue review']||0],
    ['Due today',counts['Due today']||0],
    ['Due within 7 days',counts['Due within 7 days']||0],
    ['Date missing / check',counts['Date missing / check']||0]
  ];
  document.querySelector('#actionSummary').innerHTML=countsToShow.map(([label,n])=>
    '<div class="card kpi"><div class="kpi-label">'+esc(label)+'</div>' +
    '<div class="kpi-value">'+esc(n)+'</div>' +
    '<div class="kpi-footer">Recorded site tasks; not verified as outstanding</div></div>').join('');
  const items=data.items||[];
  const html=items.map((task)=>{
    const closed=task.status==='Completed'||task.status==='Not Applicable';
    const fields='<div class="action-edit" data-task="'+esc(task.task_id)+'">' +
      '<select class="select" data-field="status" aria-label="Action status">' +
      ACTION_STATUSES.map(s=>'<option '+(s===task.status?'selected':'')+'>'+esc(s)+'</option>').join('') +
      '</select>' +
      '<input class="input" data-field="note" maxlength="1500" value="'+esc(task.note||'')+'" ' +
      'placeholder="Action evidence or follow-up note" aria-label="Action note">' +
      '<label class="fine-print">Review again <input class="input" data-field="snooze" type="date" ' +
      'value="'+esc(task.snooze_until||'')+'"></label>' +
      '<button class="button button-outline" data-save-task="'+esc(task.task_id)+'">Record update</button>' +
      '</div>';
    return '<tr><td class="name">'+esc(task.customer_site)+
      '<div class="fine-print">'+esc(task.sheet)+' · '+esc(task.contract_reference||'No contract ref')+
      ' · '+esc(task.sales_manager||'Manager not recorded')+'</div></td>' +
      '<td><strong>'+esc(ACTION_KIND_LABEL[task.kind]||task.kind)+'</strong>' +
      '<div>'+esc(task.description)+'</div>' +
      (task.kind==='renewal_review' ? '<button type="button" class="button button-outline" ' +
        'data-start-quote="'+esc(task.contract_id)+'" data-quote-site="'+esc(task.customer_site)+'">' +
        'Prepare unpriced SmartQuote draft</button>' : '') + '</td>' +
      '<td>'+esc(task.recorded_due_date||'No recorded date')+
      (task.snooze_until?'<div class="fine-print">Reviewed again: '+esc(task.snooze_until)+'</div>':'')+'</td>' +
      '<td>'+chip(task.urgency)+'<div class="fine-print">'+esc(task.status)+
      '</div></td>' +
      '<td>'+ (actionUserCanWrite?fields:
        '<span class="fine-print">'+esc(task.status)+(task.last_updated_by?
        ' · '+esc(task.last_updated_by):'')+'</span>') +'</td></tr>';
  }).join('');
  document.querySelector('#actionResults').innerHTML=
    '<div class="table-shell"><div class="scroll-table compact-table">' +
    '<table class="data-table"><thead><tr><th>Customer / source</th><th>Action</th>' +
    '<th>Source due date</th><th>Priority / status</th><th>Update status</th></tr></thead><tbody>' +
    (html||'<tr><td colspan="5">No recorded actions match these filters.</td></tr>') +
    '</tbody></table></div></div>' +
    '<p class="fine-print">Completion statuses are stored with a staff identity and event history. ' +
    'They do not automatically overwrite Excel, renew agreements or change Sage/Sicon.</p>';
  document.querySelectorAll('[data-start-quote]').forEach(button=>{
    button.addEventListener('click',()=>{
      window.unifiedSourceFromAction={
        contract_id:Number(button.dataset.startQuote),
        site_label:button.dataset.quoteSite
      };
      setView('quoting');
    });
  });
  const begin=data.offset+1,end=data.offset+items.length;
  document.querySelector('#actionPager').innerHTML=
    '<span>'+ (data.total ? esc(begin)+'–'+esc(end)+' of '+esc(data.total) : 'No actions') +
    '</span><div class="pager"><button id="actionsPrevious"'+
    (!data.offset?' disabled':'')+'>Previous</button><button id="actionsNext"'+
    (end>=data.total?' disabled':'')+'>Next</button></div>';
  document.querySelector('#actionsPrevious').onclick=()=> {
    actionFilter.offset=Math.max(0,actionFilter.offset-actionFilter.limit);
    loadActionCentre().catch(e=>toast(e.message));
  };
  document.querySelector('#actionsNext').onclick=()=> {
    actionFilter.offset+=actionFilter.limit;loadActionCentre().catch(e=>toast(e.message));
  };
  if(!actionUserCanWrite)return;
  document.querySelectorAll('[data-save-task]').forEach(button=>{
    button.addEventListener('click',async()=>{
      const holder=button.closest('.action-edit');
      const taskId=button.dataset.saveTask;
      const status=holder.querySelector('[data-field=status]').value;
      const note=holder.querySelector('[data-field=note]').value;
      const snooze=holder.querySelector('[data-field=snooze]').value;
      button.disabled=true;
      try {
        await api('/api/action-centre/'+encodeURIComponent(taskId)+'/status',{
          method:'POST',headers:{'Content-Type':'application/json'},
          body:JSON.stringify({status,note,snooze_until:snooze||null})
        });
        toast('Action update recorded with audit history');
        await loadActionCentre();
      }catch(e){toast('No update saved: '+e.message);button.disabled=false;}
    });
  });
}
