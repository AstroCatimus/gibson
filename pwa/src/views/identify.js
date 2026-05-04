/**
 * Gibson Identification Result View.
 * Shows Gibson's identification with confidence scores.
 * One-tap confirm. Gibson always prompts the logical choice.
 */

Gibson.router.register('identify', function(container, params) {
  const r = params.result || Gibson.store.get('lastIdentification') || {};
  const conf = r.confidence || 0;
  const confClass = conf >= 0.85 ? 'confidence-high' : conf >= 0.5 ? 'confidence-med' : 'confidence-low';
  const confPct = Math.round(conf * 100);

  container.innerHTML = `
    <div class="card">
      <div style="display: flex; justify-content: space-between; align-items: start;">
        <div>
          <h2 style="font-size: 18px; margin-bottom: 4px;">${r.title || 'Unknown Title'}</h2>
          <p style="color: var(--text-secondary);">${r.author || 'Unknown Author'}</p>
        </div>
        <span class="confidence ${confClass}">${confPct}%</span>
      </div>

      <div style="margin-top: 12px; display: grid; grid-template-columns: 1fr 1fr; gap: 8px; font-size: 13px;">
        <div><span style="color:var(--text-muted)">Publisher</span><br>${r.publisher || '—'}</div>
        <div><span style="color:var(--text-muted)">Year</span><br>${r.publication_year || '—'}</div>
        <div><span style="color:var(--text-muted)">ISBN</span><br><code style="font-size:11px">${r.isbn_13 || '—'}</code></div>
        <div><span style="color:var(--text-muted)">Format</span><br>${r.format || '—'}</div>
      </div>

      ${r.per_field_confidence ? `
        <div style="margin-top: 12px; padding-top: 12px; border-top: 1px solid var(--border);">
          <p style="font-size: 11px; color: var(--text-muted); margin-bottom: 6px;">Per-field confidence</p>
          ${Object.entries(r.per_field_confidence).map(([k, v]) => `
            <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 4px;">
              <span style="font-size: 12px; width: 70px; color: var(--text-secondary);">${k}</span>
              <div style="flex:1; height: 4px; background: var(--border); border-radius: 2px;">
                <div style="width: ${v * 100}%; height: 100%; background: ${v >= 0.85 ? 'var(--green)' : v >= 0.5 ? 'var(--yellow)' : 'var(--red)'}; border-radius: 2px;"></div>
              </div>
              <span style="font-size: 11px; font-family: var(--mono); color: var(--text-muted);">${Math.round(v * 100)}%</span>
            </div>
          `).join('')}
        </div>
      ` : ''}
    </div>

    ${r.suggested_price ? `
      <div class="card">
        <div style="display: flex; justify-content: space-between; align-items: center;">
          <div>
            <div class="price-label">Suggested Price</div>
            <div class="price-tag">$${r.suggested_price.toFixed(2)}</div>
          </div>
          ${r.price_range ? `
            <div style="text-align: right;">
              <div class="price-label">Range</div>
              <span style="font-family: var(--mono); font-size: 14px; color: var(--text-secondary);">
                $${r.price_range.low?.toFixed(2)} – $${r.price_range.high?.toFixed(2)}
              </span>
            </div>
          ` : ''}
        </div>
      </div>
    ` : ''}

    ${r.follow_up_needed ? `
      <div class="card" style="border-color: var(--yellow);">
        <p style="color: var(--yellow); font-weight: 600; margin-bottom: 8px;">Gibson needs one more thing</p>
        <p style="font-size: 14px;">${r.follow_up_request || 'Additional photo needed.'}</p>
        <button class="btn btn-primary btn-full" style="margin-top: 12px;" onclick="Gibson.router.navigate('camera')">
          📸 Take Follow-up Photo
        </button>
      </div>
    ` : ''}

    ${r.suggested_section ? `
      <div style="margin-bottom: 12px;">
        <span class="section-tag">${r.suggested_section}</span>
      </div>
    ` : ''}

    <div style="display: flex; gap: 8px;">
      <button id="confirm-btn" class="btn btn-primary" style="flex: 2;">
        ✓ Confirm & Catalogue
      </button>
      <button id="edit-btn" class="btn btn-secondary" style="flex: 1;">
        Edit
      </button>
    </div>

    ${r.routing_decision === 'slow_path' ? `
      <div style="margin-top: 12px; display: flex; gap: 8px;">
        <button class="btn btn-secondary" style="flex:1;" onclick="alert('Queued for overnight research')">
          Queue Research
        </button>
        <button class="btn btn-secondary" style="flex:1;" onclick="alert('Marked in-store only')">
          In-Store Only
        </button>
      </div>
    ` : ''}
  `;

  document.getElementById('confirm-btn')?.addEventListener('click', () => {
    Gibson.router.navigate('condition', { identification: r });
  });
});
