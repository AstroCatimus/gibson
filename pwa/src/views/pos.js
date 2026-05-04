/**
 * Gibson POS / Counter Flow.
 * SKU lookup → price auto-fills. Section code + price for uncatalogued.
 * Section code carries forward across multi-book sale.
 */

Gibson.router.register('pos', function(container) {
  const sale = Gibson.store.get('currentSale');

  container.innerHTML = `
    <div class="card">
      <h3 style="margin-bottom: 12px;">Sale</h3>
      <div style="display: flex; gap: 8px; margin-bottom: 12px;">
        <input id="pos-input" type="text" placeholder='SKU (JS-1213) or section+price (F 5)'
          style="flex:1; padding: 10px; background: var(--bg-secondary); border: 1px solid var(--border);
                 border-radius: var(--radius); color: var(--text-primary); font-size: 16px;"
          autofocus>
        <button id="pos-add" class="btn btn-primary">Add</button>
      </div>
      <div id="pos-items"></div>
    </div>

    <div class="card" id="pos-totals" style="display: none;">
      <div style="display: flex; justify-content: space-between; margin-bottom: 8px;">
        <span style="color: var(--text-secondary);">Subtotal</span>
        <span id="pos-subtotal" style="font-family: var(--mono);">$0.00</span>
      </div>
      <div style="display: flex; justify-content: space-between; margin-bottom: 8px;">
        <span style="color: var(--text-secondary);">Tax (5.5%)</span>
        <span id="pos-tax" style="font-family: var(--mono);">$0.00</span>
      </div>
      <div style="display: flex; justify-content: space-between; font-size: 20px; font-weight: 700;">
        <span>Total</span>
        <span id="pos-total" class="price-tag">$0.00</span>
      </div>
      <div style="display: flex; gap: 8px; margin-top: 16px;">
        <button class="btn btn-primary" style="flex:1;" id="pos-cash">💵 Cash</button>
        <button class="btn btn-secondary" style="flex:1;" id="pos-card">💳 Card</button>
      </div>
    </div>
  `;

  const items = [];

  function renderItems() {
    const el = document.getElementById('pos-items');
    const totalsEl = document.getElementById('pos-totals');

    if (items.length === 0) {
      el.innerHTML = '<p style="color:var(--text-muted); text-align:center; padding:20px;">Scan or type to add items</p>';
      totalsEl.style.display = 'none';
      return;
    }

    el.innerHTML = items.map((item, i) => `
      <div style="display: flex; justify-content: space-between; align-items: center; padding: 8px 0; border-bottom: 1px solid var(--border);">
        <div>
          <p style="font-size: 14px;">${item.title || item.section || 'Item'}</p>
          <p style="font-size: 11px; color: var(--text-muted);">${item.sku || ''}</p>
        </div>
        <div style="display: flex; align-items: center; gap: 12px;">
          <span style="font-family: var(--mono); font-weight: 600;">$${item.price.toFixed(2)}</span>
          <button style="background:none; border:none; color:var(--red); cursor:pointer; font-size: 16px;"
            onclick="document.dispatchEvent(new CustomEvent('pos-remove', {detail:${i}}))">×</button>
        </div>
      </div>
    `).join('');

    const subtotal = items.reduce((s, i) => s + i.price, 0);
    const tax = Math.round(subtotal * 0.055 * 100) / 100;
    document.getElementById('pos-subtotal').textContent = '$' + subtotal.toFixed(2);
    document.getElementById('pos-tax').textContent = '$' + tax.toFixed(2);
    document.getElementById('pos-total').textContent = '$' + (subtotal + tax).toFixed(2);
    totalsEl.style.display = 'block';
  }

  document.addEventListener('pos-remove', (e) => {
    items.splice(e.detail, 1);
    renderItems();
  });

  document.getElementById('pos-add').addEventListener('click', async () => {
    const input = document.getElementById('pos-input').value.trim();
    if (!input) return;

    // Parse input: SKU (JS-1213) or section+price (F 5)
    const skuMatch = input.match(/^([A-Z]{2}-\d+)$/i);
    const sectionMatch = input.match(/^([A-Za-z]+)\s+(\d+\.?\d*)$/);

    if (skuMatch) {
      try {
        const item = await Gibson.api.lookupSku(skuMatch[1]);
        items.push({ sku: item.gibson_sku, title: item.title, price: item.asking_price || 0, stock_item_id: item.stock_item_id });
      } catch (e) {
        alert('SKU not found: ' + skuMatch[1]);
        return;
      }
    } else if (sectionMatch) {
      items.push({ section: sectionMatch[1], price: parseFloat(sectionMatch[2]), title: sectionMatch[1] + ' section' });
    } else {
      alert('Enter SKU (JS-1213) or section+price (F 5)');
      return;
    }

    document.getElementById('pos-input').value = '';
    document.getElementById('pos-input').focus();
    renderItems();
  });

  document.getElementById('pos-input').addEventListener('keypress', (e) => {
    if (e.key === 'Enter') document.getElementById('pos-add').click();
  });

  async function closeSale(method) {
    if (!items.length) return;
    try {
      const result = await Gibson.api.createSale({
        items: items.map(i => ({ stock_item_id: i.stock_item_id, price: i.price, gibson_sku: i.sku })),
        payment_method: method,
      });
      alert(`Sale complete! Total: $${result.total?.toFixed(2) || '0.00'}`);
      items.length = 0;
      renderItems();
    } catch (e) {
      alert('Sale failed: ' + e.message);
    }
  }

  document.getElementById('pos-cash')?.addEventListener('click', () => closeSale('cash'));
  document.getElementById('pos-card')?.addEventListener('click', () => closeSale('card'));

  renderItems();
});
