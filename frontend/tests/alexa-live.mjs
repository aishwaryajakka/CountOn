// Opt-in only. Creates one expectation via MCP and deletes only its returned ID.
import { chromium, expect } from '@playwright/test';
import { mkdir } from 'node:fs/promises';
import { randomUUID } from 'node:crypto';

const site = process.env.COUNTON_ALEXA_BASE_URL;
const handoff = process.env.COUNTON_E2E_HANDOFF_URL ?? site;
const api = process.env.COUNTON_E2E_API_BASE_URL;
const email = process.env.COUNTON_E2E_EMAIL;
const password = process.env.COUNTON_E2E_PASSWORD;
if (!site || !api || !email || !password) throw new Error('Explicit test URL, API URL, email and password are required.');
const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
const claim = "I'm counting on my grocery bill staying under $120 this week";
const taggedClaim = `${claim} [CountOn Alexa acceptance ${randomUUID()}]`;
let captureId; let token; let monitoring = false; let directApiRequests = 0;
page.on('request', request => { if (monitoring && request.url().startsWith(api + '/api/v1/')) directApiRequests++; });
page.on('response', async response => {
  if (!response.url().endsWith('/api/mcp')) return;
  try {
    const body = await response.json();
    if (body.meta?.tool === 'capture_expectation' && body.result?.structuredContent?.id) captureId = body.result.structuredContent.id;
  } catch { /* No diagnostics containing response data. */ }
});
async function login(origin) {
  await page.goto(origin + '/login');
  await page.getByLabel('Email address').fill(email);
  await page.getByLabel('Password', { exact: true }).fill(password);
  await page.getByRole('button', { name: 'Sign in to CountOn' }).click();
  await page.waitForURL('**/dashboard');
}
// Tag only the test write at the browser boundary; the product parser is unchanged.
await page.route('**/api/mcp', async route => {
  const request = route.request();
  const body = request.postDataJSON();
  if (body?.action === 'call_tool' && body.tool === 'capture_expectation') {
    body.arguments.request.claim = taggedClaim;
    await route.continue({ postData: JSON.stringify(body) });
  } else await route.continue();
});
try {
  await page.goto(site + '/alexa'); await page.waitForURL('**/login');
  await login(site);
  token = await page.evaluate(() => {
    const key = Object.keys(localStorage).find(key => /^sb-.*-auth-token$/.test(key));
    return key ? JSON.parse(localStorage.getItem(key)).access_token : null;
  });
  if (!token) throw new Error('Test session unavailable');
  await page.goto(site + '/alexa'); monitoring = true;
  await expect(page.getByText('Connected to CountOn MCP', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'What am I counting on?' }).click();
  await expect(page.getByText('MCP → list_expectations', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Tell me about my electricity bill' }).click();
  await expect(page.getByText('MCP → get_expectation', { exact: true })).toBeVisible();
  await page.getByText('MCP → get_expectation', { exact: true }).click();
  await mkdir('test-results/alexa', { recursive: true });
  await page.screenshot({ path: 'test-results/alexa/desktop.png', fullPage: true });
  await page.getByRole('button', { name: claim }).click();
  await expect(page.getByText('Saved to CountOn', { exact: true })).toBeVisible();
  await expect(page.getByText('MCP → capture_expectation', { exact: true })).toBeVisible();
  const href = await page.getByRole('link', { name: 'View in CountOn' }).getAttribute('href');
  const id = href?.split('/').at(-1);
  if (!id || id !== captureId || !/^[0-9a-f-]{36}$/i.test(id)) throw new Error('Capture handoff verification failed');
  if (directApiRequests) throw new Error('Simulator made a direct FastAPI request');
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByRole('button', { name: 'Send message' })).toBeVisible();
  if (await page.evaluate(() => document.documentElement.scrollWidth > innerWidth)) throw new Error('Mobile horizontal overflow');
  await page.screenshot({ path: 'test-results/alexa/mobile.png', fullPage: true });
  monitoring = false;
  // A separate production handoff origin supports testing local /alexa against
  // remote MCP without adding HTTP localhost to production API CORS.
  if (handoff !== site) await login(handoff);
  await page.goto(handoff + href);
  await expect(page.locator('.claim')).toContainText(taggedClaim);
  await page.reload(); await expect(page.locator('.claim')).toContainText(taggedClaim);
  const persisted = await fetch(api + '/api/v1/expectations/' + id, { headers: { Authorization: `Bearer ${token}` } });
  if (persisted.status !== 200) throw new Error('API persistence cross-check failed');
  const stored = await persisted.json();
  if (stored.claim !== taggedClaim || stored.target_value !== 120 || stored.comparison !== 'less_than') throw new Error('Stored capture contract mismatch');
  console.log('PASS login, real discovery, list, list/get detail, capture, handoff, refresh, persistence, mobile layout and MCP-only browser path');
} catch {
  process.exitCode = 1;
  console.error('Alexa live acceptance failed; private records and credentials omitted.');
} finally {
  if (captureId && token && /^[0-9a-f-]{36}$/i.test(captureId)) {
    try {
      const verify = await fetch(api + '/api/v1/expectations/' + captureId, { headers: { Authorization: `Bearer ${token}` } });
      if (verify.status !== 200 || (await verify.json()).claim !== taggedClaim) throw new Error();
      const cleanup = await fetch(api + '/api/v1/expectations/' + captureId, { method: 'DELETE', headers: { Authorization: `Bearer ${token}` } });
      if (cleanup.status !== 204) throw new Error();
      const absent = await fetch(api + '/api/v1/expectations/' + captureId, { headers: { Authorization: `Bearer ${token}` } });
      if (absent.status !== 404) throw new Error();
      console.log('PASS cleanup of only the MCP-created test expectation');
    } catch { process.exitCode = 1; console.error('Test expectation cleanup failed; inspect the dedicated test account.'); }
  }
  await browser.close();
}
