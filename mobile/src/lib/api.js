/**
 * Gibson Mobile API Client.
 * Store ID and employee ID come from the Supabase session.
 * Every request carries X-Store-Id and X-Employee-Id headers.
 */

import { supabase } from './supabase';
import { logger } from './logger';

const BASE_URL = process.env.EXPO_PUBLIC_API_BASE_URL || 'http://localhost:8000';

async function getHeaders() {
  const { data: { session } } = await supabase.auth.getSession();

  const meta       = session?.user?.user_metadata || {};
  const storeId    = meta.store_id || '';        // set during onboarding; empty until store is joined
  const employeeId = session?.user?.id || '';
  const name       = meta.display_name || '';
  const email      = session?.user?.email || '';

  return {
    'Content-Type':     'application/json',
    'X-Store-Id':       storeId,
    'X-Employee-Id':    employeeId,
    'X-Employee-Email': email,
    'X-Employee-Name':  name,
  };
}

async function request(method, path, body = null, headerOverrides = {}) {
  const url = `${BASE_URL}${path}`;
  logger.debug(`→ ${method} ${path}`, body ?? undefined);

  let headers;
  try {
    headers = { ...await getHeaders(), ...headerOverrides };
  } catch (e) {
    logger.error('getHeaders failed', e.message);
    throw e;
  }

  const opts = { method, headers };
  if (body) opts.body = JSON.stringify(body);

  let resp;
  try {
    resp = await fetch(url, opts);
  } catch (e) {
    logger.error(`Network error ${method} ${path}`, e.message);
    throw new Error(`Cannot reach server at ${BASE_URL}. Is the API running?`);
  }

  if (!resp.ok) {
    const err = await resp.json().catch(() => ({ detail: resp.statusText }));
    const msg = err.detail || `HTTP ${resp.status}`;
    logger.warn(`← ${resp.status} ${path}`, msg);
    throw new Error(msg);
  }

  const data = await resp.json();
  logger.debug(`← ${resp.status} ${path}`, data);
  return data;
}

