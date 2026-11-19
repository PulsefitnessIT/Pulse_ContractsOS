/* Pulse Fitness setup/navigation. Settings is ONE understandable dashboard.
   No jumps to retired V10 or source-register screens. */
(function(){
  const node=id=>document.getElementById(id);
  const menu=node('pulseSettingsMenu');
  const toggle=node('pulseSettingsToggle');
  let initialized=false;
  function openSettingsMenu(open){
    if(!menu||!toggle)return;
    menu.hidden=!open;
    toggle.setAttribute('aria-expanded',String(open));
  }
  window.pulseSetupFirstLogin=false;
  window.updatePulseSettingsStatus=function(status){
    const count=node('pulseMenuSetupCount');
    if(!count||!status)return;
    const missing=Math.max(0,Number(status.required_count||0)-Number(status.ready_count||0));
    count.textContent=missing?' · '+missing+' to check':(status.core_setup_ready?' · Ready':'');
    const btn=node('pulseMenuAdvanced');
    if(btn)btn.title=missing?
      missing+' setup checks still require attention':'View platform settings and approved source status';
  };
  window.initPulseSettings=async function(session){
    const isPilot=Boolean(session?.pilot);
    const isAdmin=isPilot&&session.role==='Admin';
    const identity=node('pulseSettingsIdentity');
    if(identity)identity.textContent=isPilot?
      'Signed in as '+String(session.user||'Staff')+' · '+String(session.role||''):
      'Local workspace';
    if(menu)menu.querySelectorAll('[data-admin-menu]').forEach(item=>item.hidden=!isAdmin);
    node('pulseMenuSignOut').hidden=!isPilot;
    if(!initialized&&menu&&toggle){
      initialized=true;
      toggle.addEventListener('click',event=>{
        event.stopPropagation();
        openSettingsMenu(menu.hidden);
      });
      document.addEventListener('pointerdown',event=>{
        if(!event.target.closest('.portal-settings'))openSettingsMenu(false);
      });
      document.addEventListener('keydown',event=>{
        if(event.key==='Escape'&&!menu.hidden){
          openSettingsMenu(false);toggle.focus();
        }
      });
      node('pulseMenuExport').onclick=()=>{
        openSettingsMenu(false);
        downloadExcel();
      };
      node('pulseMenuAdvanced').onclick=()=>{
        openSettingsMenu(false);
        if(window.pulseAuthRole==='Admin')setView('setup');
      };
      node('pulseMenuSignOut').onclick=async()=>{
        openSettingsMenu(false);
        try{
          await api('/api/pilot/logout',{method:'POST'});
          location.assign('/pilot/login');
        }catch(error){toast('Sign out failed: '+error.message);}
      };
    }
    if(!isAdmin)return;
    try{
      const status=await api('/api/admin/setup/status');
      window.updatePulseSettingsStatus(status);
      if(status.first_login_wizard){
        // Saved on the private device, not in the browser. If the application
        // crashes, setup can always be resumed from Settings.
        await api('/api/admin/setup/progress',{
          method:'POST',headers:{'Content-Type':'application/json'},
          body:JSON.stringify({action:'start'})
        });
        window.pulseSetupFirstLogin=true;
        setView('setup');
      }
    }catch(error){
      // Daily internal work remains accessible; commercial issue is still
      // enforced at the server, regardless of whether this screen loads.
      toast('Setup status unavailable: '+error.message);
    }
  };
})();
