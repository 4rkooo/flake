import { defineConfig, devices } from '@playwright/test';

// Machines without libnss3/libasound2 for Chromium (WSL without sudo): extract the .deb files and
// point PW_CHROMIUM_LD_LIBRARY_PATH at the lib directory; see README "Visual demo".
const libs = process.env.PW_CHROMIUM_LD_LIBRARY_PATH;
const env: Record<string, string> = {};
for (const [k, v] of Object.entries(process.env)) if (typeof v === 'string') env[k] = v;
if (libs) env.LD_LIBRARY_PATH = libs;

export default defineConfig({
  testDir: './e2e',
  timeout: 180_000,
  expect: { timeout: 30_000 },
  workers: 1,               // one shared fake server; tests reset it themselves
  retries: 0,
  reporter: [['list']],
  use: {
    baseURL: 'http://127.0.0.1:8765',
    trace: 'retain-on-failure',
    launchOptions: libs ? { env } : {},
  },
  webServer: {
    command: 'uv run flake-demo --fake --port 8765 --pace 0',
    cwd: '..',
    url: 'http://127.0.0.1:8765/api/state',
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
    stdout: 'pipe',
    stderr: 'pipe',
  },
  projects: [
    { name: 'desktop', use: { ...devices['Desktop Chrome'], viewport: { width: 1440, height: 900 } } },
    { name: 'narrow', use: { ...devices['Pixel 7'] } },
  ],
});
