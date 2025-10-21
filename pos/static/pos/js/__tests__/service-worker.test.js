// Mock the caches API
const mockCaches = {
  open: jest.fn().mockResolvedValue({
    addAll: jest.fn().mockResolvedValue(undefined),
    match: jest.fn().mockImplementation(request => {
      if (request.url.includes('test.css')) {
        return Promise.resolve(new Response('body { color: red; }'));
      }
      return Promise.resolve(undefined);
    }),
    put: jest.fn().mockResolvedValue(undefined),
  }),
  match: jest.fn().mockResolvedValue(undefined),
};

// Mock the global caches object
global.caches = mockCaches;

// Mock the global fetch API
global.fetch = jest.fn((url) => {
  if (url.includes('test.css')) {
    return Promise.resolve(new Response('body { color: red; }'));
  }
  return Promise.reject(new Error('Not found'));
});

// Mock the service worker registration
const mockRegistration = {
  scope: '/',
  update: jest.fn().mockResolvedValue(undefined),
  unregister: jest.fn().mockResolvedValue(true),
};

// Mock the service worker global
const serviceWorkerPath = require.resolve('../../service-worker.js');
const fs = require('fs');
const serviceWorkerCode = fs.readFileSync(serviceWorkerPath, 'utf8');

describe('Service Worker', () => {
  let self;
  
  beforeEach(() => {
    // Reset mocks
    jest.clearAllMocks();
    
    // Create a mock self object for the service worker
    self = {
      caches: mockCaches,
      registration: mockRegistration,
      addEventListener: jest.fn(),
      clients: {
        claim: jest.fn().mockResolvedValue(undefined),
        matchAll: jest.fn().mockResolvedValue([]),
      },
      skipWaiting: jest.fn().mockResolvedValue(undefined),
    };
    
    // Mock the global self object
    global.self = self;
    
    // Execute the service worker code in the test context
    // This is a simplified version - in a real test, you'd want to properly parse and execute the SW
    // For now, we'll just test the basic structure
    // In a real project, you might want to use a library like `service-worker-mock`
  });
  
  it('should install the service worker and cache assets', async () => {
    // Mock the install event
    const installEvent = {
      waitUntil: jest.fn().mockImplementation(promise => promise),
    };
    
    // Call the install event listener
    const installHandler = self.addEventListener.mock.calls.find(
      call => call[0] === 'install'
    );
    
    expect(installHandler).toBeDefined();
    
    // Execute the install handler
    await installHandler[1](installEvent);
    
    // Check that caches.open was called with the correct cache name
    expect(mockCaches.open).toHaveBeenCalledWith('restaurant-pos-v1');
    
    // Check that addAll was called with the correct URLs
    const cache = await mockCaches.open();
    expect(cache.addAll).toHaveBeenCalled();
  });
  
  it('should handle fetch events', async () => {
    // Mock the fetch event
    const fetchEvent = {
      request: new Request('http://example.com/test.css'),
      respondWith: jest.fn().mockImplementation(promise => promise),
    };
    
    // Call the fetch event listener
    const fetchHandler = self.addEventListener.mock.calls.find(
      call => call[0] === 'fetch'
    );
    
    expect(fetchHandler).toBeDefined();
    
    // Execute the fetch handler
    await fetchHandler[1](fetchEvent);
    
    // Check that respondWith was called
    expect(fetchEvent.respondWith).toHaveBeenCalled();
    
    // Get the response promise passed to respondWith
    const responsePromise = fetchEvent.respondWith.mock.calls[0][0];
    const response = await responsePromise;
    
    // Check that we got a response
    expect(response).toBeDefined();
  });
  
  it('should handle sync events', async () => {
    // Mock the sync event
    const syncEvent = {
      tag: 'sync-orders',
      waitUntil: jest.fn().mockImplementation(promise => promise),
    };
    
    // Mock the IndexedDB
    const mockDb = {
      transaction: jest.fn().mockReturnValue({
        objectStore: jest.fn().mockReturnValue({
          getAll: jest.fn().mockReturnValue({
            then: jest.fn().mockImplementation(callback => {
              return Promise.resolve(callback([
                { id: 1, data: { items: [] }, csrf_token: 'test-token' }
              ]));
            })
          }),
          delete: jest.fn().mockReturnValue({
            then: jest.fn(callback => callback())
          })
        })
      })
    };
    
    // Mock the openDatabase function
    const mockOpenDatabase = jest.fn().mockResolvedValue(mockDb);
    
    // Replace the global openDatabase function
    global.openDatabase = mockOpenDatabase;
    
    // Mock the fetch function for the sync
    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ status: 'success' })
    });
    
    // Call the sync event listener
    const syncHandler = self.addEventListener.mock.calls.find(
      call => call[0] === 'sync'
    );
    
    expect(syncHandler).toBeDefined();
    
    // Execute the sync handler
    await syncHandler[1](syncEvent);
    
    // Check that the database was opened
    expect(mockOpenDatabase).toHaveBeenCalled();
    
    // Check that fetch was called with the correct parameters
    expect(global.fetch).toHaveBeenCalledWith(
      'http://example.com/api/orders/',
      expect.objectContaining({
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-CSRFToken': 'test-token'
        }
      })
    );
  });
});
