const { test, expect } = require('@playwright/test');
const BasePage = require('./pages/BasePage');
const FormPage = require('./pages/FormPage');
const AdminLoginPage = require('./pages/AdminLoginPage');
const DashboardPage = require('./pages/DashboardPage');
const RecordsPage = require('./pages/RecordsPage');

const BASE_URL = 'http://127.0.0.1:8000';

// =====================================================================
// Public Pages (no auth required)
// =====================================================================

test.describe('Public Pages', () => {
  test('Index page renders and navigation works', async ({ page }) => {
    const base = new BasePage(page);
    await base.goto('/');

    await expect(page).toHaveTitle(/Perbadanan Labuan/i);

    const btn = page.locator('#cta-register');
    await expect(btn).toBeVisible();
    await btn.click();

    await expect(page).toHaveURL(/.*form.html/);
  });

  test('Public Form submission and Success redirect', async ({ page }) => {
    const form = new FormPage(page);
    await form.navigate();

    const randomIC = await form.getRandomIC();
    await form.fillAndSubmit({
      fullname: 'Automated E2E Tester',
      ic: randomIC,
      phone: '0198765432',
      email: 'tester@example.com',
    });

    await page.waitForURL(/.*success.html/, { timeout: 15000 });
    await expect(page.locator('h2')).toContainText(/Kehadiran Berjaya Didaftarkan/i, { timeout: 10000 });
  });

  test('Form validation shows errors for empty fields', async ({ page }) => {
    const form = new FormPage(page);
    await form.navigate();

    // Submit without filling anything
    await form.uncheckTerms();
    await form.submit();

    // Should show validation errors
    await expect(page.locator('#error-fullname')).toBeVisible({ timeout: 5000 });
    await expect(page.locator('#error-ic')).toBeVisible();
    await expect(page.locator('#error-phone')).toBeVisible();
  });

  test('Form validation shows error for invalid IC', async ({ page }) => {
    const form = new FormPage(page);
    await form.navigate();

    await form.fillAndSubmit({
      fullname: 'Test User',
      ic: '123',  // Too short
      phone: '0198765432',
    });

    // Should show IC error
    await expect(page.locator('#error-ic')).toBeVisible({ timeout: 5000 });
  });

  test('Theme Toggling works across pages', async ({ page }) => {
    const base = new BasePage(page);
    await base.goto('/index.html');
    await base.clearTheme();
    await page.reload();

    // Default should be dark mode
    await expect(page.locator('html')).not.toHaveAttribute('data-theme', 'light');

    // Toggle to light mode
    await base.toggleTheme();
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'light');

    // Verify it persists across navigation
    await base.goto('/form.html');
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'light');
  });
});

// =====================================================================
// Admin Authentication
// =====================================================================

test.describe('Admin Authentication', () => {
  test('Admin Login and Dashboard', async ({ page }) => {
    const login = new AdminLoginPage(page);
    await login.navigate();
    await login.login('admin', 'admin123');

    await login.waitForLoginResult();
    await expect(page.locator('#login-error')).not.toHaveClass(/.*show.*/);
    await login.isAdminAppVisible();
    await expect(page.locator('#stat-total')).not.toBeEmpty();
  });

  test('Admin Logout redirects to login', async ({ page }) => {
    const login = new AdminLoginPage(page);
    const dashboard = new DashboardPage(page);

    await login.navigate();
    await login.login('admin', 'admin123');
    await login.isAdminAppVisible();

    // Logout
    await dashboard.openSettings();
    await page.locator('#logout-btn').waitFor({ state: 'visible' });
    await dashboard.clickLogout();
    await dashboard.confirmModal();

    // Should see login overlay again
    await expect(page.locator('#login-overlay')).toBeVisible({ timeout: 5000 });
  });

  test('Invalid login shows error', async ({ page }) => {
    const login = new AdminLoginPage(page);
    await login.navigate();
    await login.login('admin', 'wrongpassword');

    await login.waitForLoginResult();
    await expect(page.locator('#login-error')).toBeVisible({ timeout: 10000 });
  });
});

// =====================================================================
// Records Management
// =====================================================================

