/**
 * Gibson — Global state store.
 * Simple reactive state management. No framework.
 */

window.Gibson = window.Gibson || {};

Gibson.store = {
  state: {
    storeId: localStorage.getItem('gibson_store_id') || 'a1b2c3d4-0001-4000-8000-000000000001',
    storeName: localStorage.getItem('gibson_store_name') || 'Driftless Books & Music',
    storePrefix: localStorage.getItem('gibson_store_prefix') || 'DL',
    employeeId: localStorage.getItem('gibson_employee_id') || null,
    employeeName: localStorage.getItem('gibson_employee_name') || null,
    currentView: 'camera',
    // Identification state
    lastIdentification: null,
    lastPricing: null,
    // POS state
    currentSale: { items: [], subtotal: 0, lastSectionCode: null },
    // Conversation
    conversationId: null,
  },

  listeners: [],

  get(key) {
    return this.state[key];
  },

  set(key, value) {
    this.state[key] = value;
    if (key === 'storeId') localStorage.setItem('gibson_store_id', value);
    if (key === 'storePrefix') localStorage.setItem('gibson_store_prefix', value);
    this.notify(key, value);
  },

  subscribe(fn) {
    this.listeners.push(fn);
    return () => { this.listeners = this.listeners.filter(l => l !== fn); };
  },

  notify(key, value) {
    this.listeners.forEach(fn => fn(key, value));
  },
};
