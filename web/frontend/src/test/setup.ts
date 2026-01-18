import '@testing-library/jest-dom'

// Mock fetch globally
global.fetch = vi.fn()

// Mock WebSocket
global.WebSocket = vi.fn().mockImplementation(() => ({
  close: vi.fn(),
  send: vi.fn(),
  addEventListener: vi.fn(),
  removeEventListener: vi.fn(),
  readyState: 1,
})) as unknown as typeof WebSocket
