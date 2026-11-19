/* Coordinator actions: responsive, auditable and readable without side-scrolling. */
let actionFilter={search:'',sheet:'',status:'',kind:'',offset:0,limit:100};
let actionUserCanWrite=false;
const ACTION_STATUSES=['Open','In progress','Awaiting Customer','Awaiting PO','Blocked','Completed','Not Applicable'];
const ACTION_KIND_LABEL={
  follow_up:'Next action',renewal_review:'Renewal review',missing_expiry:'Check expiry date'
};

async function actionCentrePage(){
  content.innerHTML='<div class="main-inner action-centre-page">'+
    heading('Coordinator Action Centre','Your upcoming tasks and agreement renewals.')+
    '<div class="notice">Older dates may describe completed work. Check the customer record before marking an action as outstanding.</div>'+
    '<div class="toolbar action-toolbar">'+
      '<input id="actionSearch" class="input search" aria-label="Search customer or task" placeholder="Search customer, contract, task or manager" value="'+esc(actionFilter.search)+'">'+
      '<select id="actionSheet" class="select" aria-label="Site category"><option value="">All sites</option>'+
        '<option value="Maintenance Database">Maintenance customers</option><option value="MOD">MOD customers</option></select>'+
      '<select id="actionStatus" class="select" aria-label="Action status"><option value="">All statuses</option>'+
        ACTION_STATUSES.map(s=>'<option value="'+esc(s)+'">'+esc(s)+'</option>').join('')+'</select>'+
      '<select id="actionKind" class="select" aria-label="Task type"><option value="">All actions</option>'+
        Object.entries(ACTION_KIND_LABEL).map(([key,label])=>
        '<option value="'+esc(key)+'">'+esc(label)+'</option>').join('')+'</select>'+
    '</div><div id="actionSummary" class="kpi-grid"></div>'+
    '<div id="actionResults" aria-live="polite">Loading your actions…</div>'+
    '<div id="actionPager" class="table-footer"></div></div>';
  const user=await api('/api/pilot/me');
  actionUserCanWrite=Boolean(user?.pilot&&['Admin','Coordinator'].includes(user.role));
  if(view!=='action_centre')return;
  for(const [id,key] of [['actionSheet','sheet'],['actionStatus','status'],['actionKind','kind']]){
    const el=document.getElementById(id);
    el.value=actionFilter[key];
    el.addEventListener('change',()=>{
      actionFilter[key]=el.value;actionFilter.offset=0;loadActionCentre().catch(e=>toast(e.message));
    });
  }
  let debounce;
  document.getElementById('actionSearch').addEventListener('input',event=>{
    clearTimeout(debounce);
    actionFilter.search=event.target.value;actionFilter.offset=0;
    debounce=setTimeout(()=>loadActionCentre().catch(error=>toast(error.message)),250);
  });
  return loadActionCentre();
}

