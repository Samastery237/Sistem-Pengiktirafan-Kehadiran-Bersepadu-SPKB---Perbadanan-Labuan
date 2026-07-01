/**
 * Admin Login Page Object Model — login overlay and authentication.
 */
const { expect } = require('@playwright/test');
const BasePage = require('./BasePage');

class AdminLoginPage extends BasePage {
  constructor(page) {
    super(page);
  }

  async navigate() {
    await this.goto('/admin.html');
  }

  async fillUsername(username) {
    await this.page.fill('#admin-username', username);
  }

  async fillPassword(password) {
    await this.page.fill('#admin-password', password);
  }

  async clickLogin() {
    await this.page.click('#login-btn');
  }

  async login(username, password) {
    await this.goto('/admin.html');
    await this.fillUsername(username);
    await this.fillPassword(password);
    await this.clickLogin();
  }

  async isLoginErrorVisible() {
    const error = this.page.locator('#login-error');
    await error.waitFor({ state: 'visible', timeout: 10000 });
    return true;
  }

  async getLoginErrorText() {
    return this.page.locator('#login-error').textContent();
  }

  async isAdminAppVisible() {
    await this.page.locator('#admin-app.visible').waitFor({ state: 'visible', timeout: 10000 });
    return true;
  }

  async waitForLoginResult() {
    await this.page.locator('#admin-app.visible, #login-error.show').first().waitFor({ state: 'visible', timeout: 15000 });
  }
}

module.exports = AdminLoginPage;
