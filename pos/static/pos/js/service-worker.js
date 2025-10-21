const CACHE_NAME = 'restaurant-pos-v1';
const API_CACHE = 'api-cache-v1';
const urlsToCache = [
  '/',
  '/static/pos/css/style.css',
  '/static/pos/js/app.js',
  '/static/pos/images/offline.png'
];

// Install service worker and cache static assets
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => cache.addAll(urlsToCache))
  );
});

// Fetch event for handling requests
self.addEventListener('fetch', event => {
  const { request } = event;
  
  // Cache API responses for offline use
  if (request.url.includes('/api/')) {
    event.respondWith(
      caches.open(API_CACHE).then(cache => {
        return fetch(request)
          .then(response => {
            // Clone the response to store in cache
            const responseToCache = response.clone();
            cache.put(request, responseToCache);
            return response;
          })
          .catch(() => {
            // Return cached response if fetch fails
            return caches.match(request);
          });
      })
    );
  } else {
    // For static assets, try cache first, then network
    event.respondWith(
      caches.match(request)
        .then(response => response || fetch(request))
    );
  }
});

// Sync event for background sync
self.addEventListener('sync', event => {
  if (event.tag === 'sync-orders') {
    event.waitUntil(syncOrders());
  }
});

// Function to sync pending orders
async function syncOrders() {
  const registration = await self.registration;
  const db = await openDatabase();
  const tx = db.transaction('pendingOrders', 'readwrite');
  const store = tx.objectStore('pendingOrders');
  const orders = await store.getAll();

  for (const order of orders) {
    try {
      const response = await fetch('/api/orders/', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': order.csrf_token
        },
        body: JSON.stringify(order.data)
      });

      if (response.ok) {
        await store.delete(order.id);
      }
    } catch (error) {
      console.error('Sync error:', error);
    }
  }
}

// Open IndexedDB
function openDatabase() {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open('RestaurantPOS', 1);

    request.onupgradeneeded = (event) => {
      const db = event.target.result;
      
      // Create object store for pending orders
      if (!db.objectStoreNames.contains('pendingOrders')) {
        const store = db.createObjectStore('pendingOrders', { keyPath: 'id', autoIncrement: true });
        store.createIndex('timestamp', 'timestamp', { unique: false });
      }
      
      // Create object store for products cache
      if (!db.objectStoreNames.contains('products')) {
        const store = db.createObjectStore('products', { keyPath: 'id' });
        store.createIndex('category', 'category', { unique: false });
      }
    };

    request.onsuccess = (event) => resolve(event.target.result);
    request.onerror = (event) => reject(event.target.error);
  });
}
