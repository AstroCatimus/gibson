/**
 * Gibson Pricing View.
 * Displays labeled pricing: SOLD / ASKING / TREND / AI ESTIMATE.
 * Vialibri is the gate. Dealer price is always final.
 */

Gibson.router.register('pricing', function(container, params) {
  const p = params.pricing || Gibson.store.get('lastPricing') || {};

  function renderComps(comps, title) {
    if (!comps || comps.length === 0) return '';
    return `
      <div style="margin-bottom: 12px;">
        <p style="font-size: 11px; color: var(--text-muted); margin-bottom: 4px;">${title}</p>
        ${comps.map(c => `
          <div style="display: flex; justify-content: space-between; padding: 4px 0; border-bottom: 1px solid var(--border);">
            <span style="font-size: 13px;">
              <span style="background: ${c.label === 'SOLD' ? '#065f46' : c.label === 'ASKING' ? '#78350f' : '#1e3a5f'};
                     padding: 1px 5px; border-radius: 3px; font-size: 9px; font-weight: 700;">${c.label}</span>
              ${c.condition ? `<span style="color: var(--text-muted); font-size: 11px;"> ${c.condition}</span>` : ''}
            </span>
            <span style="font-family: var(--mono); font-weight: 600;">$${c.amount.toFixed(2)}</span>
          </div>
        `).join('')}
      </div>
    `;
  }

  container.innerHTML = `
    <div class="card">
      <h3 style="margin-bottom: 12px;">Pricing</h3>
      ${renderComps(p.gibson_pos, 'Gibson POS (Our Sales) — Highest Weight')}
      ${renderComps(p.ebay_sold, 'eBay Sold — Realized')}
      ${renderComps(p.vialibri, 'Vialibri — Asking (GATE)')}
      ${renderComps(p.ebay_active, 'eBay Active — Asking')}
      ${renderComps(p.booksrun, 'BooksRun — Low Weight')}
      ${renderComps(p.bookscouter, 'BookScouter — Trend')}
      ${p.ai_estimate ? `
        <div style="padding: 8px; background: #7f1d1d; border-radius: var(--radius); margin-top: 8px;">
          <p style="font-size: 11px; font-weight: 700; color: var(--red);">⚠ AI ESTIMATE — NO MARKET DATA</p>
          <p style="font-family: var(--mono);">$${p.ai_estimate.amount.toFixed(2)}</p>
        </div>
      ` : ''}
    </div>

    ${!p.vialibri_has_comps ? `
      <div class="card" style="border-color: var(--yellow);">
        <p style="color: var(--yellow); font-weight: 600;">No Vialibri comps</p>
        <p style="font-size: 13px; color: var(--text-secondary); margin-top: 4px;">
          Nothing found on Vialibri. Price and keep in-store, or queue for pricing research?
        </p>
        <div style="display: flex; gap: 8px; margin-top: 12px;">
          <button class="btn btn-secondary" style="flex:1;">In-Store Only</button>
          <button class="btn btn-primary" style="flex:1;">Queue Research</button>
        </div>
      </div>
    ` : ''}

    <div class="card">
      <p class="price-label">Your Price</p>
      <div style="display: flex; gap: 8px; align-items: center;">
        <span style="font-size: 20px; color: var(--text-muted);">$</span>
        <input id="dealer-price" type="number" step="0.01"
          value="${p.suggested_price || ''}"
          style="flex:1; font-size: 24px; font-weight: 700; font-family: var(--mono);
                 background: var(--bg-secondary); border: 1px solid var(--border);
                 border-radius: var(--radius); color: var(--green); padding: 8px;">
      </div>
    </div>
  `;
});
