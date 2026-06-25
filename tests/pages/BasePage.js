/**
 * Base Page Object Model — common helpers for all pages.
 */
const { expect } = require('@playwright/test');

class BasePage {
  constructor(page) {
    this.page = page;
    this.baseURL = 'http://127.0.0.1:8000';
  }

  async goto(path) {
    await this.page.goto(`${this.baseURL}${path}`);
  }

  async waitForToast(timeout = 5000) {
    const toast = this.page.locator('#toast');
    await toast.waitFor({ state: 'visible', timeout });
    return toast;
  }

  async getToastText() {
    const toast = await this.waitForToast();
    return toast.textContent();
  }

  async toggleTheme() {
    await this.page.click('#theme-toggle-btn');
  }

  async isDarkMode() {
    const html = this.page.locator('html');
    const theme = await html.getAttribute('data-theme');
    return theme !== 'light';
  }

  async isLightMode() {
    const html = this.page.locator('html');
    const theme = await html.getAttribute('data-theme');
    return theme === 'light';
  }

  async clearTheme() {
    await this.page.evaluate(() => localStorage.removeItem('spkb_theme'));
  }
}

module.exports = BasePage;
