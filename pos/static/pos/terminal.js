(() => {
  const app = document.querySelector('#pos-app');
  if (!app) return;
  const form = document.querySelector('#pos-checkout');
  const key = `4tax-pos-cart-${app.dataset.business}`;
  const products = new Map(JSON.parse(document.querySelector('#pos-products').textContent).map(p => [String(p.id), p]));
  const token = form.querySelector('[name=token]');
  const tendered = form.querySelector('[name=tendered]');
  let cart = [], editedPayment = !!tendered.value;
  try {
    const saved = JSON.parse(sessionStorage.getItem(key) || 'null');
    if (saved && Array.isArray(saved.items) && saved.items.length <= 50) {
      cart = saved.items.filter(item => item && Number.isSafeInteger(item.id) && Number.isSafeInteger(item.version) && ['name', 'price', 'tax', 'unit', 'quantity'].every(field => typeof item[field] === 'string'));
      if (app.dataset.posted !== 'true' && saved.token) token.value = saved.token;
    }
  } catch (_) { /* Storage is optional; server-side retry protection remains in effect. */ }
  if (app.dataset.posted === 'true') cart = JSON.parse(document.querySelector('#pos-initial-cart').textContent);
  const fixed = value => {
    const match = /^(\d{1,12})(?:\.(\d{1,2}))?$/.exec(String(value));
    return match ? BigInt(match[1]) * 100n + BigInt((match[2] || '').padEnd(2, '0')) : null;
  };
  const money = cents => `${cents / 100n}.${String(cents % 100n).padStart(2, '0')}`;
  const round = (number, denominator) => (number + denominator / 2n) / denominator;
  const store = () => { try { sessionStorage.setItem(key, JSON.stringify({token: token.value, items: cart})); } catch (_) {} };
  function totals() {
    let subtotal = 0n, tax = 0n, valid = cart.length > 0;
    cart.forEach(item => {
      const quantity = fixed(item.quantity), price = fixed(item.price), rate = fixed(item.tax);
      if (quantity === null || quantity <= 0n || price === null || rate === null) { valid = false; return; }
      const base = round(quantity * price, 100n);
      subtotal += base; tax += round(base * rate, 10000n);
    });
    const total = subtotal + tax;
    document.querySelector('#subtotal').textContent = `M ${money(subtotal)}`;
    document.querySelector('#tax').textContent = `M ${money(tax)}`;
    document.querySelector('#total').textContent = `M ${money(total)}`;
    if (!editedPayment) tendered.value = total ? money(total) : '';
    const paid = fixed(tendered.value);
    document.querySelector('#change').textContent = `M ${money(paid !== null && paid >= total ? paid - total : 0n)}`;
    document.querySelector('#complete-sale').disabled = !valid || total <= 0n;
    store();
  }
  function render() {
    const basket = document.querySelector('#basket'); basket.replaceChildren();
    form.querySelector('[name="items-TOTAL_FORMS"]').value = cart.length;
    document.querySelector('#basket-message').hidden = cart.length > 0;
    cart.forEach((item, index) => {
      const row = document.createElement('div'); row.className = 'rounded-lg border border-gray-200 p-3';
      const title = document.createElement('p'); title.className = 'font-semibold text-sm'; title.textContent = item.name; row.append(title);
      const detail = document.createElement('p'); detail.className = 'mt-1 text-xs text-gray-500'; detail.textContent = `M ${item.price} / ${item.unit} · VAT ${item.tax}%`; row.append(detail);
      for (const [name, value] of [['product', item.id], ['version', item.version]]) {
        const input = document.createElement('input'); input.type = 'hidden'; input.name = `items-${index}-${name}`; input.value = value; row.append(input);
      }
      const controls = document.createElement('div'); controls.className = 'mt-3 flex items-center gap-3';
      const label = document.createElement('label'); label.className = 'text-xs text-gray-500'; label.textContent = 'Quantity'; label.htmlFor = `cart-quantity-${index}`;
      const quantity = document.createElement('input'); quantity.type = 'number'; quantity.min = '0.01'; quantity.max = '9999999.99'; quantity.step = '0.01'; quantity.required = true; quantity.className = 'w-24'; quantity.id = label.htmlFor; quantity.name = `items-${index}-quantity`; quantity.value = item.quantity;
      quantity.addEventListener('input', () => { item.quantity = quantity.value; totals(); });
      const remove = document.createElement('button'); remove.type = 'button'; remove.className = 'ml-auto text-xs text-gray-500 underline'; remove.textContent = 'Remove'; remove.setAttribute('aria-label', `Remove ${item.name}`);
      remove.addEventListener('click', () => { cart.splice(index, 1); render(); });
      controls.append(label, quantity, remove); row.append(controls); basket.append(row);
    });
    totals();
  }
  document.querySelectorAll('[data-add-product]').forEach(button => button.addEventListener('click', () => {
    const product = products.get(button.dataset.addProduct);
    const existing = cart.find(item => String(item.id) === String(product.id));
    if (existing) existing.quantity = money((fixed(existing.quantity) || 0n) + 100n);
    else if (cart.length < 50) cart.push({...product, quantity: '1.00'});
    else { document.querySelector('#basket-message').hidden = false; document.querySelector('#basket-message').textContent = 'A sale can contain up to 50 different items.'; return; }
    render();
  }));
  tendered.addEventListener('input', () => { editedPayment = true; totals(); });
  document.querySelector('#clear-cart').addEventListener('click', () => { cart = []; editedPayment = false; render(); });
  form.addEventListener('submit', () => { store(); const button = document.querySelector('#complete-sale'); button.disabled = true; button.textContent = 'Recording sale…'; });
  render();
})();
