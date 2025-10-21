module.exports = {
  // Test environment
  testEnvironment: 'jsdom',
  
  // File patterns to test
  testMatch: [
    '**/pos/static/pos/js/__tests__/**/*.test.js',
  ],
  
  // Module file extensions
  moduleFileExtensions: ['js', 'json', 'jsx', 'node'],
  
  // Transform configuration
  transform: {
    '^.+\\.js$': 'babel-jest',
  },
  
  // Mock file and module paths
  moduleNameMapper: {
    '^@/(.*)$': '<rootDir>/$1',
    '^\\.(css|less|scss|sass)$': 'identity-obj-proxy',
  },
  
  // Setup files
  setupFilesAfterEnv: ['<rootDir>/jest.setup.js'],
  
  // Coverage configuration
  collectCoverage: true,
  collectCoverageFrom: [
    'pos/static/pos/js/**/*.js',
    '!**/node_modules/**',
    '!**/vendor/**',
  ],
  coverageReporters: ['text', 'lcov'],
  
  // Test timeout
  testTimeout: 10000,
};
