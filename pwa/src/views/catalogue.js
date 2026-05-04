/**
 * Gibson Catalogue View — final confirmation before stock item creation.
 * Gibson prompts the logical choice. Dealer is always final.
 * One tap to confirm. Every override is a training signal.
 */

Gibson.router.register('catalogue', function(container, params) {
  const id = params.identification || {};
  const grade = params.conditionGrade || 'Good';
  const price = id.suggested_price || '';

  container.innerHTML = `
    <div class="card">
      <h3 style="margin-bottom: 12px;">Confirm & Catalogue</h3>

      <div style="display: grid; gap: 12px;">
        <div>
          <label style="font-size: 11px; color: var(--text-muted);">Title</label>
          <input id="cat-title" value="${id.title || ''}"
            style="width:100%; padding: 8px; background: var(--bg-secondary); border: 1px solid var(--border);
                   border-radius: var(--radius); color: var(--text-primary); font-size: 14px;">
        </div>
        <div>
          <label style="font-size: 11px; color: var(--text-muted);">Author</label>
          <input id="cat-author" value="${id.author || ''}"
            style="width:100%; padding: 8px; background: var(--bg-secondary); border: 1px solid var(--border);
                   border-radius: var(--radius); color: var(--text-primary); font-size: 14px;">
        </div>
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px;">
          <div>
            <label style="font-size: 11px; color: var(--text-muted);">Condition</label>
            <input id="cat-condition" value="${grade}" readonly
              style="width:100%; padding: 8px; background: var(--bg-secondary); border: 1px solid var(--border);
                     border-radius: var(--radius); color: var(--green); font-size: 14px;">
          </div>
          <div>
            <label style="font-size: 11px; color: var(--text-muted);">Price</label>
            <input id="cat-price" type="number" step="0.01" value="${price}"
              style="width:100%; padding: 8px; background: var(--bg-secondary); border: 1px solid var(--border);
                     border-radius: var(--radius); color: var(--green); font-size: 14px; font-family: var(--mono);">
          </div>
        </div>
        <div>
          <label style="font-size: 11px; color: var(--text-muted);">Section</label>
          <input id="cat-section" value="${id.suggested_section || ''}" placeholder="e.g., Fiction, SF, Bio"
            style="width:100%; padding: 8px; background: var(--bg-secondary); border: 1px solid var(--border);
                   border-radius: var(--radius); color: var(--text-primary); font-size: 14px;">
        </div>
        <div style="display: flex; gap: 12px;">
          <label style="font-size: 13px; display: flex; align-items: center; gap: 6px;">
            <input type="checkbox" id="cat-signed"> Signed
          </label>
          <label style="font-size: 13px; display: flex; align-items: center; gap: 6px;">
            <input type="checkbox" id="cat-inscribed"> Inscribed
          </label>
        </div>
      </div>
    </div>

    <button id="catalogue-confirm" class="btn btn-primary btn-full" style="font-size: 16px; padding: 14px;">
      ✓ Add to Inventory
    </button>

    <button class="btn btn-secondary btn-full" style="margin-top: 8px;"
      onclick="Gibson.router.navigate('camera')">
      ← Scan Another
    </button>
  `;

  document.getElementById('catalogue-confirm').addEventListener('click', async () => {
    const btn = document.getElementById('catalogue-confirm');
    btn.disabled = true;
    btn.textContent = 'Saving...';

    try {
      // In production this calls the confirm endpoint which creates
      // Work + Edition + Stock Item in a single transaction
      alert(`Catalogued: ${document.getElementById('cat-title').value}\n` +
            `${grade} — $${document.getElementById('cat-price').value}\n` +
            `Section: ${document.getElementById('cat-section').value}`);
      Gibson.router.navigate('camera');
    } catch (e) {
      btn.disabled = false;
      btn.textContent = '✓ Add to Inventory';
      alert('Error: ' + e.message);
    }
  });
});
