/**
 * Gibson Inventory View.
 * Search by title, author, ISBN, SKU. Filter by status and section.
 * Every query includes store_id. Cost basis never shown in shared views.
 */

Gibson.router.register('inventory', function(container) {
  container.innerHTML = `
    <div style="display: flex; gap: 8px; margin-bottom: 12px;">
      <input id="inv-search" type="text" placeholder="Search title, author, ISBN, SKU..."
        style="flex:1; padding: 10px; background: var(--bg-secondary); border: 1px solid var(--border);
               border-radius: var(--radius); color: var(--text-primary); font-size: 14px;">
      <button id="inv-search-btn" class="btn btn-primary">Search</button>
    </div>

    <div id="inv-stats" class="card" style="display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; text-align: center;">
      <div><span style="font-size: 20px; font-weight: 700; font-family: var(--mono);" id="stat-total">—</span><br><span style="font-size: 10px; color: var(--text-muted);">Total</span></div>
      <div><span style="font-size: 20px; font-weight: 700; font-family: var(--mono); color: var(--green);" id="stat-available">—</span><br><span style="font-size: 10px; color: var(--text-muted);">Available</span></div>
      <div><span style="font-size: 20px; font-weight: 700; font-family: var(--mono); color: var(--yellow);" id="stat-pending">—</span><br><span style="font-size: 10px; color: var(--text-muted);">Pending</span></div>
      <div><span style="font-size: 20px; font-weight: 700; font-family: var(--mono);" id="stat-value">—</span><br><span style="font-size: 10px; color: var(--text-muted);">Value</span></div>
    </div>

    <div id="inv-filters" style="display: flex; gap: 6px; margin-bottom: 12px; flex-wrap: wrap;">
      ${['All', 'AVAILABLE', 'LISTED', 'PENDING_IDENTIFICATION', 'GHOST_BOOK_QUEUE'].map(s => `
        <button class="section-tag inv-filter" data-status="${s === 'All' ? '' : s}">${s.replace(/_/g, ' ')}</button>
      `).join('')}
    </div>

    <div id="inv-list"></div>
  `;

  // Load stats
  Gibson.api.inventoryCount().then(stats => {
    document.getElementById('stat-total').textContent = stats.total || 0;
    document.getElementById('stat-available').textContent = stats.available || 0;
    document.getElementById('stat-pending').textContent = (stats.pending_id || 0) + (stats.pending_review || 0);
    document.getElementById('stat-value').textContent = '$' + (stats.total_value || 0).toLocaleString();
  }).catch(() => {});

  // Search
  async function search(query = '', status = '') {
    const listEl = document.getElementById('inv-list');
    listEl.innerHTML = '<div class="spinner" style="margin: 20px auto;"></div>';

    try {
      const params = { limit: 50 };
      if (status) params.status = status;
      const items = await Gibson.api.listInventory(params);

      if (!items.length) {
        listEl.innerHTML = '<p style="text-align:center; color:var(--text-muted); padding: 40px;">No items found</p>';
        return;
      }

      listEl.innerHTML = items.map(item => `
        <div class="card" style="cursor: pointer;" onclick="Gibson.router.navigate('identify', {result: ${JSON.stringify(item).replace(/"/g, '&quot;')}})">
          <div style="display: flex; justify-content: space-between;">
            <div>
              <p style="font-weight: 600; font-size: 14px;">${item.title || 'Untitled'}</p>
              <p style="font-size: 12px; color: var(--text-secondary);">${item.author || ''}</p>
            </div>
            <div style="text-align: right;">
              <span class="price-tag" style="font-size: 16px;">$${(item.asking_price || 0).toFixed(2)}</span>
              <p style="font-size: 10px; color: var(--text-muted);">${item.condition_grade || ''}</p>
            </div>
          </div>
          <div style="display: flex; gap: 8px; margin-top: 8px; font-size: 11px; color: var(--text-muted);">
            <span>${item.gibson_sku || ''}</span>
            <span>${item.section || ''}</span>
            <span>${item.isbn_13 || ''}</span>
            <span style="margin-left: auto;">${item.status}</span>
          </div>
        </div>
      `).join('');
    } catch (e) {
      listEl.innerHTML = `<p style="color: var(--red);">Error: ${e.message}</p>`;
    }
  }

  document.getElementById('inv-search-btn').addEventListener('click', () => {
    search(document.getElementById('inv-search').value);
  });
  document.getElementById('inv-search').addEventListener('keypress', (e) => {
    if (e.key === 'Enter') search(document.getElementById('inv-search').value);
  });

  container.querySelectorAll('.inv-filter').forEach(btn => {
    btn.addEventListener('click', () => {
      container.querySelectorAll('.inv-filter').forEach(b => { b.style.background = ''; b.style.color = ''; });
      btn.style.background = 'var(--accent)'; btn.style.color = 'white';
      search('', btn.dataset.status);
    });
  });

  // Initial load
  search();
});
