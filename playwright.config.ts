import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './tests/e2e',
  timeout: 30_000,
  expect: {
    timeout: 8_000,
  },
  use: {
    baseURL: 'http://127.0.0.1:5173',
    trace: 'on-first-retry',
  },
  webServer: [
    {
      command: 'cmd /c "set DATABASE_URL=postgresql+psycopg://workflow_studio:workflow_studio_dev_password@127.0.0.1:5432/workflow_studio_test&& set RUN_JOB_QUEUE_BACKEND=thread&& server\\.venv\\Scripts\\python.exe -m uvicorn server.src.main:app --host 127.0.0.1 --port 8000"',
      url: 'http://127.0.0.1:8000/api/health',
      reuseExistingServer: true,
      timeout: 60_000,
    },
    {
      command: 'npm.cmd run dev -- --host 127.0.0.1 --port 5173',
      url: 'http://127.0.0.1:5173',
      reuseExistingServer: true,
      timeout: 60_000,
    },
  ],
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
})
