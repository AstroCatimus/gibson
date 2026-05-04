/**
 * Gibson PWA Service Worker
 * Cache-first for static assets, network-first for API calls.
 * Offline queue for identification and POS when network drops.
 */

const CACHE_NAME = 'gibson-v1';
const STATIC_ASSETS = [
  '/',
  '/static/src/lib/api.js',
  '/static/src/lib/router.js',
  '/static/src/lib/store.js',
  '/static/src/lib/voice.js',
];

// Install — cache static assets
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(STATIC_ASSETS))
  );
  self.skipWaiting();
});

// Activate — clean old caches
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

// Fetch — network-first for API, cache-first for static
self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  if (url.pathname.startsWith('/api/')) {
    // Network-first for API calls
    event.respondWith(
      fetch(event.request).catch(() => caches.match(event.request))
    );
  } else {
    // Cache-first for static assets
    event.respondWith(
      caches.match(event.request).then((cached) => cached || fetch(event.request))
    );
  }
});

// Background sync for offline queue
self.addEventListener('sync', (event) => {
  if (event.tag === 'offline-queue') {
    event.waitUntil(processOfflineQueue());
  }
});

async function processOfflineQueue() {
  // Process queued identification and POS requests
  const db = await openOfflineDB();
  const tx = db.transaction('queue', 'readonly');
  const store = tx.objectStore('queue');
  const items = await store.getAll();

  for (const item of items) {
    try {
      await fetch(item.url, {
        method: item.method,
        headers: item.headers,
        body: item.body,
      });
      // Remove from queue on success
      const delTx = db.transaction('queue', 'readwrite');
      delTx.objectStore('queue').delete(item.id);
    } catch (e) {
      // Keep in queue for next sync
    }
  }
}

function openOfflineDB() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open('gibson-offline', 1);
    request.onupgradeneeded = (e) => {
      e.target.result.createObjectStore('queue', { keyPath: 'id', autoIncrement: true });
    };
    request.onsuccess = (e) => resolve(e.target.result);
    request.onerror = (e) => reject(e.target.error);
  });
}
