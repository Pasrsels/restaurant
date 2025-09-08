// service worker
const CACHE_NAME = 'offline-v1';
const STATIC_CACHE = 'static-v1';
const API_CACHE = 'api-v1';

self.addEventListener('install', event => {
    console.log('[SW] Install event');
    event.waitUntil(
        caches.open(STATIC_CACHE).then(cache => {
            console.log(cache)
            console.log('[SW] Caching static assets...');
            return cache.addAll([
                '/',
            ]).then(() => {
                console.log('[SW] All static assets cached!');
            }).catch(err => {
                console.error('[SW] Error caching static assets:', err);
            });
        })
    );
});

self.addEventListener('fetch', event => {
    const { request } = event;
    const url = new URL(request.url);

    if (request.mode === 'navigate') {
        console.log('[SW] Fetch navigation:', request.url);
        event.respondWith(
            caches.match('/')
                .then(response => {
                    if (response) {
                        console.log('[SW] Serving cached HTML for navigation:', request.url);
                    } else {
                        console.log('[SW] No cached HTML for navigation, fetching from network:', request.url);
                    }
                    return response || fetch(request);
                })
        );
        return;
    }

    if (url.pathname.startsWith('/api/')) {
        console.log('[SW] Fetch API:', request.url);
        event.respondWith(
            fetch(request)
                .then(response => {
                    if (response.ok) {
                        const responseClone = response.clone();
                        caches.open(API_CACHE).then(cache => {
                            cache.put(request, responseClone);
                        });
                        console.log('[SW] API response cached:', request.url);
                    }
                    return response;
                })
                .catch(() => {
                    console.warn('[SW] API fetch failed, trying cache:', request.url);
                    return caches.match(request);
                })
        );
        return;
    }
    
    event.respondWith(
        caches.match(request).then(response => {
            if (response) {
                console.log('[SW] Serving cached asset:', request.url);
            } else {
                console.log('[SW] Fetching asset from network:', request.url);
            }
            return response || fetch(request);
        })
    );
});

self.addEventListener('syncc', event => {
    if(event.tag === 'background-sync'){
        event.waitUntil(syncData)
    }
})


async function syncData(){
    
    const db = await openDB(); // pending operations from IndexeDB
    const pendingOps = await getAllPendingOperations(db)

    if (pendingOps > 0){
        try {
            const response = await fetch('api/tasks/sync', {
                method: 'POST',
                headers:{
                    'Content-Type': 'application/json',
                    'X-CSRF-Token': getCookie('csrftoken')
                },
                body: JSON.stringify({
                    data:pendingOps,
                    last_sync: localStorage.getItem('last_sync')
                })
            })

            if (response.ok){
                const data = await response.json();
                await processSyncResponse(db, data)
                localStorage.setItem('last_sync', data.sync_timestamp);
            }
        } catch(error){
            console.error('Sync failed', error);
        }
    }
}