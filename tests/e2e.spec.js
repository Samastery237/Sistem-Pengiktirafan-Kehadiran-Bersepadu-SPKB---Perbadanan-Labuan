const { test, expect } = require('@playwright/test');

const BASE_URL = 'http://127.0.0.1:8000';

test.describe('SPKB Frontend E2E Suite', () => {

  test('Index page renders and navigation works', async ({ page }) => {
    await page.goto(`${BASE_URL}/`);
    await expect(page).toHaveTitle(/Perbadanan Labuan/i);
    const btn = page.locator('#cta-register');
    await expect(btn).toBeVisible();
    await btn.click();
    await expect(page).toHaveURL(/.*form.html/);
  });

  test('Public Form submission and Success redirect', async ({ page }) => {
    const randomIC = "123" + Math.floor(100000000 + Math.random() * 900000000).toString();
    
    await page.goto(`${BASE_URL}/form.html`);
    
    await page.fill('#fullname', 'Automated E2E Tester');
    await page.fill('#ic', randomIC);
    await page.fill('#phone', '0198765432');
    await page.selectOption('#organization', 'Jabatan Hal Ehwal Korporat');
    await page.check('#terms');
    
    // Crucial wait for DOM / JS event loop to settle
    await page.waitForTimeout(1000); 
    
    await page.click('#submit-btn');
    
    await page.waitForURL(/.*success.html/, { timeout: 15000 });
    await expect(page.locator('h2')).toContainText(/Kehadiran Berjaya Didaftarkan/i, { timeout: 10000 });
  });

  test('Admin Login and Dashboard', async ({ page }) => {
    await page.goto(`${BASE_URL}/admin.html`);
    
    // Ensure clean state
    await page.goto(`${BASE_URL}/api/attendance/auth/logout/`);
    await page.goto(`${BASE_URL}/admin.html`);
    
    await page.fill('#admin-username', 'admin');
    await page.fill('#admin-password', 'admin123');
    await page.click('#login-btn');
    
    await expect(page.locator('#admin-app')).toHaveClass(/.*visible.*/, { timeout: 10000 });
    await expect(page.locator('#stat-total')).not.toBeEmpty();
  });

});
