/**
 * Gibson — API client.
 * All API calls go through here. Adds store context headers.
 */

window.Gibson = window.Gibson || {};

Gibson.api = {
  baseUrl: '/api',

  async request(method, path, body = null) {
    const headers = {
      'Content-Type': 'application/json',
      'X-Store-Id': Gibson.store.get('storeId'),
    };
    const employeeId = Gibson.store.get('employeeId');
    if (employeeId) headers['X-Employee-Id'] = employeeId;

    const opts = { method, headers };
    if (body) opts.body = JSON.stringify(body);

    const response = await fetch(this.baseUrl + path, opts);
    if (!response.ok) {
      const err = await response.json().catch(() => ({ detail: response.statusText }));
      throw new Error(err.detail || 'Request failed');
    }
    return response.json();
  },

  get(path) { return this.request('GET', path); },
  post(path, body) { return this.request('POST', path, body); },
  patch(path, body) { return this.request('PATCH', path, body); },

  // ─── Identification ───
  async identifyBarcode(isbn13) {
    return this.post('/identification/barcode', {
      isbn_13: isbn13, raw_barcode: isbn13, barcode_type: 'EAN-13',
    });
  },

  async identifyPhoto(imageBase64) {
    return this.post('/identification/photo', {
      image_base64: imageBase64,
      store_id: Gibson.store.get('storeId'),
    });
  },

  // ─── Pricing ───
  async lookupPricing(params) {
    return this.post('/pricing/lookup', params);
  },

  // ─── Inventory ───
  async listInventory(params = {}) {
    const qs = new URLSearchParams(params).toString();
    return this.get('/inventory/' + (qs ? '?' + qs : ''));
  },

  async getStockItem(id) {
    return this.get('/inventory/' + id);
  },

  async lookupSku(sku) {
    return this.get('/inventory/sku/' + encodeURIComponent(sku));
  },

  async inventoryCount() {
    return this.get('/inventory/count');
  },

  // ─── POS ───
  async createSale(saleData) {
    return this.post('/pos/sale', saleData);
  },

  // ─── Customer ───
  async browse(params = {}) {
    const qs = new URLSearchParams(params).toString();
    return this.get('/customer/browse' + (qs ? '?' + qs : ''));
  },

  // ─── Conversation ───
  async sendMessage(message, mode = 'ambient', conversationId = null) {
    return this.post('/conversation/message', {
      conversation_id: conversationId,
      mode,
      message,
    });
  },

  // ─── Health ───
  async health() { return this.get('/health'); },
};
