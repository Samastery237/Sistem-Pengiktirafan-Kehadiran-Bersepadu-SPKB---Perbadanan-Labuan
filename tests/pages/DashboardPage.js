/**
 * Dashboard Page Object Model — admin dashboard tabs, stats, and navigation.
 */
const { expect } = require('@playwright/test');
const BasePage = require('./BasePage');

class DashboardPage extends BasePage {
  constructor(page) {
    super(page);
  }

  // --- Tab Navigation ---
  async clickTabAttendance() {
    await this.page.click('#tab-attendance-btn');
  }

  async clickTabCertificate() {
    await this.page.click('#tab-certificate-btn');
  }

  async clickTabSettings() {
    await this.page.click('#tab-settings-btn');
  }

  async clickTabUsers() {
    await this.page.click('#tab-users-btn');
  }

  async isTabVisible(tabName) {
    const tabMap = {
      attendance: '#tab-attendance-btn',
      certificate: '#tab-certificate-btn',
      settings: '#tab-settings-btn',
      users: '#tab-users-btn',
    };
    return this.page.locator(tabMap[tabName]).isVisible();
  }

  // --- Stats ---
  async getStatTotal() {
    const text = await this.page.locator('#stat-total').textContent();
    return parseInt(text.trim(), 10);
  }

  async getStatToday() {
    const text = await this.page.locator('#stat-today').textContent();
    return parseInt(text.trim(), 10);
  }

  async getStatCerts() {
    const text = await this.page.locator('#stat-certs').textContent();
    return parseInt(text.trim(), 10);
  }

  async statsVisible() {
    return this.page.locator('#stats-grid').isVisible();
  }

  // --- Search ---
  async search(query) {
    await this.page.fill('#search-input', query);
    await this.page.waitForTimeout(500); // debounce
  }

  // --- Bulk Actions ---
  async getBulkCount() {
    const text = await this.page.locator('#bulk-count').textContent();
    const match = text.match(/(\d+)/);
    return match ? parseInt(match[1], 10) : 0;
  }

  async clickBulkDelete() {
    await this.page.click('#btn-bulk-delete');
  }

  async clickBulkCert() {
    await this.page.click('#btn-bulk-cert');
  }

  // --- Export ---
  async clickExport() {
    await this.page.click('#btn-export');
  }

  // --- Certificate Tab ---
  async certSearch(query) {
    await this.page.fill('#cert-search', query);
    await this.page.waitForTimeout(500);
  }

  async getCertParticipantCount() {
    const list = this.page.locator('#cert-participant-list .cert-participant-item');
    return list.count();
  }

  async clickGenAll() {
    await this.page.click('#btn-gen-all');
  }

  // --- Settings Tab ---
  async fillCertDelay(hours, minutes) {
    await this.page.fill('#cert-delay-hours', hours.toString());
    await this.page.fill('#cert-delay-minutes', minutes.toString());
  }

  async fillNamePosition(x, y, size) {
    await this.page.fill('#name-x', x.toString());
    await this.page.fill('#name-y', y.toString());
  }

  // --- Users Tab ---
  async getUserRowCount() {
    return this.page.locator('#users-tbody tr').count();
  }

  // --- Folder Management ---
  async selectDepartment(deptName) {
    await this.page.selectOption('#department-selector', deptName);
    await this.page.waitForTimeout(300);
  }

  async selectFolder(folderName) {
    await this.page.selectOption('#folder-selector', folderName);
    await this.page.waitForTimeout(300);
  }

  async clickAddFolder() {
    await this.page.click('#btn-add-folder');
  }

  async clickDeleteFolder() {
    await this.page.click('#btn-del-folder');
  }

  // --- Settings Dropdown ---
  async openSettings() {
    await this.page.click('#admin-settings-btn');
  }

  async clickChangePassword() {
    await this.page.click('#btn-open-cp');
  }

  async clickLogout() {
    await this.page.click('#logout-btn');
  }

  // --- Change Password Modal ---
  async fillOldPassword(pw) {
    await this.page.fill('#modal-old-password', pw);
  }

  async fillNewPassword(pw) {
    await this.page.fill('#modal-new-password', pw);
  }

  async fillConfirmPassword(pw) {
    await this.page.fill('#modal-confirm-password', pw);
  }

  async submitChangePassword() {
    await this.page.click('#change-password-modal .btn-primary');
  }

  async getPasswordStatus() {
    return this.page.locator('#modal-pw-status').textContent();
  }

  // --- Generic Modal ---
  async confirmModal() {
    await this.page.click('#btn-confirm-action');
  }

  async cancelModal() {
    await this.page.click('#btn-confirm-cancel');
  }

  async fillPromptInput(value) {
    await this.page.locator('#prompt-modal-input').fill(value);
  }

  async submitPrompt() {
    await this.page.click('#btn-prompt-action');
  }
}

module.exports = DashboardPage;
