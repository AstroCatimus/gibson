/**
 * Gibson — Client-side router.
 * Simple view switching. No framework. No hash routing needed for PWA.
 */

window.Gibson = window.Gibson || {};

Gibson.router = {
  views: {},
  currentView: null,

  register(name, renderFn) {
    this.views[name] = renderFn;
  },

  navigate(viewName, params = {}) {
    const container = document.getElementById('view-container');
    if (!container) return;

    // Update nav active state
    document.querySelectorAll('.nav-btn').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.view === viewName);
    });

    Gibson.store.set('currentView', viewName);
    this.currentView = viewName;

    const renderFn = this.views[viewName];
    if (renderFn) {
      container.innerHTML = '';
      renderFn(container, params);
    } else {
      container.innerHTML = `<div class="card"><p>View "${viewName}" not found.</p></div>`;
    }
  },

  init() {
    // Wire up nav buttons
    document.querySelectorAll('.nav-btn').forEach(btn => {
      btn.addEventListener('click', () => this.navigate(btn.dataset.view));
    });

    // Default view
    this.navigate('camera');
  },
};
