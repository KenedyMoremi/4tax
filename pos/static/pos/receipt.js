(() => {
  const receipt = document.querySelector('#pos-receipt');
  if (!receipt) return;
  const key = `4tax-pos-cart-${receipt.dataset.business}`;
  try {
    const saved = JSON.parse(sessionStorage.getItem(key) || 'null');
    if (saved?.token === receipt.dataset.token) sessionStorage.removeItem(key);
  } catch (_) {}
  document.querySelector('[data-print-receipt]')?.addEventListener('click', () => window.print());
})();
