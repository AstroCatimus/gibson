/**
 * Gibson Customer Want List View.
 * Customers submit a title/author/ISBN they're looking for.
 * SMS notification via Twilio on confirmed match. Not PWA push.
 */

Gibson.router.register('customer-wantlist', function(container, params) {
  const prefill = params?.query || '';

  container.innerHTML = `
    <div class="card">
      <h3 style="margin-bottom: 8px;">Want List</h3>
      <p style="font-size: 12px; color: var(--text-muted); margin-bottom: 12px;">
        Tell us what you're looking for. We'll text you when we find it.
      </p>

      <div style="display: grid; gap: 12px;">
        <div>
          <label style="font-size: 11px; color: var(--text-muted);">What are you looking for?</label>
          <input id="want-query" value="${prefill}" placeholder="Title, author, or ISBN..."
            style="width:100%; padding: 10px; background: var(--bg-secondary); border: 1px solid var(--border);
                   border-radius: var(--radius); color: var(--text-primary); font-size: 14px;">
        </div>
        <div>
          <label style="font-size: 11px; color: var(--text-muted);">Your name</label>
          <input id="want-name" placeholder="First name"
            style="width:100%; padding: 8px; background: var(--bg-secondary); border: 1px solid var(--border);
                   border-radius: var(--radius); color: var(--text-primary); font-size: 14px;">
        </div>
        <div>
          <label style="font-size: 11px; color: var(--text-muted);">Phone (for text notification)</label>
          <input id="want-phone" type="tel" placeholder="608-555-1234"
            style="width:100%; padding: 8px; background: var(--bg-secondary); border: 1px solid var(--border);
                   border-radius: var(--radius); color: var(--text-primary); font-size: 14px;">
        </div>
        <div>
          <label style="font-size: 11px; color: var(--text-muted);">Notes (optional)</label>
          <textarea id="want-notes" rows="2" placeholder="First edition only, any condition, etc."
            style="width:100%; padding: 8px; background: var(--bg-secondary); border: 1px solid var(--border);
                   border-radius: var(--radius); color: var(--text-primary); font-size: 14px; resize: vertical;"></textarea>
        </div>
      </div>
    </div>

    <button id="want-submit" class="btn btn-primary btn-full" style="font-size: 16px; padding: 14px;">
      Add to Want List
    </button>

    <div id="want-status"></div>
  `;

  document.getElementById('want-submit').addEventListener('click', async () => {
    const query = document.getElementById('want-query').value.trim();
    const name = document.getElementById('want-name').value.trim();
    const phone = document.getElementById('want-phone').value.trim();
    const notes = document.getElementById('want-notes').value.trim();

    if (!query) { alert('Please describe what you\'re looking for'); return; }
    if (!phone) { alert('Phone number required for notifications'); return; }

    const btn = document.getElementById('want-submit');
    btn.disabled = true;
    btn.textContent = 'Submitting...';

    try {
      await Gibson.api.post('/customer/want-list', {
        search_query: query,
        customer_name: name,
        customer_phone: phone,
        notes: notes,
      });

      document.getElementById('want-status').innerHTML = `
        <div class="card" style="text-align:center;margin-top:12px;">
          <p style="color:var(--green);font-weight:600;">Added to want list!</p>
          <p style="font-size:12px;color:var(--text-muted);margin-top:4px;">
            We'll text ${phone} when we find a match.
          </p>
        </div>
      `;
      btn.textContent = 'Added!';
    } catch (e) {
      btn.disabled = false;
      btn.textContent = 'Add to Want List';
      alert('Error: ' + e.message);
    }
  });
});
