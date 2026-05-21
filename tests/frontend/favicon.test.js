const fs = require('fs');
const path = require('path');
const util = require('util');
global.TextEncoder = util.TextEncoder;
global.TextDecoder = util.TextDecoder;
const { JSDOM } = require('jsdom');

describe('Favicon Integration Tests', () => {
  const htmlFiles = ['index.html', 'admin.html', 'form.html', 'success.html'];
  const rootDir = path.resolve(__dirname, '../../');



  htmlFiles.forEach(file => {
    describe(`${file} Favicon`, () => {
      let dom;
      let document;

      beforeAll(() => {
        const filePath = path.join(rootDir, file);
        const html = fs.readFileSync(filePath, 'utf8');
        dom = new JSDOM(html);
        document = dom.window.document;
      });

      test('should have a link tag with rel="icon"', () => {
        const iconLink = document.querySelector('link[rel="icon"]');
        expect(iconLink).not.toBeNull();
      });

      test('icon link should point to a base64 inline data URI', () => {
        const iconLink = document.querySelector('link[rel="icon"]');
        expect(iconLink.getAttribute('href').startsWith('data:image/png;base64,')).toBe(true);
      });

      test('icon link should have the correct MIME type (image/png)', () => {
        const iconLink = document.querySelector('link[rel="icon"]');
        expect(iconLink.getAttribute('type')).toBe('image/png');
      });
    });
  });
});
