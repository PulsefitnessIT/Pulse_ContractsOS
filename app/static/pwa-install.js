/* PWA installation helpers – no account, customer or contract information stored locally. */
(() => {
  'use strict';
  let deferredPrompt = null;
  const btn = document.getElementById('installPulseApp');
  const installed = () => window.matchMedia('(display-mode: standalone)').matches || window.navigator.standalone === true;
  const sync = () => { if (btn) btn.hidden = installed(); };
  if ('serviceWorker' in navigator && window.isSecureContext) {
    window.addEventListener('load', () => {
      navigator.serviceWorker.register('/sw.js', { scope: '/' }).catch(err => {
        console.warn('Desktop installation is not available:', err);
      });
    });
  }
  window.addEventListener('beforeinstallprompt', event => {
    event.preventDefault();
    deferredPrompt = event;
    if (btn) { btn.hidden = false; btn.textContent = 'Install desktop app'; }
  });
  window.addEventListener('appinstalled', () => { deferredPrompt = null; sync(); });
  if (btn) {
    btn.addEventListener('click', async () => {
      if (deferredPrompt) {
        const prompt = deferredPrompt;
        deferredPrompt = null;
        await prompt.prompt();
        await prompt.userChoice;
        sync();
        return;
      }
      window.alert('To install Contracts OS: open this site in Microsoft Edge or Google Chrome over HTTPS. Select the browser menu (⋯) → Apps → Install this site as an app, or choose Install from the address bar.');
    });
    sync();
  }
})();
