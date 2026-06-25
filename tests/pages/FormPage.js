/**
 * Form Page Object Model — public attendance registration form.
 */
const { expect } = require('@playwright/test');
const BasePage = require('./BasePage');

class FormPage extends BasePage {
  constructor(page) {
    super(page);
  }

  async navigate() {
    await this.goto('/form.html');
  }

  async fillFullName(name) {
    await this.page.fill('#fullname', name);
  }

  async fillIC(ic) {
    await this.page.fill('#ic', ic);
  }

  async fillPhone(phone) {
    await this.page.fill('#phone', phone);
  }

  async fillEmail(email) {
    await this.page.fill('#email', email);
  }

  async selectOrganization(org) {
    await this.page.selectOption('#organization', org);
  }

  async checkTerms() {
    await this.page.check('#terms');
  }

  async uncheckTerms() {
    await this.page.uncheck('#terms');
  }

  async submit() {
    await this.page.click('#submit-btn');
  }

  async fillAndSubmit({ fullname, ic, phone, email, organization = 'Jabatan Hal Ehwal Korporat', terms = true }) {
    if (fullname !== undefined) await this.fillFullName(fullname);
    if (ic !== undefined) await this.fillIC(ic);
    if (phone !== undefined) await this.fillPhone(phone);
    if (email !== undefined) await this.fillEmail(email);
    if (organization !== undefined) await this.selectOrganization(organization);
    if (terms) await this.checkTerms();
    await this.page.waitForTimeout(500);
    await this.submit();
  }

  async getError(fieldName) {
    return this.page.locator(`#error-${fieldName}`).textContent();
  }

  async isErrorVisible(fieldName) {
    return this.page.locator(`#error-${fieldName}`).isVisible();
  }

  async getRandomIC() {
    return '123' + Math.floor(100000000 + Math.random() * 900000000).toString();
  }
}

module.exports = FormPage;
