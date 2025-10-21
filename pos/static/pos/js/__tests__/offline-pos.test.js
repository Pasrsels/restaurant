// Mock IndexedDB for testing
const mockIndexedDB = () => {
  const store = {
    data: new Map(),
    index: (name) => ({
      getAll: () => ({
        then: (callback) => {
          const items = [];
          for (const [key, value] of store.data.entries()) {
            if (value.category === name) {
              items.push(value);
            }
          }
          return Promise.resolve(callback(items));
        }
      })
    })
  };

  return {
    open: jest.fn().mockImplementation(() => ({
      onupgradeneeded: jest.fn(),
      onsuccess: jest.fn().mockImplementation(function(event) {
        if (this.onupgradeneeded) this.onupgradeneeded(event);
        if (this.onsuccess) this.onsuccess(event);
      }),
      onerror: jest.fn(),
      result: {
        createObjectStore: jest.fn().mockReturnValue(store),
        transaction: jest.fn().mockReturnValue({
          objectStore: jest.fn().mockReturnValue(store)
        })
      }
    }))
  };
};

// Mock the window.indexedDB
window.indexedDB = mockIndexedDB();

// Mock the service worker registration
window.navigator.serviceWorker = {
  register: jest.fn().mockResolvedValue({
    sync: {
      register: jest.fn().mockResolvedValue(undefined)
    }
  })
};

// Mock the fetch API
const mockFetch = (data) => {
  return jest.fn().mockImplementation((url) => {
    if (url.includes('/api/pos/products/')) {
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve(data.products || []),
        clone: function() { return this; }
      });
    }
    return Promise.reject(new Error('Not found'));
  });
};

describe('OfflinePOS', () => {
  let OfflinePOS;
  let offlinePOS;
  
  beforeAll(() => {
    // Load the OfflinePOS class
    global.OfflinePOS = require('../offline-pos.js').default;
    OfflinePOS = global.OfflinePOS;
  });
  
  beforeEach(() => {
    // Reset mocks and create a new instance before each test
    jest.clearAllMocks();
    offlinePOS = new OfflinePOS();
    
    // Mock fetch with test data
    global.fetch = mockFetch({
      products: [
        { id: 1, name: 'Test Product', price: 10.99, category: 1 }
      ]
    });
  });
  
  describe('initialization', () => {
    it('should initialize the database', async () => {
      await offlinePOS.initializeDB();
      expect(indexedDB.open).toHaveBeenCalledWith('RestaurantPOS', 1);
    });
    
    it('should register the service worker', async () => {
      await new Promise(resolve => setTimeout(resolve, 100)); // Wait for registration
      expect(navigator.serviceWorker.register).toHaveBeenCalledWith('/pos/static/pos/js/service-worker.js');
    });
  });
  
  describe('online/offline handling', () => {
    it('should handle online status', async () => {
      // Simulate going online
      window.dispatchEvent(new Event('online'));
      
      // Check if the sync method was called
      await new Promise(resolve => setTimeout(resolve, 100));
      expect(global.fetch).toHaveBeenCalled();
    });
    
    it('should handle offline status', () => {
      // Simulate going offline
      window.dispatchEvent(new Event('offline'));
      expect(document.body.classList.contains('offline')).toBe(true);
    });
  });
  
  describe('product management', () => {
    it('should get products from local DB', async () => {
      // Mock the database response
      const mockProducts = [
        { id: 1, name: 'Test Product', price: 10.99, category: 1 }
      ];
      
      // Mock the IndexedDB get all request
      const mockRequest = {
        onsuccess: null,
        result: mockProducts
      };
      
      // Mock the transaction and store
      const mockStore = {
        getAll: jest.fn().mockReturnValue(mockRequest)
      };
      
      const mockTransaction = {
        objectStore: jest.fn().mockReturnValue(mockStore)
      };
      
      offlinePOS.db = {
        transaction: jest.fn().mockReturnValue(mockTransaction)
      };
      
      // Call the method and wait for the promise to resolve
      const products = await offlinePOS.getProducts();
      
      // Check the results
      expect(products).toEqual(mockProducts);
      expect(offlinePOS.db.transaction).toHaveBeenCalledWith(['products'], 'readonly');
    });
    
    it('should save products to local DB', async () => {
      const products = [
        { id: 1, name: 'Test Product', price: 10.99, category: 1 }
      ];
      
      // Mock the transaction
      const mockStore = {
        put: jest.fn()
      };
      
      const mockTransaction = {
        objectStore: jest.fn().mockReturnValue(mockStore),
        oncomplete: jest.fn(),
        onerror: jest.fn()
      };
      
      offlinePOS.db = {
        transaction: jest.fn().mockReturnValue(mockTransaction)
      };
      
      // Call the method
      await offlinePOS.saveProducts(products);
      
      // Check that the put method was called for each product
      expect(mockStore.put).toHaveBeenCalledWith({
        id: 1,
        name: 'Test Product',
        price: 10.99,
        category: 1,
        image: 'placeholder.jpg'
      });
    });
  });
  
  describe('order management', () => {
    it('should save order locally when offline', async () => {
      // Simulate offline mode
      jest.spyOn(navigator, 'onLine', 'get').mockReturnValue(false);
      
      // Mock the transaction
      const mockStore = {
        add: jest.fn().mockImplementation((data, key, callback) => {
          if (callback) callback();
          return { onsuccess: (cb) => cb() };
        })
      };
      
      const mockTransaction = {
        objectStore: jest.fn().mockReturnValue(mockStore)
      };
      
      offlinePOS.db = {
        transaction: jest.fn().mockReturnValue(mockTransaction)
      };
      
      // Mock the notification function
      offlinePOS.showNotification = jest.fn();
      
      // Create a test order
      const orderData = {
        items: [
          { productId: 1, quantity: 2, price: 10.99 }
        ],
        total: 21.98
      };
      
      // Call the method
      await offlinePOS.saveOrderLocally(orderData);
      
      // Check that the order was saved locally
      expect(offlinePOS.db.transaction).toHaveBeenCalledWith(['pendingOrders'], 'readwrite');
      expect(offlinePOS.showNotification).toHaveBeenCalledWith(
        'Order saved locally. Will sync when online.',
        'info'
      );
    });
    
    it('should sync pending orders when online', async () => {
      // Simulate online mode
      jest.spyOn(navigator, 'onLine', 'get').mockReturnValue(true);
      
      // Mock pending orders
      const pendingOrders = [
        {
          id: 1,
          data: { items: [{ productId: 1, quantity: 1 }] },
          csrf_token: 'test-token'
        }
      ];
      
      // Mock the getPendingOrders method
      offlinePOS.getPendingOrders = jest.fn().mockResolvedValue(pendingOrders);
      
      // Mock the submitOrder method
      offlinePOS.submitOrder = jest.fn().mockResolvedValue({});
      
      // Mock the removePendingOrder method
      offlinePOS.removePendingOrder = jest.fn().mockResolvedValue(undefined);
      
      // Call the sync method
      await offlinePOS.syncPendingOrders();
      
      // Check that the order was processed
      expect(offlinePOS.submitOrder).toHaveBeenCalledWith(pendingOrders[0]);
      expect(offlinePOS.removePendingOrder).toHaveBeenCalledWith(1);
    });
  });
});
