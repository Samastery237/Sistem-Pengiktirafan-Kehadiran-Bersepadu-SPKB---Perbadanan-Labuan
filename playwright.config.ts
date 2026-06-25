import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './tests',
  baseURL: 'http://127.0.0.1:8000',
  timeout: 30000,
  retries: 2,
  workers: 1,
  reporter: [['html'], ['list']],
  use: {
    headless: true,
    screenshot: 'only-on-failure',
    trace: 'on-first-retry',
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
  ],
  webServer: {
    command: 'cd backend && python manage.py runserver 0.0.0.0:8000',
    url: 'http://127.0.0.1:8000/api/attendance/health/',
    reuseExistingServer: !process.env.CI,
    timeout: 60000,
  },
});
