'use strict';
const items = document.querySelector('#line-items');
if (items) {
  const count = document.querySelector('#id_lines-TOTAL_FORMS');
  document.querySelector('#add-line').addEventListener('click', () => {
    if (Number(count.value) >= 50) { window.alert('A document can have up to 50 line items.'); return; }
    const html = document.querySelector('#line-template').innerHTML.replaceAll('__prefix__', count.value);
    items.insertAdjacentHTML('beforeend', html);
    count.value = Number(count.value) + 1;
    const last = items.lastElementChild;
    last.querySelector('[name$="-description"]').focus();
    calculate();
  });
  function calculate() {
    let subtotal = 0, tax = 0;
    items.querySelectorAll('.line-row').forEach(row => {
      if (row.querySelector('[name$="-DELETE"]').checked) return;
      const qty = Number(row.querySelector('[name$="-quantity"]').value) || 0;
      const price = Number(row.querySelector('[name$="-unit_price"]').value) || 0;
      const rate = Number(row.querySelector('[name$="-tax_rate"]').value) || 0;
      const cents = Math.round(qty * price * 100);
      subtotal += cents;
      tax += Math.round(cents * rate / 100);
    });
    const display = cents => 'M ' + (cents / 100).toLocaleString('en-LS', {minimumFractionDigits:2, maximumFractionDigits:2});
    document.querySelector('#subtotal').textContent = display(subtotal);
    document.querySelector('#tax-total').textContent = display(tax);
    document.querySelector('#grand-total').textContent = display(subtotal + tax);
  }
  items.addEventListener('input', calculate);
  calculate();
}
