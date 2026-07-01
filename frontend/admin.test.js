/**
 * @jest-environment jsdom
 */

const { getCookie, api, startLoginCountdown } = require('./js/admin.js');

function mockFetchResponse(overrides = {}) {
  return {
    ok: true,
    status: 200,
    headers: { get: () => 'application/json' },
    json: () => Promise.resolve({ status: 'success' }),
    ...overrides,
  };
}

global.fetch = jest.fn();

const localStorageMock = (() => {
  let store = {};
  return {
    getItem: jest.fn((key) => store[key] || null),
    setItem: jest.fn((key, value) => { store[key] = value; }),
    removeItem: jest.fn((key) => { delete store[key]; }),
    clear: jest.fn(() => { store = {}; }),
  };
})();
Object.defineProperty(global, 'localStorage', { value: localStorageMock });

const sessionStorageMock = (() => {
  let store = {};
  return {
    getItem: jest.fn((key) => store[key] || null),
    setItem: jest.fn((key, value) => { store[key] = value; }),
    removeItem: jest.fn((key) => { delete store[key]; }),
    clear: jest.fn(() => { store = {}; }),
  };
})();
Object.defineProperty(global, 'sessionStorage', { value: sessionStorageMock });

beforeEach(() => {
  document.body.innerHTML = `
    <div id="login-overlay" style="display:none"></div>
    <div id="admin-app" style="display:none"></div>
    <div id="login-error"></div>
    <input type="text" id="admin-username" />
    <input type="password" id="admin-password" />
    <button type="submit" id="login-btn">Log Masuk</button>
    <span id="submit-text">Hantar</span>
    <span id="submit-spinner" style="display:none"></span>
    <div id="admin-content"></div>
    <div id="admin-dropdown-menu" style="display:none"></div>
    <div id="toast"></div>
    <form id="login-form"></form>
    <button id="toggle-password-btn"></button>
    <div id="records-table-wrap"></div>
    <div id="pagination-controls"></div>
    <select id="filter-folder"></select>
    <input id="filter-search" />
    <button id="filter-search-btn"></button>
    <button id="filter-clear-btn"></button>
    <div id="stats-cards"></div>
    <div id="cert-grid"></div>
    <canvas id="stats-chart"></canvas>
    <nav class="navbar"></nav>
  `;
  jest.clearAllMocks();
  localStorageMock.clear();
  sessionStorageMock.clear();
  global.window.location = { href: '', protocol: 'http:', hostname: 'localhost' };
});

describe('getCookie', () => {
  test('returns null when cookie does not exist', () => {
    Object.defineProperty(global.document, 'cookie', {
      get: () => 'other=value',
      configurable: true,
    });
    expect(getCookie('nonexistent')).toBeNull();
  });

  test('returns cookie value when found', () => {
    Object.defineProperty(global.document, 'cookie', {
      get: () => 'csrftoken=abc123; sessionid=xyz',
      configurable: true,
    });
    expect(getCookie('csrftoken')).toBe('abc123');
  });

  test('handles empty cookie string', () => {
    Object.defineProperty(global.document, 'cookie', {
      get: () => '',
      configurable: true,
    });
    expect(getCookie('csrftoken')).toBeNull();
  });

  test('decodes URI-encoded values', () => {
    Object.defineProperty(global.document, 'cookie', {
      get: () => 'token=hello%20world',
      configurable: true,
    });
    expect(getCookie('token')).toBe('hello world');
  });
});

describe('api', () => {
  const API_BASE = '/api/attendance/';

  test('GET request includes credentials', async () => {
    fetch.mockResolvedValueOnce(mockFetchResponse());
    const result = await api('auth/check/', { method: 'GET' });
    expect(fetch).toHaveBeenCalledWith(
      API_BASE + 'auth/check/',
      expect.objectContaining({ method: 'GET', credentials: 'include' })
    );
    expect(result).toEqual({ status: 'success' });
  });

  test('includes CSRF token from cookie', async () => {
    Object.defineProperty(global.document, 'cookie', {
      get: () => 'csrftoken=cookie-csrf-token',
      configurable: true,
    });
    fetch.mockResolvedValueOnce(mockFetchResponse());
    await api('auth/login/', { method: 'POST' });
    expect(fetch).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({
        headers: expect.objectContaining({ 'X-CSRFToken': 'cookie-csrf-token' }),
      })
    );
  });

  test('includes Content-Type for JSON body', async () => {
    fetch.mockResolvedValueOnce(mockFetchResponse());
    await api('auth/login/', {
      method: 'POST',
      body: JSON.stringify({ username: 'admin' }),
    });
    expect(fetch).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({
        headers: expect.objectContaining({ 'Content-Type': 'application/json' }),
      })
    );
  });

  test('rejects on non-JSON error response', async () => {
    fetch.mockResolvedValueOnce({
      ok: false,
      status: 500,
      headers: { get: () => 'text/html' },
      json: () => Promise.reject(new Error('Invalid JSON')),
      text: () => Promise.resolve('<html>Server Error</html>'),
    });
    await expect(api('auth/check/', { method: 'GET' })).rejects.toBe('HTTP 500');
  });

  test('rejects on 403 response as Unauthorized', async () => {
    fetch.mockResolvedValueOnce({
      ok: false,
      status: 403,
      headers: { get: () => 'application/json' },
      json: () => Promise.resolve({ status: 'error', message: 'Forbidden' }),
    });
    await expect(api('auth/check/', { method: 'GET' })).rejects.toBe('Unauthorized');
  });

  test('rejects on non-auth 500 with JSON error', async () => {
    fetch.mockResolvedValueOnce({
      ok: false,
      status: 500,
      headers: { get: () => 'application/json' },
      json: () => Promise.resolve({ message: 'Server error' }),
    });
    await expect(api('auth/check/', { method: 'GET' })).rejects.toBe('Server error');
  });
});

describe('startLoginCountdown', () => {
  beforeEach(() => { jest.useFakeTimers(); });
  afterEach(() => { jest.useRealTimers(); });

  test('disables button and shows countdown', () => {
    const btn = document.getElementById('login-btn');
    btn.disabled = false;
    startLoginCountdown(60);
    expect(btn.disabled).toBe(true);
    expect(btn.textContent).toContain('60s');
  });

  test('re-enables button after countdown ends', () => {
    const btn = document.getElementById('login-btn');
    btn.innerHTML = 'Log Masuk';
    btn.disabled = true;
    startLoginCountdown(1);
    jest.advanceTimersByTime(2000);
    expect(btn.disabled).toBe(false);
    expect(btn.textContent).toBe('Log Masuk');
  });
});
