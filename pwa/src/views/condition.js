/**
 * Gibson Condition View.
 * Two modes — Gibson determines which before asking.
 *
 * TAP mode (first floor / commodity / under $15):
 *   Single tap: Fine / VG+ / VG / Good / Reading Copy
 *
 * QA mode (upstairs / online listing / $15+):
 *   Seven questions. Generated condition description. DJ grade if applicable.
 */

Gibson.router.register('condition', function(container, params) {
  const identification = params.identification || {};
  const price = identification.suggested_price || 0;
  const mode = price >= 15 ? 'qa' : 'tap';

  if (mode === 'tap') {
    container.innerHTML = `
      <div class="card">
        <h3 style="margin-bottom: 4px;">Condition</h3>
        <p style="font-size: 12px; color: var(--text-muted); margin-bottom: 16px;">
          Tap mode — quick grade for in-store stock
        </p>
        <div style="display: flex; flex-direction: column; gap: 8px;">
          ${['Fine', 'Very Good+', 'Very Good', 'Good', 'Fair', 'Poor'].map(grade => `
            <button class="btn btn-secondary btn-full condition-tap" data-grade="${grade}"
              style="justify-content: start; font-size: 16px;">
              ${grade}
            </button>
          `).join('')}
        </div>
      </div>
    `;

    container.querySelectorAll('.condition-tap').forEach(btn => {
      btn.addEventListener('click', () => {
        const grade = btn.dataset.grade;
        Gibson.router.navigate('catalogue', {
          identification, conditionGrade: grade, conditionMode: 'tap',
        });
      });
    });

  } else {
    // QA mode — seven questions for online listing
    container.innerHTML = `
      <div class="card">
        <h3 style="margin-bottom: 4px;">Condition Assessment</h3>
        <p style="font-size: 12px; color: var(--text-muted); margin-bottom: 16px;">
          QA mode — detailed for online listing ($${price.toFixed(2)})
        </p>
        <div id="qa-questions"></div>
        <button id="qa-submit" class="btn btn-primary btn-full" style="margin-top: 16px;">
          Generate Condition Description
        </button>
      </div>
    `;

    const questions = [
      { id: 'binding', q: 'Binding tight and square?', opts: ['Yes', 'Slightly loose', 'Cocked', 'Broken'] },
      { id: 'pages', q: 'Page condition?', opts: ['Clean', 'Light toning', 'Foxing', 'Staining', 'Tears'] },
      { id: 'cover', q: 'Cover/boards?', opts: ['Clean', 'Light wear', 'Moderate wear', 'Heavy wear'] },
      { id: 'spine', q: 'Spine?', opts: ['Bright', 'Faded', 'Sunned', 'Creased', 'Damage'] },
      { id: 'dj', q: 'Dust jacket?', opts: ['Not applicable', 'Present/Fine', 'Present/Good', 'Present/Fair', 'Missing'] },
      { id: 'markings', q: 'Previous owner markings?', opts: ['None', 'Name only', 'Light notes', 'Heavy marking'] },
      { id: 'odor', q: 'Odor?', opts: ['None', 'Light mustiness', 'Smoke', 'Strong odor'] },
    ];

    const qaDiv = document.getElementById('qa-questions');
    questions.forEach(q => {
      qaDiv.innerHTML += `
        <div style="margin-bottom: 12px;">
          <p style="font-size: 13px; font-weight: 600; margin-bottom: 6px;">${q.q}</p>
          <div style="display: flex; flex-wrap: wrap; gap: 6px;">
            ${q.opts.map(opt => `
              <button class="section-tag qa-opt" data-question="${q.id}" data-value="${opt}">${opt}</button>
            `).join('')}
          </div>
        </div>
      `;
    });

    const answers = {};
    container.querySelectorAll('.qa-opt').forEach(btn => {
      btn.addEventListener('click', () => {
        // Deselect siblings
        container.querySelectorAll(`.qa-opt[data-question="${btn.dataset.question}"]`).forEach(b => {
          b.style.background = ''; b.style.color = '';
        });
        btn.style.background = 'var(--accent)';
        btn.style.color = 'white';
        answers[btn.dataset.question] = btn.dataset.value;
      });
    });

    document.getElementById('qa-submit').addEventListener('click', () => {
      // Simple grade derivation from answers
      let grade = 'Very Good';
      const negative = Object.values(answers).filter(v =>
        ['Heavy wear', 'Broken', 'Staining', 'Tears', 'Heavy marking', 'Strong odor', 'Damage'].includes(v)
      ).length;
      if (negative === 0) grade = 'Fine';
      else if (negative === 1) grade = 'Very Good+';
      else if (negative <= 2) grade = 'Very Good';
      else if (negative <= 3) grade = 'Good+';
      else grade = 'Good';

      Gibson.router.navigate('catalogue', {
        identification,
        conditionGrade: grade,
        conditionMode: 'qa',
        conditionQA: answers,
      });
    });
  }
});
