(() => {
  const form = document.querySelector('#stock-sale');
  if (!form) return;
  const tendered = form.querySelector('[name=tendered]');
  let edited = !!tendered.value;
  const fixed = value => {
    const match = /^(\d{1,10})(?:\.(\d{1,2}))?$/.exec(String(value));
    return match ? BigInt(match[1]) * 100n + BigInt((match[2] || '').padEnd(2, '0')) : null;
  };
  const money = cents => `${cents / 100n}.${String(cents % 100n).padStart(2, '0')}`;
  function update() {
    let total = 0n, valid = true, count = 0;
    form.querySelectorAll('[data-stock-row]').forEach(row => {
      if (!row.querySelector('[name$="-selected"]')?.checked) return;
      count++;
      const quantity = fixed(row.querySelector('[name$="-quantity"]').value);
      const price = fixed(row.querySelector('[name$="-selling_price"]').value);
      const rate = fixed(row.dataset.tax);
      if (quantity === null || price === null || rate === null || quantity <= 0n || price <= 0n) {valid = false; return;}
      const base = (quantity * price + 50n) / 100n;
      total += base + (base * rate + 5000n) / 10000n;
    });
    document.querySelector('#stock-total').textContent = count && valid ? `Total including VAT: M ${money(total)}` : 'Tick items and enter quantities and selling prices';
    if (!edited) tendered.value = count && valid ? money(total) : '';
  }
  tendered.addEventListener('input', () => {edited = true;});
  form.addEventListener('input', update);
  form.addEventListener('submit', () => {
    const button = form.querySelector('button[type=submit]');
    button.disabled = true;
    button.textContent = 'Recording sale…';
  });
  window.addEventListener('pageshow', () => {const button = form.querySelector('button[type=submit]'); button.disabled = false; button.textContent = 'Record sale & reduce stock';});
  update();
})();