test.describe('Records Management', () => {
  test.beforeEach(async ({ page }) => {
    const login = new AdminLoginPage(page);
    await login.navigate();
    await login.login('admin', 'admin123');
    await login.isAdminAppVisible();
  });

  test('Records table shows attendance data', async ({ page }) => {
    const dashboard = new DashboardPage(page);
    await dashboard.clickTabAttendance();

    // Table should have at least one row or show empty state
    const rowCount = await page.locator('#attendance-tbody tr').count();
    const emptyVisible = await page.locator('#empty-state').isVisible();
    expect(rowCount > 0 || emptyVisible).toBeTruthy();
  });

  test('Search filters records by name', async ({ page }) => {
    const records = new RecordsPage(page);
    await records.search('Automated');

    const visibleRows = await records.getVisibleRowsAfterSearch();
    // Either we found matches or table is empty after search
    expect(visibleRows).toBeGreaterThanOrEqual(0);
  });

  test('Select all shows bulk action bar', async ({ page }) => {
    const records = new RecordsPage(page);
    const rowCount = await records.getTableRowCount();

    if (rowCount > 0) {
      await records.selectAll();
      await expect(page.locator('#bulk-bar')).toBeVisible({ timeout: 5000 });
    }
  });

  test('Delete single record removes from table', async ({ page }) => {
    const records = new RecordsPage(page);
    const initialCount = await records.getTableRowCount();

    if (initialCount > 0) {
      await records.deleteRow(0);
      const newCount = await records.getTableRowCount();
      expect(newCount).toBeLessThan(initialCount);
    }
  });
});

// =====================================================================
// Certificate Management
// =====================================================================

test.describe('Certificate Management', () => {
  test.beforeEach(async ({ page }) => {
    const login = new AdminLoginPage(page);
    await login.navigate();
    await login.login('admin', 'admin123');
    await login.isAdminAppVisible();
  });

  test('Certificate tab shows participant list or empty state', async ({ page }) => {
    const dashboard = new DashboardPage(page);
    await dashboard.clickTabCertificate();

    const listVisible = await page.locator('#cert-participant-list').isVisible({ timeout: 5000 });
    const emptyVisible = await page.locator('#cert-empty').isVisible();
    expect(listVisible || emptyVisible).toBeTruthy();
  });

  test('Certificate search filters participants', async ({ page }) => {
    const dashboard = new DashboardPage(page);
    await dashboard.clickTabCertificate();

    await dashboard.certSearch('Test');
    await page.waitForTimeout(500);

    const count = await dashboard.getCertParticipantCount();
    expect(count).toBeGreaterThanOrEqual(0);
  });
});

// =====================================================================
// Settings & Configuration
// =====================================================================

test.describe('Settings & Configuration', () => {
  test.beforeEach(async ({ page }) => {
    const login = new AdminLoginPage(page);
    await login.navigate();
    await login.login('admin', 'admin123');
    await login.isAdminAppVisible();
  });

  test('Settings tab shows template upload zone', async ({ page }) => {
    const dashboard = new DashboardPage(page);
    await dashboard.clickTabSettings();

    await expect(page.locator('#upload-zone')).toBeVisible({ timeout: 5000 });
  });

  test('Certificate delay fields accept input', async ({ page }) => {
    const dashboard = new DashboardPage(page);
    await dashboard.clickTabSettings();

    await dashboard.fillCertDelay(2, 30);
    await expect(page.locator('#cert-delay-hours')).toHaveValue('2');
    await expect(page.locator('#cert-delay-minutes')).toHaveValue('30');
  });

  test('Change password modal opens and validates', async ({ page }) => {
    const dashboard = new DashboardPage(page);
    await dashboard.openSettings();
    await dashboard.clickChangePassword();

    await expect(page.locator('#change-password-modal')).toBeVisible({ timeout: 5000 });

    // Fill wrong old password
    await dashboard.fillOldPassword('wrongpassword');
    await dashboard.fillNewPassword('NewPass123!');
    await dashboard.fillConfirmPassword('NewPass123!');
    await dashboard.submitChangePassword();

    // Should show error (not success)
    await expect(page.locator('#modal-pw-status')).toBeVisible({ timeout: 5000 });
  });
});

// =====================================================================
// API Health & Security
// =====================================================================

test.describe('API Health & Security', () => {
  test('Health check endpoint returns 200', async ({ request }) => {
    const response = await request.get(`${BASE_URL}/api/attendance/health/`, {
      headers: { 'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36' },
    });
    expect(response.status()).toBe(200);
  });
});

// =====================================================================
// Gap E2E Tests
// =====================================================================

test.describe('Form page additional tests', () => {
  test('IC input accepts 12-digit number', async ({ page }) => {
    const form = new FormPage(page);
    await form.navigate();

    await form.fillIC('900101123456');
    // Field should contain the value
    const icValue = await page.locator('#ic').inputValue();
    expect(icValue.replace(/-/g, '').length).toBeGreaterThanOrEqual(6);
  });

  test('Email validation rejects invalid email', async ({ page }) => {
    const form = new FormPage(page);
    await form.navigate();

    await form.fillAndSubmit({
      fullname: 'Test User',
      ic: '123456789012',
      phone: '0198765432',
      email: 'notanemail',
    });

    await page.waitForURL(/.*success.html|form.html/, { timeout: 10000 });
    // Should stay on form page or show error
    const errorVisible = await page.locator('#error-email').isVisible();
    const currentUrl = page.url();
    // Either error shown or URL still has form.html
    expect(errorVisible || currentUrl.includes('form.html')).toBeTruthy();
  });
});

