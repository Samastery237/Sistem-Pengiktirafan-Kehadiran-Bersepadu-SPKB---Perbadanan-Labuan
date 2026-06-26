/**
 * Records Page Object Model — attendance records table, CRUD, and edit modal.
 */
const { expect } = require('@playwright/test');
const BasePage = require('./BasePage');

class RecordsPage extends BasePage {
  constructor(page) {
    super(page);
  }

  async navigate() {
    await this.goto('/admin.html');
  }

  // --- Table Operations ---
  async getTableRowCount() {
    return this.page.locator('#attendance-tbody tr').count();
  }

  async isTableEmpty() {
    return this.page.locator('#empty-state').isVisible();
  }

  async isEmptyStateVisible() {
    return this.page.locator('#empty-state').isVisible();
  }

  async getFirstRowText() {
    const firstRow = this.page.locator('#attendance-tbody tr').first();
    return firstRow.textContent();
  }

  // --- Selecting Records ---
  async selectAll() {
    await this.page.click('#check-all');
    await this.page.waitForTimeout(300);
  }

  async selectRow(index = 0) {
    const checkboxes = this.page.locator('.row-check');
    await checkboxes.nth(index).check();
    await this.page.waitForTimeout(300);
  }

  async getSelectedCount() {
    const text = await this.page.locator('#bulk-count').textContent();
    const match = text.match(/(\d+)/);
    return match ? parseInt(match[1], 10) : 0;
  }

  // --- Deleting Records ---
  async deleteAllSelected() {
    await this.selectAll();
    await this.page.waitForTimeout(300);
    await this.page.click('#btn-bulk-delete');
    await this.page.locator('#generic-confirm-modal').waitFor({ state: 'visible' });
    await this.confirmModal();
    await this.page.waitForTimeout(500);
  }

  async deleteRow(index = 0) {
    const deleteBtn = this.page.locator('#attendance-tbody tr').nth(index).locator('button[title="Padam"]');
    await deleteBtn.click();
    await this.page.locator('#generic-confirm-modal').waitFor({ state: 'visible' });
    await this.confirmModal();
    await this.page.waitForTimeout(500);
  }

  // --- Editing Records ---
  async editRow(index = 0) {
    const editBtn = this.page.locator('#attendance-tbody tr').nth(index).locator('button[title="Kemaskini"]');
    await editBtn.click();
    await this.page.locator('#edit-modal').waitFor({ state: 'visible' });
  }

  async fillEditFullName(name) {
    await this.page.fill('#edit-fullname', name);
  }

  async fillEditIC(ic) {
    await this.page.fill('#edit-ic', ic);
  }

  async fillEditPhone(phone) {
    await this.page.fill('#edit-phone', phone);
  }

  async fillEditEmail(email) {
    await this.page.fill('#edit-email', email);
  }

  async submitEdit() {
    await this.page.locator('#edit-modal .btn-primary').click();
    await this.page.waitForTimeout(500);
  }

  // --- Confirm/Cancel Modal ---
  async confirmModal() {
    await this.page.click('#btn-confirm-action');
    await this.page.waitForTimeout(500);
  }

  async cancelModal() {
    await this.page.click('#btn-confirm-cancel');
    await this.page.waitForTimeout(500);
  }

  async cancelEditModal() {
    await this.page.locator('#edit-modal .btn-ghost').click();
    await this.page.waitForTimeout(500);
  }

  // --- Search & Filter ---
  async search(query) {
    await this.page.fill('#search-input', query);
    await this.page.waitForTimeout(500);
  }

  async getVisibleRowsAfterSearch() {
    await this.page.waitForTimeout(300);
    return this.page.locator('#attendance-tbody tr').count();
  }
}

module.exports = RecordsPage;
