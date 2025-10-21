// Register service worker for offline functionality
if ('serviceWorker' in navigator) {
  window.addEventListener('load', function() {
    navigator.serviceWorker.register('{% static "pos/js/service-worker.js" %}').then(
      function(registration) {
        console.log('ServiceWorker registration successful with scope: ', registration.scope);
        
        // Check if the browser supports background sync
        if ('sync' in registration) {
          // Register for background sync
          document.addEventListener('online', function() {
            registration.sync.register('sync-orders')
              .then(() => console.log('Registered background sync'))
              .catch(err => console.error('Background sync registration failed:', err));
          });
        }
      },
      function(err) {
        console.error('ServiceWorker registration failed: ', err);
      }
    );
  });
}

// Online/Offline status handling
function updateOnlineStatus() {
  const status = document.getElementById('connection-status');
  if (navigator.onLine) {
    if (status) {
      status.textContent = 'Online';
      status.className = 'badge bg-success';
    }
    // Sync any pending orders when coming back online
    if (window.offlinePOS) {
      window.offlinePOS.syncPendingOrders();
    }
  } else {
    if (status) {
      status.textContent = 'Offline';
      status.className = 'badge bg-danger';
    }
  }
}

// Update status on load
window.addEventListener('load', updateOnlineStatus);

// Update status when connection changes
window.addEventListener('online', updateOnlineStatus);
window.addEventListener('offline', updateOnlineStatus);
