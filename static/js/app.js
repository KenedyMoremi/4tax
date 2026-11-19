'use strict';
const toggle = document.querySelector('#menu-toggle');
const sidebar = document.querySelector('#sidebar');
const overlay = document.querySelector('#nav-overlay');
function closeMenu() { sidebar?.classList.remove('open'); overlay?.classList.add('hidden'); toggle?.setAttribute('aria-expanded', 'false'); }
toggle?.addEventListener('click', () => { const open = sidebar.classList.toggle('open'); overlay.classList.toggle('hidden', !open); toggle.setAttribute('aria-expanded', String(open)); });
overlay?.addEventListener('click', closeMenu);
document.addEventListener('keydown', event => { if (event.key === 'Escape') closeMenu(); });
document.querySelectorAll('[data-confirm]').forEach(form => form.addEventListener('submit', event => { if (!window.confirm(form.dataset.confirm)) event.preventDefault(); }));
document.querySelectorAll('[data-print]').forEach(button => button.addEventListener('click', () => window.print()));
