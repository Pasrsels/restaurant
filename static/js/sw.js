const CACHE_NAME = 'pos-cache-v2';
const urlsToCache = [
  '/',
  '/pos/',
  '/offline/',
  '/static/css/main.css',
  '/static/css/theme.css',
  '/static/css/bootstrap/css/bootstrap.css',
  '/static/assets/hint.css/hint.min.css',
  '/static/assets/DataTables/datatables.min.css',
  '/static/assets/boxicons/css/boxicons.css',
  '/static/js/jquery.js',
  '/static/css/bootstrap/js/bootstrap.bundle.min.js',
  '/static/assets/DataTables/datatables.min.js',
  '/static/css/pos.css',
  'https://unpkg.com/boxicons@2.1.4/css/boxicons.min.css',
  'https://cdn.jsdelivr.net/npm/select2@4.1.0-rc.0/dist/css/select2.min.css',
  'https://cdnjs.cloudflare.com/ajax/libs/animate.css/4.1.1/animate.min.css',
  'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.1.1/css/all.min.css',
  'https://unpkg.com/slim-select@latest/dist/slimselect.min.js',
  'https://unpkg.com/slim-select@latest/dist/slimselect.css',
  'https://cdn.jsdelivr.net/npm/chart.js',
  'https://cdn.jsdelivr.net/npm/sweetalert2@11',
  'https://cdn.jsdelivr.net/npm/bootstrap@5.3.0-alpha1/dist/js/bootstrap.bundle.min.js',
  'https://cdnjs.cloudflare.com/ajax/libs/toastify-js/1.6.1/toastify.js',
  'https://cdn.jsdelivr.net/npm/select2@4.1.0-rc.0/dist/js/select2.min.js'
];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => {
        console.log('Opened cache');
        return cache.addAll(urlsToCache);
      })
  );
});

self.addEventListener('fetch', event => {
  event.respondWith(
    caches.match(event.request)
      .then(response => {
        if (response) {
          return response;
        }

        const fetchRequest = event.request.clone();

        return fetch(fetchRequest).then(
          response => {
            if (!response || response.status !== 200 ) {
              return response;
            }

            const responseToCache = response.clone();
            caches.open(CACHE_NAME)
              .then(cache => {
                cache.put(event.request, responseToCache);
              });

            return response;
          }
        );
      })
      .catch(() => {
        if (event.request.mode === 'navigate') {
          return caches.match('/offline/');
        }
      })
  );
});

self.addEventListener('activate', event => {
  const cacheWhitelist = [CACHE_NAME];
  event.waitUntil(
    caches.keys().then(cacheNames => {
      return Promise.all(
        cacheNames.map(cacheName => {
          if (cacheWhitelist.indexOf(cacheName) === -1) {
            return caches.delete(cacheName);
          }
        })
      );
    })
  );
});

importScripts('/static/db.js');

self.addEventListener('sync', event => {
    if (event.tag === 'sync-pending-sales') {
        event.waitUntil(syncPendingSales());
    }
    if (event.tag === 'sync-pending-collections') {
        event.waitUntil(syncPendingCollections());
    }
});

async function syncPendingSales() {
    const pendingSales = await getPendingSales();
    if (pendingSales.length === 0) {
        return;
    }

    try {
        const csrfTokenResponse = await fetch('/pos/get-csrf-token/');
        const csrfTokenData = await csrfTokenResponse.json();
        const csrfToken = csrfTokenData.csrfToken;

        const response = await fetch('/pos/sync/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken
            },
            body: JSON.stringify(pendingSales)
        });

        if (response.ok) {
            await clearPendingSales();
            console.log('Pending sales synced successfully');
        } else {
            console.error('Failed to sync pending sales');
        }
    } catch (error) {
        console.error('Error syncing pending sales:', error);
    }
}

async function syncPendingCollections() {
    const pendingCollections = await getPendingCollections();
    if (pendingCollections.length === 0) {
        return;
    }

    try {
        const csrfTokenResponse = await fetch('/pos/get-csrf-token/');
        const csrfTokenData = await csrfTokenResponse.json();
        const csrfToken = csrfTokenData.csrfToken;

        const response = await fetch('/pos/sync-collections/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken
            },
            body: JSON.stringify(pendingCollections)
        });

        if (response.ok) {
            await clearPendingCollections();
            console.log('Pending collections synced successfully');
        } else {
            console.error('Failed to sync pending collections');
        }
    } catch (error) {
        console.error('Error syncing pending collections:', error);
    }
}