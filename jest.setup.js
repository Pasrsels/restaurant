// Mock the localStorage
const localStorageMock = (() => {
  let store = {};
  
  return {
    getItem: (key) => store[key] || null,
    setItem: (key, value) => {
      store[key] = value.toString();
    },
    removeItem: (key) => {
      delete store[key];
    },
    clear: () => {
      store = {};
    },
  };
})();

// Mock the sessionStorage
const sessionStorageMock = (() => {
  let store = {};
  
  return {
    getItem: (key) => store[key] || null,
    setItem: (key, value) => {
      store[key] = value.toString();
    },
    removeItem: (key) => {
      delete store[key];
    },
    clear: () => {
      store = {};
    },
  };
})();

// Mock the window object
Object.defineProperty(window, 'localStorage', { value: localStorageMock });
Object.defineProperty(window, 'sessionStorage', { value: sessionStorageMock });

// Mock the matchMedia function
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: jest.fn().mockImplementation(query => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: jest.fn(),
    removeListener: jest.fn(),
    addEventListener: jest.fn(),
    removeEventListener: jest.fn(),
    dispatchEvent: jest.fn(),
  })),
});

// Mock the scrollTo function
window.scrollTo = jest.fn();

// Mock the service worker
if (typeof window !== 'undefined') {
  // Mock the service worker registration
  const mockRegister = jest.fn().mockResolvedValue({
    active: { state: 'activated' },
    installing: null,
    waiting: null,
  });
  
  // Mock the service worker container
  const mockServiceWorker = {
    register: mockRegister,
    ready: Promise.resolve({
      controller: { state: 'activated' },
    }),
    controller: { state: 'activated' },
    addEventListener: jest.fn(),
    removeEventListener: jest.fn(),
    dispatchEvent: jest.fn(),
  };
  
  // Add to window.navigator
  Object.defineProperty(window.navigator, 'serviceWorker', {
    value: mockServiceWorker,
    configurable: true,
  });
  
  // Mock the onLine property
  Object.defineProperty(window.navigator, 'onLine', {
    value: true,
    writable: true,
  });
  
  // Mock the IndexedDB
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
  
  // Add to window
  window.indexedDB = mockIndexedDB();
  
  // Mock the IDBFactory
  window.indexedDB.deleteDatabase = jest.fn(() => ({
    onsuccess: jest.fn(),
    onerror: jest.fn(),
    onblocked: jest.fn(),
  }));
  
  // Mock the IDBTransaction
  window.IDBTransaction = {
    READ_ONLY: 'readonly',
    READ_WRITE: 'readwrite',
  };
  
  // Mock the IDBKeyRange
  window.IDBKeyRange = {
    bound: jest.fn(),
    lowerBound: jest.fn(),
    upperBound: jest.fn(),
    only: jest.fn(),
  };
}

// Mock the fetch API
global.fetch = jest.fn(() =>
  Promise.resolve({
    ok: true,
    json: () => Promise.resolve({}),
    text: () => Promise.resolve(''),
    clone: function() { return this; },
  })
);

// Mock the console methods to keep test output clean
const originalConsole = { ...console };
const consoleMocks = ['log', 'warn', 'error', 'info', 'debug'];

beforeEach(() => {
  consoleMocks.forEach(method => {
    global.console[method] = jest.fn();
  });
});

afterEach(() => {
  // Restore the original console methods
  consoleMocks.forEach(method => {
    global.console[method] = originalConsole[method];
  });
  
  // Clear all mocks
  jest.clearAllMocks();
  
  // Clear local and session storage
  localStorage.clear();
  sessionStorage.clear();
});
