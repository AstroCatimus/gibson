/**
 * Gibson Customer Search View.
 * Public search by title, author, ISBN. Results never include cost basis.
 */

Gibson.router.register('customer-search', function(container) {
  container.innerHTML = `
    <div class="card">
      <h3 style="margin-bottom: 8px;">Search</h3>
      <div style="display: flex; gap: 8px;">
        <input id="cust-search" type="text" placeholder="Title, author, or ISBN..."
          style="flex:1; padding: 10px; background: var(--bg-secondary); border: 1px solid var(--border);
                 border-radius: var(--radius); color: var(--text-primary); font-size: 14px;">
        <button id="cust-search-btn" class="btn btn-primary">Search</button>
      </div>
    </div>
    <div id="cust-results"></div>
  `;

  async function doSearch() {
    const query = document.getElementById('cust-search').value.trim();
    if (!query) return;

    const el = document.getElementById('cust-results');
    el.innerHTML = '<div class="spinner" style="margin: 20px auto;"></div>';

    try {
      const items = await Gibson.api.get('/customer/browse?q=' + encodeURIComponent(query));

      if (!items.length) {
        el.innerHTML = `
          <div class="card" style="text-align:center;padding:20px;">
            <p style="color:var(--text-muted);">No results found</p>
            <p style="font-size:12px;color:var(--text-muted);margin-top:8px;">
              Want us to look for this? <button class="btn btn-secondary" style="font-size:12px;"
                onclick="Gibson.router.navigate('customer-wantlist', {query: '${query.replace(/'/g, "\\'")}'})"
              >Add to Want List</button>
            </p>
          </div>
        `;
        return;
      }

      el.innerHTML = items.map(item => `
        <div class="card">
          <div style="display:flex;justify-content:space-between;">
            <div>
              <p style="font-weight:600;font-size:14px;">${item.title || 'Untitled'}</p>
              <p style="font-size:12px;color:var(--text-secondary);">${item.author || ''}</p>
            </div>
            <div style="text-align:right;">
              <span class="price-tag">$${(item.asking_price || 0).toFixed(2)}</span>
              <p style="font-size:10px;color:var(--text-muted);">${item.condition_grade || ''}</p>
            </div>
          </div>
          <div style="font-size:11px;color:var(--text-muted);margin-top:6px;">
            ${item.section || ''} · ${item.store_name || ''}
          </div>
        </div>
      `).join('');
    } catch (e) {
      el.innerHTML = `<p style="color:var(--red);">Error: ${e.message}</p>`;
    }
  }

  document.getElementById('cust-search-btn').addEventListener('click', doSearch);
  document.getElementById('cust-search').addEventListener('keypress', (e) => {
    if (e.key === 'Enter') doSearch();
  });
});
