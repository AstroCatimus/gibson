/**
 * Gibson Customer Visit Scheduling View.
 * "I'm coming Saturday" — stores this as a visit with prep notes.
 * Employee dashboard shows upcoming visits.
 */

Gibson.router.register('customer-visit', function(container) {
  container.innerHTML = `
    <div class="card">
      <h3 style="margin-bottom: 8px;">Plan a Visit</h3>
      <p style="font-size: 12px; color: var(--text-muted); margin-bottom: 12px;">
        Let us know when you're coming and what you're interested in.
        We'll prepare recommendations.
      </p>

      <div style="display: grid; gap: 12px;">
        <div>
          <label style="font-size: 11px; color: var(--text-muted);">Your name</label>
          <input id="visit-name" placeholder="First name"
            style="width:100%; padding: 8px; background: var(--bg-secondary); border: 1px solid var(--border);
                   border-radius: var(--radius); color: var(--text-primary); font-size: 14px;">
        </div>
        <div>
          <label style="font-size: 11px; color: var(--text-muted);">When are you coming?</label>
          <input id="visit-date" type="date"
            style="width:100%; padding: 8px; background: var(--bg-secondary); border: 1px solid var(--border);
                   border-radius: var(--radius); color: var(--text-primary); font-size: 14px;">
        </div>
        <div>
          <label style="font-size: 11px; color: var(--text-muted);">Which store?</label>
          <div style="display: flex; gap: 8px;">
            <label style="font-size: 13px; display: flex; align-items: center; gap: 6px;">
              <input type="radio" name="visit-store" value="DL" checked> Driftless Books
            </label>
            <label style="font-size: 13px; display: flex; align-items: center; gap: 6px;">
              <input type="radio" name="visit-store" value="MG"> Metaphysical Graffiti
            </label>
          </div>
        </div>
        <div>
          <label style="font-size: 11px; color: var(--text-muted);">What are you looking for?</label>
          <textarea id="visit-interests" rows="3" placeholder="Interested in first edition sci-fi, anything by PKD, vintage cookbooks..."
            style="width:100%; padding: 8px; background: var(--bg-secondary); border: 1px solid var(--border);
                   border-radius: var(--radius); color: var(--text-primary); font-size: 14px; resize: vertical;"></textarea>
        </div>
        <div>
          <label style="font-size: 11px; color: var(--text-muted);">Phone (optional, for updates)</label>
          <input id="visit-phone" type="tel" placeholder="608-555-1234"
            style="width:100%; padding: 8px; background: var(--bg-secondary); border: 1px solid var(--border);
                   border-radius: var(--radius); color: var(--text-primary); font-size: 14px;">
        </div>
      </div>
    </div>

    <button id="visit-submit" class="btn btn-primary btn-full" style="font-size: 16px; padding: 14px;">
      Schedule Visit
    </button>

    <div id="visit-status"></div>
  `;

  // Default date to next Saturday
  const today = new Date();
  const saturday = new Date(today);
  saturday.setDate(today.getDate() + ((6 - today.getDay() + 7) % 7 || 7));
  document.getElementById('visit-date').value = saturday.toISOString().split('T')[0];

  document.getElementById('visit-submit').addEventListener('click', async () => {
    const name = document.getElementById('visit-name').value.trim();
    const date = document.getElementById('visit-date').value;
    const store = document.querySelector('input[name="visit-store"]:checked')?.value;
    const interests = document.getElementById('visit-interests').value.trim();
    const phone = document.getElementById('visit-phone').value.trim();

    if (!name || !date) { alert('Name and date are required'); return; }

    const btn = document.getElementById('visit-submit');
    btn.disabled = true;
    btn.textContent = 'Scheduling...';

    try {
      await Gibson.api.post('/customer/visit', {
        customer_name: name,
        visit_date: date,
        store_prefix: store,
        interests: interests,
        customer_phone: phone,
      });

      document.getElementById('visit-status').innerHTML = `
        <div class="card" style="text-align:center;margin-top:12px;">
          <p style="color:var(--green);font-weight:600;">Visit scheduled!</p>
          <p style="font-size:12px;color:var(--text-muted);margin-top:4px;">
            We'll have recommendations ready for ${name} on ${date}.
          </p>
        </div>
      `;
      btn.textContent = 'Scheduled!';
    } catch (e) {
      btn.disabled = false;
      btn.textContent = 'Schedule Visit';
      alert('Error: ' + e.message);
    }
  });
});
