(() => {
  if (!('serviceWorker' in navigator) || !window.isSecureContext) return;
  navigator.serviceWorker.register('/sw.js', {scope: '/', updateViaCache: 'none'}).catch(() => {});
  const standalone = window.matchMedia('(display-mode: standalone)');
  if (standalone.matches || navigator.standalone) return;
  let deferred;
  const panel = document.createElement('div');
  panel.className = 'pwa-install';
  const button = document.createElement('button');
  button.type = 'button'; button.textContent = 'Install app';
  panel.append(button); document.body.append(panel);
  const dialog = document.createElement('dialog');
  dialog.className = 'pwa-dialog';
  const title = document.createElement('h2'); title.textContent = 'Keep 4Tax close'; title.id = 'pwa-install-title';
  dialog.setAttribute('aria-labelledby', title.id);
  const help = document.createElement('p');
  help.textContent = /iPhone|iPad|iPod/.test(navigator.userAgent) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1)
    ? 'Open your browser’s Share menu, choose Add to Home Screen, then Add.'
    : 'Use Install app in your browser menu or address bar. In Safari on Mac, choose File → Add to Dock. If your browser does not offer installation, open this page in Chrome or Edge.';
  const note = document.createElement('p'); note.textContent = 'An internet connection is required to work with your records.';
  const close = document.createElement('button'); close.type = 'button'; close.textContent = 'Got it';
  close.addEventListener('click', () => dialog.close());
  dialog.append(title, help, note, close); document.body.append(dialog);
  window.addEventListener('beforeinstallprompt', event => {event.preventDefault(); deferred = event;});
  button.addEventListener('click', async () => {
    if (!deferred) {dialog.showModal(); return;}
    const prompt = deferred; deferred = null;
    try {
      await prompt.prompt();
      if ((await prompt.userChoice).outcome === 'accepted') panel.remove();
    } catch (_) {dialog.showModal();}
  });
  const installed = () => {panel.remove(); dialog.close(); dialog.remove();};
  window.addEventListener('appinstalled', installed);
  standalone.addEventListener('change', event => {if (event.matches) installed();});
})();
