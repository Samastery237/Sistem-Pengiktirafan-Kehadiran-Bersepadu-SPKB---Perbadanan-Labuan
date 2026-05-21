// tests/frontend/admin.test.js
const fs = require('fs');
const path = require('path');

describe('Admin Panel Frontend Logic', () => {
  beforeAll(() => {
    // Set up a basic DOM structure that admin.js expects
    document.body.innerHTML = `
      <div id="login-overlay"></div>
      <input type="text" id="admin-username" value="Administrator" />
      <input type="password" id="admin-password" value="admin123" />
      <div id="login-error"></div>
      <div id="admin-app"></div>
      <div id="logout-btn"></div>
    `;

    // Load admin.js into the jsdom environment
    const jsPath = path.resolve(__dirname, '../../js/admin.js');
    const jsCode = fs.readFileSync(jsPath, 'utf8');
    
    // Evaluate the code in the context of jsdom
    const scriptEl = document.createElement('script');
    scriptEl.textContent = jsCode;
    document.body.appendChild(scriptEl);
  });

  beforeEach(() => {
    // Reset specific DOM elements if needed, but keep the script intact
    document.getElementById('login-error').textContent = '';
  });

  test('Mock test to ensure Jest environment is working', () => {
    expect(true).toBe(true);
  });
  
  test('DOM should contain the login overlay', () => {
    const overlay = document.getElementById('login-overlay');
    expect(overlay).not.toBeNull();
  });

  // TDD Demonstration: Red Phase
  // We write a test for a function that doesn't exist yet, or doesn't have the new logic.
  test('isValidPassword should require at least 6 characters and 1 number', () => {
    // These should fail
    expect(window.isValidPassword('short')).toBe(false); // < 6 chars
    expect(window.isValidPassword('onlyletters')).toBe(false); // no numbers
    
    // These should pass
    expect(window.isValidPassword('admin123')).toBe(true);
    expect(window.isValidPassword('password1')).toBe(true);
  });

  describe('Utility Functions', () => {
    test('esc() should escape HTML characters', () => {
      // Test basic escaping
      const escaped = window.esc('<script>alert("xss")</script>');
      expect(escaped).toBe('&lt;script&gt;alert("xss")&lt;/script&gt;');
      
      // Test null/undefined handling
      expect(window.esc(null)).toBe('');
      expect(window.esc(undefined)).toBe('');
      
      // Test safe string
      expect(window.esc('Safe string')).toBe('Safe string');
    });
  });

  describe('Settings Management', () => {
    test('getSettings() should return expected default settings when localStorage is empty', () => {
      localStorage.clear();
      const settings = window.getSettings();
      
      expect(settings).toBeDefined();
      expect(settings.nameFontSize).toBe(42);
      expect(settings.showIC).toBe(true);
      expect(settings.certDelayMinutes).toBe(0);
      expect(settings.fontFamily).toBe('Palatino, serif');
    });

    test('getSettings() should return saved settings from localStorage', () => {
      const mockSettings = { nameFontSize: 50, showIC: false, certDelayMinutes: 5 };
      localStorage.setItem('cert_settings', JSON.stringify(mockSettings));
      
      const settings = window.getSettings();
      expect(settings.nameFontSize).toBe(50);
      expect(settings.showIC).toBe(false);
      expect(settings.certDelayMinutes).toBe(5);
      
      // Check that fallbacks still work for missing keys
      expect(settings.fontFamily).toBe('Palatino, serif');
    });
  });

  describe('Participant Management (TDD)', () => {
    test('openEditModal() should populate the edit form correctly', () => {
      // Mock global records data by evaluating a script in jsdom
      const injectScript = document.createElement('script');
      injectScript.textContent = `
        cachedRecords = [
          { id: '123', fullname: 'John Doe', ic_number: '111', phone: '012', email: 'j@d.com', organization: 'Org A' }
        ];
      `;
      document.body.appendChild(injectScript);
      
      // Inject the modal HTML expected by the test
      document.body.innerHTML += `
        <div id="edit-modal" style="display:none;"></div>
        <input id="edit-id" />
        <input id="edit-fullname" />
        <input id="edit-ic" />
        <input id="edit-phone" />
        <input id="edit-email" />
        <input id="edit-org" />
      `;

      // Should throw or fail until implemented
      expect(typeof window.openEditModal).toBe('function');
      
      window.openEditModal('123');
      expect(document.getElementById('edit-id').value).toBe('123');
      expect(document.getElementById('edit-fullname').value).toBe('John Doe');
      expect(document.getElementById('edit-modal').style.display).toBe('flex');
    });
  });
});
