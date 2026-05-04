/**
 * Gibson Research / Dashboard view.
 * Correction queue, research queue, overnight results, want list intelligence.
 */

Gibson.router.register('research', function(container) {
  container.innerHTML = `
    <div id="dash-tabs" style="display: flex; gap: 6px; margin-bottom: 12px;">
      <button class="section-tag dash-tab active" data-tab="corrections" style="background:var(--accent);color:white;">Corrections</button>
      <button class="section-tag dash-tab" data-tab="research">Research Queue</button>
      <button class="section-tag dash-tab" data-tab="ghostbook">Ghost Book</button>
      <button class="section-tag dash-tab" data-tab="visits">Visits</button>
    </div>
    <div id="dash-content"></div>
  `;

  container.querySelectorAll('.dash-tab').forEach(btn => {
    btn.addEventListener('click', () => {
      container.querySelectorAll('.dash-tab').forEach(b => { b.style.background = ''; b.style.color = ''; });
      btn.style.background = 'var(--accent)'; btn.style.color = 'white';
      loadTab(btn.dataset.tab);
    });
  });

  async function loadTab(tab) {
    const el = document.getElementById('dash-content');
    el.innerHTML = '<div class="spinner" style="margin: 40px auto;"></div>';

    try {
      if (tab === 'corrections') {
        el.innerHTML = `
          <div class="card">
            <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
              <h3>Correction Queue</h3>
              <button class="btn btn-secondary" style="font-size:12px;">Batch Approve LOW</button>
            </div>
            <p style="color:var(--text-muted);font-size:13px;">
              Review corrections sorted by concern level. HIGH first.
            </p>
            <div style="margin-top:12px;color:var(--text-secondary);text-align:center;padding:20px;">
              No corrections pending review
            </div>
          </div>
        `;
      } else if (tab === 'research') {
        const items = await Gibson.api.get('/research/queue');
        el.innerHTML = `
          <div class="card">
            <h3 style="margin-bottom:12px;">Overnight Research Queue</h3>
            ${items.length ? items.map(i => `
              <div style="padding:8px 0;border-bottom:1px solid var(--border);">
                <p>${i.title || 'Unidentified'} — ${i.author || ''}</p>
                <p style="font-size:11px;color:var(--text-muted);">${i.gibson_sku || ''} · ${i.status}</p>
              </div>
            `).join('') : '<p style="color:var(--text-muted);text-align:center;padding:20px;">Queue empty</p>'}
          </div>
        `;
      } else if (tab === 'ghostbook') {
        const items = await Gibson.api.get('/ghostbook/queue');
        el.innerHTML = `
          <div class="card">
            <h3 style="margin-bottom:12px;">Ghost Book Pipeline</h3>
            <p style="font-size:12px;color:var(--text-muted);margin-bottom:12px;">
              Pre-ISBN, no-institutional-record material
            </p>
            ${items.length ? items.map(i => `
              <div style="padding:8px 0;border-bottom:1px solid var(--border);">
                <p>${i.physical_description || 'No description'}</p>
                <p style="font-size:11px;color:var(--text-muted);">${i.research_status} · ${i.sources_searched?.length || 0} sources checked</p>
              </div>
            `).join('') : '<p style="color:var(--text-muted);text-align:center;padding:20px;">No Ghost Book records</p>'}
          </div>
        `;
      } else if (tab === 'visits') {
        el.innerHTML = `
          <div class="card">
            <h3 style="margin-bottom:12px;">Upcoming Visits</h3>
            <p style="color:var(--text-muted);text-align:center;padding:20px;">No visits scheduled</p>
          </div>
        `;
      }
    } catch (e) {
      el.innerHTML = `<div class="card"><p style="color:var(--red);">Error: ${e.message}</p></div>`;
    }
  }

  loadTab('corrections');
});

// Also register dashboard view pointing to same
Gibson.router.register('dashboard', function(container) {
  Gibson.router.views['research'](container);
});
