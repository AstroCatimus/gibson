/**
 * Gibson Customer Browse View.
 * Public-facing browse by section. No cost basis, no internal data.
 */

Gibson.router.register('customer-browse', function(container) {
  container.innerHTML = `
    <div class="card">
      <h3 style="margin-bottom: 8px;">Browse Inventory</h3>
      <p style="font-size: 12px; color: var(--text-muted); margin-bottom: 12px;">
        Browse available books by section
      </p>
      <div id="browse-sections" style="display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 16px;"></div>
    </div>
    <div id="browse-results"></div>
  `;

  // Load sections
  Gibson.api.get('/customer/sections').then(sections => {
    const el = document.getElementById('browse-sections');
    el.innerHTML = sections.map(s => `
      <button class="section-tag browse-section" data-section="${s.code}"
        style="cursor:pointer;">${s.name} <span style="font-size:10px;color:var(--text-muted);">(${s.count})</span></button>
    `).join('');

    el.querySelectorAll('.browse-section').forEach(btn => {
      btn.addEventListener('click', () => loadSection(btn.dataset.section));
    });
  }).catch(() => {});

  async function loadSection(section) {
    const el = document.getElementById('browse-results');
    el.innerHTML = '<div class="spinner" style="margin: 20px auto;"></div>';

    try {
      const items = await Gibson.api.get('/customer/browse?section=' + encodeURIComponent(section));
      if (!items.length) {
        el.innerHTML = '<p style="text-align:center;color:var(--text-muted);padding:20px;">No items in this section</p>';
        return;
      }

      el.innerHTML = items.map(item => `
        <div class="card">
          <div style="display:flex;justify-content:space-between;">
            <div>
              <p style="font-weight:600;font-size:14px;">${item.title || 'Untitled'}</p>
              <p style="font-size:12px;color:var(--text-secondary);">${item.author || ''}</p>
              ${item.publisher ? `<p style="font-size:11px;color:var(--text-muted);">${item.publisher}, ${item.year || ''}</p>` : ''}
            </div>
            <div style="text-align:right;">
              <span class="price-tag" style="font-size:16px;">$${(item.asking_price || 0).toFixed(2)}</span>
              <p style="font-size:10px;color:var(--text-muted);">${item.condition_grade || ''}</p>
            </div>
          </div>
          <div style="font-size:11px;color:var(--text-muted);margin-top:6px;">
            ${item.isbn_13 || ''} · ${item.section || ''}
          </div>
        </div>
      `).join('');
    } catch (e) {
      el.innerHTML = `<p style="color:var(--red);">Error: ${e.message}</p>`;
    }
  }
});