async function loadActionCentre(){
  const data=await api('/api/action-centre?'+qs(actionFilter));
  if(view!=='action_centre')return;
  const counts=data.summary||{};
  const summary=[
    ['Overdue review',counts['Overdue review']||0],
    ['Due today',counts['Due today']||0],
    ['Due within 7 days',counts['Due within 7 days']||0],
    ['Date missing / check',counts['Date missing / check']||0]
  ];
  document.querySelector('#actionSummary').innerHTML=summary.map(([label,n])=>
    '<div class="card kpi"><div class="kpi-label">'+esc(label)+'</div>'+
    '<div class="kpi-value">'+esc(n)+'</div>'+
    '<div class="kpi-footer">Check whether still outstanding</div></div>').join('');

  const items=data.items||[];
  const cards=items.map(task=>{
    const isClosed=task.status==='Completed'||task.status==='Not Applicable';
    const actionName=ACTION_KIND_LABEL[task.kind]||task.kind;
    const when=task.recorded_due_date?formatDate(task.recorded_due_date):'Date to check';
    const update=actionUserCanWrite?
      '<div class="action-update" data-task="'+esc(task.task_id)+'">'+
        '<label>Progress <select class="select" data-field="status" aria-label="Progress for '+esc(task.customer_site)+'">'+
        ACTION_STATUSES.map(s=>'<option '+(s===task.status?'selected':'')+'>'+esc(s)+'</option>').join('')+
        '</select></label>'+
        '<details class="action-extra"><summary>Add notes or review date</summary>'+
          '<div class="action-extra-fields">'+
            '<label>What happened? <textarea class="input" data-field="note" maxlength="1500" rows="2" placeholder="Outcome or follow-up">'+esc(task.note||'')+'</textarea></label>'+
            '<label>Review again <input class="input" data-field="snooze" type="date" value="'+esc(task.snooze_until||'')+'"></label>'+
          '</div></details>'+
        '<button type="button" class="button button-outline action-save" data-save-task="'+esc(task.task_id)+'">Save update</button>'+
      '</div>':
      '<div class="action-readonly">Progress: '+esc(task.status)+'</div>';
    return '<article class="action-record card'+(isClosed?' is-complete':'')+'">'+
      '<div class="action-record-main">'+
        '<div class="action-record-customer"><span class="action-small-label">Customer / site</span>'+
          '<strong>'+esc(task.customer_site)+'</strong>'+
          '<span class="action-subtitle">'+esc(task.contract_reference||'Contract number not recorded')+
            (task.sales_manager?' · '+esc(task.sales_manager):'')+'</span></div>'+
        '<div class="action-record-task"><span class="action-small-label">Action</span>'+
          '<strong>'+esc(actionName)+'</strong><span>'+esc(task.description)+'</span>'+
          (task.kind==='renewal_review'?
          '<button type="button" class="button button-outline action-quote" data-start-quote="'+
            esc(task.contract_id)+'" data-quote-site="'+esc(task.customer_site)+'">Prepare renewal quote</button>':'')+
        '</div>'+
        '<div class="action-record-date"><span class="action-small-label">Due date</span>'+
          '<strong>'+esc(when)+'</strong>'+chip(task.urgency)+
          (task.snooze_until?'<span class="action-subtitle">Next review: '+esc(formatDate(task.snooze_until))+'</span>':'')+'</div>'+
        update+
      '</div></article>';
  }).join('');
  document.querySelector('#actionResults').innerHTML=
    '<div class="action-record-list">'+
      (cards||'<div class="card action-empty">No actions match these filters.</div>')+
    '</div><p class="fine-print">Saving progress records who made the update. It does not automatically change an agreement or renewal date.</p>';

  document.querySelectorAll('[data-start-quote]').forEach(button=>{
    button.addEventListener('click',()=>{
      window.unifiedSourceFromAction={
        contract_id:Number(button.dataset.startQuote),
        site_label:button.dataset.quoteSite
      };
      setView('quoting');
    });
  });
  const begin=data.total?data.offset+1:0,end=data.offset+items.length;
  document.querySelector('#actionPager').innerHTML=
    '<span>'+(data.total?esc(begin)+'–'+esc(end)+' of '+esc(data.total):'No actions')+
    '</span><div class="pager"><button id="actionsPrevious"'+
    (!data.offset?' disabled':'')+'>Previous</button><button id="actionsNext"'+
    (end>=data.total?' disabled':'')+'>Next</button></div>';
  document.querySelector('#actionsPrevious').onclick=()=>{
    actionFilter.offset=Math.max(0,actionFilter.offset-actionFilter.limit);
    loadActionCentre().catch(e=>toast(e.message));
  };
  document.querySelector('#actionsNext').onclick=()=>{
    actionFilter.offset+=actionFilter.limit;loadActionCentre().catch(e=>toast(e.message));
  };
  if(!actionUserCanWrite)return;
  document.querySelectorAll('[data-save-task]').forEach(button=>{
    button.addEventListener('click',async()=>{
      const holder=button.closest('.action-update');
      const status=holder.querySelector('[data-field=status]').value;
      const note=holder.querySelector('[data-field=note]').value;
      const snooze=holder.querySelector('[data-field=snooze]').value;
      button.disabled=true;
      try{
        await api('/api/action-centre/'+encodeURIComponent(button.dataset.saveTask)+'/status',{
          method:'POST',headers:{'Content-Type':'application/json'},
          body:JSON.stringify({status,note,snooze_until:snooze||null})
        });
        toast('Action updated');
        await loadActionCentre();
      }catch(error){toast('Update not saved: '+error.message);button.disabled=false;}
    });
  });
}