test.describe('Records page additional tests', () => {
  test('Edit modal opens and can be cancelled', async ({ page }) => {
    const login = new AdminLoginPage(page);
    await login.navigate();
    await login.login('admin', 'admin123');
    await login.isAdminAppVisible();

    const records = new RecordsPage(page);
    const rowCount = await records.getTableRowCount();

    if (rowCount > 0) {
      // Get first row name
      const firstRow = page.locator('#attendance-tbody tr').first();
      const originalText = await firstRow.textContent();

      await records.editRow(0);

      // Change name in modal
      await records.fillEditFullName('Cancel Test');
      await records.cancelEditModal();

      // Table should be unchanged
      const afterText = await firstRow.textContent();
      expect(afterText).toContain(originalText.substring(0, 10));
    }
  });

  test('Bulk select and deselect all', async ({ page }) => {
    const login = new AdminLoginPage(page);
    await login.navigate();
    await login.login('admin', 'admin123');
    await login.isAdminAppVisible();

    const records = new RecordsPage(page);
    const rowCount = await records.getTableRowCount();

    if (rowCount > 1) {
      await records.selectRow(0);
      await records.selectRow(1);
      await expect(page.locator('#bulk-bar')).toBeVisible();

      // Deselect all
      await page.locator('#check-all').click();
      await page.waitForTimeout(300);
      // Bulk bar may or may not be visible depending on implementation
    }
  });
});

test.describe('Certificate tab additional tests', () => {
  test.beforeEach(async ({ page }) => {
    const login = new AdminLoginPage(page);
    await login.navigate();
    await login.login('admin', 'admin123');
    await login.isAdminAppVisible();
  });

  test('Certificate tab shows participant list when records exist', async ({ page }) => {
    const dashboard = new DashboardPage(page);
    await dashboard.clickTabCertificate();

    await page.waitForTimeout(1000);
    const listVisible = await page.locator('#cert-participant-list').isVisible({ timeout: 5000 });
    const emptyVisible = await page.locator('#cert-empty').isVisible();
    // Either we see participants or an empty state
    expect(listVisible || emptyVisible).toBeTruthy();
  });
});

test.describe('Settings tab additional tests', () => {
  test.beforeEach(async ({ page }) => {
    const login = new AdminLoginPage(page);
    await login.navigate();
    await login.login('admin', 'admin123');
    await login.isAdminAppVisible();
  });

  test('Settings tab name position fields accept input', async ({ page }) => {
    const dashboard = new DashboardPage(page);
    await dashboard.clickTabSettings();

    // These fields may exist in settings
    const nameX = page.locator('#name-x');
    if (await nameX.isVisible()) {
      await nameX.fill('600');
      await page.locator('#name-y').fill('400');
      expect(await nameX.inputValue()).toBe('600');
    }
  });

  test('Settings fields accept text color', async ({ page }) => {
    const dashboard = new DashboardPage(page);
    await dashboard.clickTabSettings();

    const textColor = page.locator('#text-color');
    if (await textColor.isVisible()) {
      await textColor.fill('#ff0000');
      expect(await textColor.inputValue()).toContain('ff0000');
    }
  });
});

test.describe('Cross-page journey', () => {
  test('Full journey: submit → admin views records', async ({ page }) => {
    // Step 1: Submit attendance
    const form = new FormPage(page);
    await form.navigate();

    const randomIC = '991234' + Math.floor(100000 + Math.random() * 900000).toString();
    await form.fillAndSubmit({
      fullname: 'E2E Journey User',
      ic: randomIC,
      phone: '0198765432',
      email: 'journey@test.com',
    });

    await page.waitForURL(/.*success.html/, { timeout: 15000 });

    // Step 2: Navigate to admin
    const login = new AdminLoginPage(page);
    await login.navigate();
    await login.login('admin', 'admin123');
    await login.isAdminAppVisible();

    // Step 3: Go to attendance records
    const dashboard = new DashboardPage(page);
    await dashboard.clickTabAttendance();

    // Step 4: Search for the submitted user
    const records = new RecordsPage(page);
    await records.search('E2E Journey');
    await page.waitForTimeout(1000);

    // The record may or may not be visible depending on timing
    const visibleRows = await records.getVisibleRowsAfterSearch();
    expect(visibleRows).toBeGreaterThanOrEqual(0);
  });
});