export const api = {
  get:   (path)       => request('GET',   path),
  post:  (path, body) => request('POST',  path, body),
  patch: (path, body) => request('PATCH', path, body),

  // ── Identification ──────────────────────────────────────────
  scanBarcode: (isbn13) =>
    request('POST', '/api/identification/barcode', { isbn_13: isbn13 }),

  identifyPhoto: (imageBase64, additionalImages = []) =>
    request('POST', '/api/identification/photo', {
      image_base64: imageBase64,
      additional_images: additionalImages,
    }),

  followUp: (sessionId, imageBase64, question) =>
    request('POST', '/api/identification/follow-up', {
      session_id: sessionId,
      image_base64: imageBase64,
      question,
    }),

  confirmIdentification: (data) =>
    request('POST', '/api/identification/confirm', data),

  // ── Pricing ─────────────────────────────────────────────────
  getPricing: (params) =>
    request('POST', '/api/pricing/lookup', params),

  // ── Catalogue ───────────────────────────────────────────────
  searchCatalogue: (query) =>
    request('GET', `/api/catalogue/search?q=${encodeURIComponent(query)}`),

  createStockItem: (data) =>
    request('POST', '/api/catalogue/stock-item', data),

  // ── Inventory ───────────────────────────────────────────────
  getInventory: (params = '', storeId = null) =>
    request('GET', `/api/inventory${params}`, null,
      storeId ? { 'X-Store-Id': storeId } : {}),

  getInventoryStats: (storeId = null) =>
    request('GET', '/api/inventory/count', null,
      storeId ? { 'X-Store-Id': storeId } : {}),

  getItemBySku: (sku) =>
    request('GET', `/api/inventory/sku/${encodeURIComponent(sku)}`),

  updateItem: (id, data) =>
    request('PATCH', `/api/inventory/${id}`, data),

  deleteItem: (id) =>
    request('DELETE', `/api/inventory/${id}`),

  addItemImage: (id, imageBase64, contentType = 'image/jpeg') =>
    request('POST', `/api/inventory/${id}/images`, { image_base64: imageBase64, content_type: contentType }),

  removeItemImage: (id, url) =>
    request('DELETE', `/api/inventory/${id}/images`, { url }),

  // ── POS ─────────────────────────────────────────────────────
  createSale: (items, paymentMethod) =>
    request('POST', '/api/pos/sale', { items, payment_method: paymentMethod }),

  recentSales: () =>
    request('GET', '/api/pos/recent'),

  // ── Health ──────────────────────────────────────────────────
  health: () => request('GET', '/api/health'),

  // ── Stores ──────────────────────────────────────────────────
  getMyStores: () =>
    request('GET', '/api/stores/mine'),

  lookupStoreByCode: (code) =>
    request('GET', `/api/stores/lookup?code=${encodeURIComponent(code)}`),

  createStore: (data) =>
    request('POST', '/api/stores', data),

  requestToJoin: (storeId, inviteCode, message) =>
    request('POST', `/api/stores/${storeId}/join`, { invite_code: inviteCode, message }),

  getJoinRequests: (storeId) =>
    request('GET', `/api/stores/${storeId}/requests`),

  reviewJoinRequest: (storeId, requestId, action) =>
    request('PATCH', `/api/stores/${storeId}/requests/${requestId}`, { action }),

  // ── Sections ────────────────────────────────────────────────
  getSections: () =>
    request('GET', '/api/stores/sections'),

  deleteSection: (locationId) =>
    request('DELETE', `/api/stores/sections/${locationId}`),

  // ── Defrag / Shelf Verification ─────────────────────────────
  defragStats: () =>
    request('GET', '/api/defrag/stats'),

  defragSections: () =>
    request('GET', '/api/defrag/sections'),

  defragQueue: (params = '') =>
    request('GET', `/api/defrag/queue${params}`),

  defragVerify: (stockItemId, action, extras = {}) =>
    request('POST', `/api/defrag/verify/${stockItemId}?action=${action}` +
      (extras.session_id ? `&session_id=${extras.session_id}` : '') +
      (extras.asking_price != null ? `&asking_price=${extras.asking_price}` : '') +
      (extras.condition_grade ? `&condition_grade=${extras.condition_grade}` : '') +
      (extras.section ? `&section=${encodeURIComponent(extras.section)}` : '')),

  defragStartSession: (section) =>
    request('POST', '/api/defrag/session/start' + (section ? `?section=${encodeURIComponent(section)}` : '')),

  defragEndSession: (sessionId) =>
    request('POST', `/api/defrag/session/${sessionId}/end`),

  defragMissing: (section) =>
    request('GET', `/api/defrag/missing${section ? `?section=${encodeURIComponent(section)}` : ''}`),

  defragResolveMissing: (stockItemId, resolution, section) =>
    request('PATCH', `/api/defrag/missing/${stockItemId}?resolution=${resolution}` +
      (section ? `&section=${encodeURIComponent(section)}` : '')),

  defragExport: (format = 'amazon', status = 'all') =>
    `${BASE_URL}/api/defrag/export?format=${format}&status=${status}`,

  defragDeleteSection: (locationId) =>
    request('DELETE', `/api/defrag/sections/${locationId}`),

  defragDeleteEmptySections: () =>
    request('DELETE', '/api/defrag/sections/empty'),

  // ── Shelf Scan ───────────────────────────────────────────────
  shelfScan: (imageBase64, section, sessionId) =>
    request('POST', '/api/defrag/shelf-scan', {
      image_base64: imageBase64,
      section,
      session_id: sessionId || null,
    }),

  resolveConflict: (stockItemId, action, newSection) =>
    request('POST', `/api/defrag/resolve-conflict/${stockItemId}`, {
      action,
      new_section: newSection || null,
    }),
};
