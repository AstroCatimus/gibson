/**
 * Gibson Whatnot Show View.
 * Batch prep for Whatnot live sales. Identify pile → generate descriptions →
 * suggest sequence → export for upload. Show-by-show management.
 */

Gibson.router.register('whatnot', function(container) {
  container.innerHTML = `
    <div id="whatnot-tabs" style="display: flex; gap: 6px; margin-bottom: 12px;">
      <button class="section-tag wn-tab active" data-tab="prep" style="background:var(--accent);color:white;">Batch Prep</button>
      <button class="section-tag wn-tab" data-tab="shows">Shows</button>
      <button class="section-tag wn-tab" data-tab="export">Export</button>
    </div>
    <div id="whatnot-content"></div>
  `;

  container.querySelectorAll('.wn-tab').forEach(btn => {
    btn.addEventListener('click', () => {
      container.querySelectorAll('.wn-tab').forEach(b => { b.style.background = ''; b.style.color = ''; });
      btn.style.background = 'var(--accent)'; btn.style.color = 'white';
      loadTab(btn.dataset.tab);
    });
  });

  function loadTab(tab) {
    const el = document.getElementById('whatnot-content');

    if (tab === 'prep') {
      el.innerHTML = `
        <div class="card">
          <h3 style="margin-bottom: 12px;">Batch Preparation</h3>
          <p style="font-size: 12px; color: var(--text-muted); margin-bottom: 12px;">
            Photograph a pile of books for Whatnot. Gibson identifies,
            prices, and generates descriptions for each.
          </p>

          <div style="margin-bottom: 12px;">
            <label style="font-size: 11px; color: var(--text-muted);">Show Name</label>
            <input id="wn-show-name" placeholder="Saturday Night Books #12"
              style="width:100%; padding: 8px; background: var(--bg-secondary); border: 1px solid var(--border);
                     border-radius: var(--radius); color: var(--text-primary); font-size: 14px;">
          </div>

          <div style="margin-bottom: 12px;">
            <label style="font-size: 11px; color: var(--text-muted);">Starting Price</label>
            <input id="wn-start-price" type="number" value="1" step="1" min="1"
              style="width:100%; padding: 8px; background: var(--bg-secondary); border: 1px solid var(--border);
                     border-radius: var(--radius); color: var(--text-primary); font-size: 14px; font-family: var(--mono);">
          </div>

          <button id="wn-batch-start" class="btn btn-primary btn-full">
            Start Batch — Scan Books
          </button>
        </div>

        <div id="wn-batch-items"></div>
      `;

      document.getElementById('wn-batch-start').addEventListener('click', () => {
        Gibson.router.navigate('camera', { returnTo: 'whatnot', mode: 'batch' });
      });

    } else if (tab === 'shows') {
      el.innerHTML = `
        <div class="card">
          <h3 style="margin-bottom: 12px;">Scheduled Shows</h3>
          <div id="wn-shows-list">
            <div class="spinner" style="margin: 20px auto;"></div>
          </div>
        </div>
      `;

      // Load shows (placeholder)
      setTimeout(() => {
        document.getElementById('wn-shows-list').innerHTML = `
          <p style="color:var(--text-muted);text-align:center;padding:20px;">No shows scheduled</p>
        `;
      }, 500);

    } else if (tab === 'export') {
      el.innerHTML = `
        <div class="card">
          <h3 style="margin-bottom: 12px;">Export for Whatnot</h3>
          <p style="font-size: 12px; color: var(--text-muted); margin-bottom: 12px;">
            Generate a CSV upload file with titles, descriptions, photos, and starting prices.
          </p>

          <div style="margin-bottom: 12px;">
            <label style="font-size: 11px; color: var(--text-muted);">Select Show</label>
            <select id="wn-export-show"
              style="width:100%; padding: 8px; background: var(--bg-secondary); border: 1px solid var(--border);
                     border-radius: var(--radius); color: var(--text-primary); font-size: 14px;">
              <option value="">No shows available</option>
            </select>
          </div>

          <button id="wn-export-btn" class="btn btn-primary btn-full">
            Generate Export CSV
          </button>

          <button id="wn-descriptions-btn" class="btn btn-secondary btn-full" style="margin-top: 8px;">
            Generate AI Descriptions
          </button>
        </div>
      `;

      document.getElementById('wn-descriptions-btn')?.addEventListener('click', async () => {
        const btn = document.getElementById('wn-descriptions-btn');
        btn.disabled = true;
        btn.textContent = 'Generating...';
        try {
          await Gibson.api.post('/whatnot/generate-descriptions', {
            show_id: document.getElementById('wn-export-show').value
          });
          btn.textContent = 'Descriptions Generated!';
        } catch (e) {
          btn.disabled = false;
          btn.textContent = 'Generate AI Descriptions';
          alert('Error: ' + e.message);
        }
      });

      document.getElementById('wn-export-btn')?.addEventListener('click', async () => {
        try {
          const blob = await Gibson.api.post('/whatnot/export', {
            show_id: document.getElementById('wn-export-show').value
          });
          alert('Export CSV generated. Download will begin shortly.');
        } catch (e) {
          alert('Export error: ' + e.message);
        }
      });
    }
  }

  loadTab('prep');
});
