/* Coordinator-first settings menu. Permissions remain enforced by the API. */
(function(){
  let isAdministrator=false;
  const $menu=id=>document.getElementById(id);
  function setMenuOpen(open){
    const panel=$menu('pulseSettingsMenu'),toggle=$menu('pulseSettingsToggle');
    if(!panel||!toggle)return;
    panel.hidden=!open;
    toggle.setAttribute('aria-expanded',String(open));
  }
  function setAdvanced(open){
    document.body.classList.toggle('pulse-advanced-settings',Boolean(isAdministrator&&open));
    window.pulseAdvancedSettings=Boolean(isAdministrator&&open);
    const button=$menu('pulseMenuAdvanced');
    if(button)button.textContent=open?'Hide technical settings':'Pricing & agreement settings';
  }
  window.initPulseSettings=function(session){
    const isPilot=Boolean(session?.pilot);
    isAdministrator=isPilot&&session.role==='Admin';
    const menu=$menu('pulseSettingsMenu'),toggle=$menu('pulseSettingsToggle');
    if(!menu||!toggle)return;
    setAdvanced(false);
    menu.querySelectorAll('[data-admin-menu]').forEach(item=>item.hidden=!isAdministrator);
    $menu('pulseSettingsIdentity').textContent=isPilot?
      'Signed in: '+String(session.user||'Staff')+' · '+String(session.role||''):
      'Local workspace';
    $menu('pulseMenuSignOut').hidden=!isPilot;
    toggle.addEventListener('click',event=>{
      event.stopPropagation();
      setMenuOpen(menu.hidden);
    });
    document.addEventListener('pointerdown',event=>{
      if(!event.target.closest('.portal-settings'))setMenuOpen(false);
    });
    document.addEventListener('keydown',event=>{
      if(event.key==='Escape'&&!menu.hidden){setMenuOpen(false);toggle.focus();}
    });
    const selected=(id,handler)=>{
      $menu(id).addEventListener('click',async()=>{
        setMenuOpen(false);
        try{await handler();}catch(error){toast(error.message);}
      });
    };
    selected('pulseMenuExport',()=>downloadExcel());
    selected('pulseMenuAdvanced',()=>{
      if(!isAdministrator)return;
      const next=!Boolean(window.pulseAdvancedSettings);
      setAdvanced(next);
      if(next && view!=='quoting')setView('quoting');
      if(next && view==='quoting'){
        const panel=$menu('quoteGoLiveStatusPanel');
        if(panel)panel.scrollIntoView({behavior:'smooth',block:'start'});
      }
    });
    selected('pulseMenuSourceAudit',()=>{if(isAdministrator)setView('source_audit');});
    selected('pulseMenuMasterSources',()=>{if(isAdministrator)setView('master_sources');});
    selected('pulseMenuSignOut',async()=>{
      await api('/api/pilot/logout',{method:'POST'});
      location.assign('/pilot/login');
    });
  };
})();
