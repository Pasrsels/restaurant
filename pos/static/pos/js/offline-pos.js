// Offline POS functionality
class OfflinePOS {
  constructor() {
    this.dbName = 'RestaurantPOS';
    this.dbVersion = 1;
    this.db = null;
    this.initializeDB();
    this.registerServiceWorker();
    this.setupEventListeners();
  }

  // Initialize IndexedDB
  async initializeDB() {
    return new Promise((resolve, reject) => {
      const request = indexedDB.open(this.dbName, this.dbVersion);

      request.onerror = (event) => {
        console.error('Database error:', event.target.error);
        reject(event.target.error);
      };

      request.onsuccess = (event) => {
        this.db = event.target.result;
        resolve(this.db);
      };

      request.onupgradeneeded = (event) => {
        const db = event.target.result;
        
        // Create object store for products
        if (!db.objectStoreNames.contains('products')) {
          const store = db.createObjectStore('products', { keyPath: 'id' });
          store.createIndex('category', 'category', { unique: false });
        }
        
        // Create object store for pending orders
        if (!db.objectStoreNames.contains('pendingOrders')) {
          const store = db.createObjectStore('pendingOrders', { 
            keyPath: 'id',
            autoIncrement: true 
          });
          store.createIndex('timestamp', 'timestamp', { unique: false });
        }
      };
    });
  }

  // Register service worker
  async registerServiceWorker() {
    if ('serviceWorker' in navigator) {
      try {
        await navigator.serviceWorker.register('/pos/static/pos/js/service-worker.js');
        console.log('Service Worker registered');
      } catch (error) {
        console.error('Service Worker registration failed:', error);
      }
    }
  }

  // Setup event listeners
  setupEventListeners() {
    // Listen for online/offline status changes
    window.addEventListener('online', () => this.handleOnlineStatus());
    window.addEventListener('offline', () => this.handleOfflineStatus());
    
    // Check if we're online/offline on page load
    if (navigator.onLine) {
      this.handleOnlineStatus();
    } else {
      this.handleOfflineStatus();
    }
  }

  // Handle online status
  async handleOnlineStatus() {
    console.log('Online - Syncing data...');
    document.body.classList.remove('offline');
    await this.syncPendingOrders();
    await this.updateLocalProducts();
  }

  // Handle offline status
  handleOfflineStatus() {
    console.log('Offline mode - Using local data');
    document.body.classList.add('offline');
  }

  // Get all products from local DB
  async getProducts() {
    return new Promise((resolve, reject) => {
      const transaction = this.db.transaction(['products'], 'readonly');
      const store = transaction.objectStore('products');
      const request = store.getAll();

      request.onsuccess = () => resolve(request.result || []);
      request.onerror = (event) => reject(event.target.error);
    });
  }

  // Get products by category from local DB
  async getProductsByCategory(categoryId) {
    return new Promise((resolve, reject) => {
      const transaction = this.db.transaction(['products'], 'readonly');
      const store = transaction.objectStore('products');
      const index = store.index('category');
      const request = index.getAll(categoryId);

      request.onsuccess = () => resolve(request.result || []);
      request.onerror = (event) => reject(event.target.error);
    });
  }

  // Save products to local DB
  async saveProducts(products) {
    return new Promise((resolve, reject) => {
      const transaction = this.db.transaction(['products'], 'readwrite');
      const store = transaction.objectStore('products');
      
      products.forEach(product => {
        store.put({
          id: product.id,
          name: product.name,
          price: parseFloat(product.price),
          category: product.category,
          image: product.image || 'placeholder.jpg',
          // Add other product fields as needed
          ...product
        });
      });

      transaction.oncomplete = () => resolve();
      transaction.onerror = (event) => reject(event.target.error);
    });
  }

  // Save order to local DB when offline
  async saveOrderLocally(orderData) {
    return new Promise((resolve, reject) => {
      const transaction = this.db.transaction(['pendingOrders'], 'readwrite');
      const store = transaction.objectStore('pendingOrders');
      
      const order = {
        data: orderData,
        timestamp: new Date().getTime(),
        status: 'pending',
        csrf_token: this.getCSRFToken()
      };

      const request = store.add(order);

      request.onsuccess = () => {
        this.showNotification('Order saved locally. Will sync when online.', 'info');
        resolve(request.result);
      };
      request.onerror = (event) => {
        console.error('Error saving order locally:', event.target.error);
        reject(event.target.error);
      };
    });
  }

  // Sync pending orders with server
  async syncPendingOrders() {
    if (!navigator.onLine) return;

    const orders = await this.getPendingOrders();
    
    for (const order of orders) {
      try {
        await this.submitOrder(order);
        await this.removePendingOrder(order.id);
      } catch (error) {
        console.error('Error syncing order:', error);
      }
    }
  }

  // Get all pending orders
  async getPendingOrders() {
    return new Promise((resolve, reject) => {
      const transaction = this.db.transaction(['pendingOrders'], 'readonly');
      const store = transaction.objectStore('pendingOrders');
      const request = store.getAll();

      request.onsuccess = () => resolve(request.result || []);
      request.onerror = (event) => reject(event.target.error);
    });
  }

  // Remove pending order after successful sync
  async removePendingOrder(orderId) {
    return new Promise((resolve, reject) => {
      const transaction = this.db.transaction(['pendingOrders'], 'readwrite');
      const store = transaction.objectStore('pendingOrders');
      const request = store.delete(orderId);

      request.onsuccess = () => resolve();
      request.onerror = (event) => reject(event.target.error);
    });
  }

  // Submit order to server
  async submitOrder(order) {
    return fetch('/api/orders/', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': order.csrf_token
      },
      body: JSON.stringify(order.data)
    }).then(response => {
      if (!response.ok) throw new Error('Failed to submit order');
      return response.json();
    });
  }

  // Update local products from server
  async updateLocalProducts() {
    if (!navigator.onLine) return;

    try {
      const response = await fetch('/api/products/');
      if (!response.ok) throw new Error('Failed to fetch products');
      
      const products = await response.json();
      await this.saveProducts(products);
      console.log('Products updated in local DB');
    } catch (error) {
      console.error('Error updating local products:', error);
    }
  }

  // Helper function to get CSRF token
  getCSRFToken() {
    const cookieValue = document.cookie
      .split('; ')
      .find(row => row.startsWith('csrftoken='))
      ?.split('=')[1];
    return cookieValue || '';
  }

  // Show notification to user
  showNotification(message, type = 'info') {
    // Implement your notification system here
    console.log(`[${type.toUpperCase()}] ${message}`);
    // Example: toastr[type](message);
  }
}

// Initialize the OfflinePOS when the DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
  window.offlinePOS = new OfflinePOS();
});
