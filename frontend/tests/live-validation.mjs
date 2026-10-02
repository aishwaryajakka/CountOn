// Opt-in browser verification. Supply credentials via process environment only.
// No traces, storage exports, headers, tokens or passwords are written to disk.
import { chromium, expect as baseExpect } from '@playwright/test';
import { mkdir } from 'node:fs/promises';

const base = process.env.COUNTON_E2E_BASE_URL ?? 'http://localhost:3000';
const email = process.env.COUNTON_E2E_EMAIL;
const password = process.env.COUNTON_E2E_PASSWORD;
const empty = process.env.COUNTON_E2E_EXPECT_EMPTY === '1';
const authOnly = process.env.COUNTON_E2E_AUTH_ONLY === '1';
const apiOverride = process.env.COUNTON_E2E_API_BASE_URL;
const output = process.env.COUNTON_E2E_OUTPUT ?? 'test-results/live';
const expect = baseExpect.configure({ timeout: 30000 });
if (!email || !password) { console.error('Set COUNTON_E2E_EMAIL and COUNTON_E2E_PASSWORD in the process environment.'); process.exit(1); }
await mkdir(output, { recursive: true });
const browser = await chromium.launch();
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
const page = await context.newPage();
const pageErrors = [];
const failedApiResponses = [];
let phase = 'normal';
page.on('response', response => {
  const url = new URL(response.url());
  if (url.pathname.startsWith('/api/v1/') && response.status() >= 400) failedApiResponses.push(`${phase}: ${response.status()} ${url.pathname} ${response.headers()['x-counton-test'] ?? 'real response'}`);
  if (url.pathname.startsWith('/api/v1/') && response.status() === 401 && !response.headers()['x-counton-test']) {
    // Diagnose claims locally without emitting the token or identity.
    const token = response.request().headers().authorization?.replace(/^Bearer /, '');
    if (token) {
      try {
        const claims = JSON.parse(Buffer.from(token.split('.')[1], 'base64url').toString());
        const now = Math.floor(Date.now() / 1000);
        console.error('Rejected JWT timing:', JSON.stringify({ phase, issuedInFuture: claims.iat > now, issuedSecondsAgo: now - claims.iat, expiresInSeconds: claims.exp - now, authenticatedRole: claims.role === 'authenticated', authenticatedAudience: claims.aud === 'authenticated' }));
      } catch { console.error('Rejected JWT could not be inspected'); }
    }
  }
});
page.on('pageerror', () => pageErrors.push('Browser JavaScript error'));
let normalConsoleErrors = 0;
let checkingNormalConsole = true;
page.on('console', message => { if (checkingNormalConsole && message.type() === 'error') normalConsoleErrors++; });
// Keep the rapid multi-route audit below FastAPI's existing request budget.
// This is test pacing, not an application retry or a rate-limit bypass.
let nextApiRequest = 0;
await context.route('http://localhost:8000/api/v1/**', async route => {
  const now = Date.now(); const delay = Math.max(0, nextApiRequest - now);
  nextApiRequest = Math.max(now, nextApiRequest) + 300;
  if (delay) await new Promise(resolve => setTimeout(resolve, delay));
  await route.continue(apiOverride ? { url: route.request().url().replace('http://localhost:8000', apiOverride) } : undefined);
});
let createdId;
let completed = false;
const protectedRoutes = ['/dashboard', '/expectations', '/expectations/new', '/expectations/00000000-0000-4000-8000-000000000000', '/integrations', '/notifications', '/activity', '/settings'];
async function signIn() {
  await page.getByLabel('Email address').fill(email);
  await page.getByLabel('Password', { exact: true }).fill(password);
  await page.getByRole('button', { name: 'Sign in to CountOn' }).click();
  await expect(page).toHaveURL(/\/dashboard$/);
  await expect(page.getByRole('button', { name: 'Sign out', exact: true })).toBeVisible();
  await expect(page.locator('[role="status"]')).toHaveCount(0);
  if (!empty) await expect(page.getByText('$162.00', { exact: true })).toBeVisible();
}
try {
  for (const route of protectedRoutes) {
    await page.goto(`${base}${route}`);
    await expect(page).toHaveURL(/\/login$/);
  }
  await expect(page.getByRole('heading', { name: 'Welcome back' })).toBeVisible();
  await page.screenshot({ path: `${output}/login-desktop.png`, fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: `${output}/login-mobile.png`, fullPage: true });
  expect(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1)).toBe(false);
  await page.setViewportSize({ width: 1440, height: 1000 });
  await signIn();
  await expect(page.getByRole('heading', { name: /Welcome back/ })).toBeVisible();
  await page.reload();
  await expect(page.getByRole('heading', { name: /Welcome back/ })).toBeVisible();
  if (empty) {
    await expect(page.getByRole('heading', { name: 'Nothing being monitored yet.' })).toBeVisible();
    for (const [route, title] of [['integrations', 'No connected accounts yet.'], ['notifications', 'Nothing needs your attention.']]) {
      await page.goto(`${base}/${route}`); await expect(page.getByRole('heading', { name: title })).toBeVisible();
    }
    console.log('PASS authenticated empty dashboard, connections, notifications, reload and direct navigation');
  } else if (!authOnly) {
    await expect(page.getByText('$162.00', { exact: true })).toBeVisible({ timeout: 30000 });
    await expect(page.getByText('Less than $142.10', { exact: true })).toBeVisible();
    await page.goto(`${base}/expectations`);
    await expect(page.getByRole('heading', { name: 'Expectations', exact: true })).toBeVisible();
    await page.goBack(); await expect(page).toHaveURL(/\/dashboard$/);
    await page.goForward(); await expect(page).toHaveURL(/\/expectations$/);
    await page.goto(`${base}/dashboard`);
    await page.getByRole('link', { name: 'See why' }).click();
    await expect(page.getByRole('heading', { name: 'Electricity bill', exact: true })).toBeVisible();
    await expect(page).toHaveURL(/\/expectations\/[0-9a-f-]{36}$/);
    const detailUrl = page.url();
    await expect(page.getByText('-18%', { exact: true })).toBeVisible();
    await expect(page.getByText('22%', { exact: true })).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Timeline', exact: true })).toBeVisible();
    await page.screenshot({ path: `${output}/detail-desktop.png`, fullPage: true });
    await page.goto(`${base}/integrations`);
    await expect(page.getByText('Demo connection', { exact: true })).toHaveCount(6);
    await page.getByRole('button', { name: '+ Connect account', exact: true }).click();
    await expect(page.getByRole('dialog')).toBeVisible();
    await page.keyboard.press('Escape'); await expect(page.getByRole('dialog')).toHaveCount(0);
    await page.goto(`${base}/notifications`);
    await expect(page.getByRole('link', { name: 'View expectation' })).toHaveCount(1);
    await expect(page.getByRole('heading', { name: 'Your electricity bill was higher than expected' })).toBeVisible();
    const sizes = process.env.COUNTON_E2E_QUICK === '1' ? [[1440,1000,'desktop']] : [[1440,1000,'desktop'], [1280,900,'wide-laptop'], [1024,900,'laptop'], [768,1024,'tablet'], [390,844,'mobile']];
    for (const [width, height, label] of sizes) {
      await page.setViewportSize({ width, height });
      for (const route of ['/dashboard','/expectations',detailUrl.replace(base,''),'/integrations','/notifications','/expectations/new','/activity','/settings']) {
        await page.goto(`${base}${route}`);
        await expect(page.locator('h1')).toBeVisible();
        await expect(page.locator('[role="status"]')).toHaveCount(0, { timeout: 30000 });
        if (width === 1440) { await page.reload(); await expect(page.locator('h1')).toBeVisible(); await expect(page.locator('[role="status"]')).toHaveCount(0); }
        if (route === '/notifications') await expect(page.getByRole('heading', { name: 'Your electricity bill was higher than expected' })).toBeVisible();
        const overflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1);
        expect(overflow, `${route} horizontal overflow at ${width}`).toBe(false);
        if (width === 768 || width === 390 || width === 1440) await page.screenshot({ path: `${output}/${route.includes('/expectations/') ? route.endsWith('new') ? 'create' : 'detail' : route.slice(1)}-${label}.png`, fullPage: true });
      }
      if (width === 390) {
        await page.getByRole('button', { name: 'Open navigation' }).click();
        expect(await page.locator('.workspace').evaluate(element => element.inert)).toBe(true);
        for (let tab = 0; tab < 12; tab++) {
          await page.keyboard.press('Tab');
          expect(await page.locator('.sidebar').evaluate(element => element.contains(document.activeElement))).toBe(true);
        }
        await page.keyboard.press('Escape');
        await expect(page.getByRole('button', { name: 'Open navigation' })).toBeFocused();
        await page.getByRole('button', { name: 'Open navigation' }).click();
        await expect(page.getByRole('link', { name: 'Connected Accounts', exact: true })).toBeVisible();
        await page.getByRole('link', { name: 'Connected Accounts', exact: true }).click();
        await expect(page).toHaveURL(/\/integrations$/);
      }
    }
    checkingNormalConsole = false; // These next requests deliberately return 422/404.
    await page.goto(`${base}/expectations/not-a-valid-uuid`);
    await expect(page.getByRole('heading', { name: 'Expectation not found' })).toBeVisible();
    await page.goto(`${base}/expectations/00000000-0000-4000-8000-000000000000`);
    await expect(page.getByRole('heading', { name: 'Expectation not found' })).toBeVisible();
    checkingNormalConsole = true;
    // Verify the real manual creation flow; delete only this invocation's row.
    await page.goto(`${base}/expectations/new`);
    await page.getByLabel('In your own words').fill(`Browser acceptance ${Date.now()}`);
    await page.getByRole('button', { name: 'Count on this' }).click();
    await page.getByLabel('Metric to watch').fill('test_observation');
    await page.getByLabel('Target value').fill('100');
    await page.getByRole('button', { name: 'Review expectation' }).click();
    await page.getByRole('button', { name: 'Start monitoring' }).click();
    await expect(page).toHaveURL(/\/expectations\/[0-9a-f-]{36}$/, { timeout: 30000 });
    createdId = page.url().split('/').pop();
    await expect(page.getByRole('heading', { name: 'Evidence gathered' })).toBeVisible();
    // Create a mismatch only for this temporary expectation, so real read/dismiss
    // mutations can be tested without altering the seeded demo notification.
    const evaluated = await page.evaluate(async ({ id, api }) => {
      const key = Object.keys(localStorage).find(key => key.startsWith('sb-') && key.endsWith('-auth-token'));
      const session = key ? JSON.parse(localStorage.getItem(key) ?? '{}') : {};
      const headers = { Authorization: `Bearer ${session.access_token}`, 'Content-Type': 'application/json' };
      const evidence = await fetch(`${api}/api/v1/expectations/${id}/evidence`, { method: 'POST', headers, body: JSON.stringify({ source: 'browser_acceptance', metric: 'test_observation', value: { amount: 125 }, unit: 'kWh', observed_at: new Date().toISOString(), confidence: 1, raw_data: {} }) });
      if (!evidence.ok) return false;
      const response = await fetch(`${api}/api/v1/expectations/${id}/evaluate`, { method: 'POST', headers });
      return response.ok && (await response.json()).result === 'MISMATCH';
    }, { id: createdId, api: apiOverride ?? 'http://localhost:8000' });
    expect(evaluated).toBe(true);
    await page.goto(`${base}/notifications`);
    const ownNotification = page.locator(`.notification-card:has(a[href="/expectations/${createdId}"])`);
    await ownNotification.getByRole('button', { name: 'Mark as read' }).click();
    await expect(ownNotification.getByText('Read · In-app notification', { exact: true })).toBeVisible();
    await ownNotification.getByRole('button', { name: 'Dismiss', exact: true }).click();
    await expect(ownNotification).toHaveCount(0);
    console.log('PASS real notification read/dismiss; seeded alert untouched');
    console.log('PASS real demo dashboard, expectations, evidence, timeline, connections, notifications and manual creation');
    console.log(`PASS ${process.env.COUNTON_E2E_QUICK === '1' ? 'desktop' : '1440/1280/1024/768/390px'} layout, no overflow, back/forward, direct links, reload and invalid IDs`);
  }
  expect(pageErrors).toHaveLength(0);
  expect(normalConsoleErrors).toBe(0);
  console.log('PASS no browser JavaScript errors');
  completed = true;
} catch (error) {
  if (failedApiResponses.length) console.error('API response failures:', failedApiResponses.join(', '));
  throw error;
} finally {
  if (createdId) {
    const removed = await page.evaluate(async ({ id, api }) => {
      // SDK storage contains the session; this is test-only transport, never app data access.
      const key = Object.keys(localStorage).find(key => key.startsWith('sb-') && key.endsWith('-auth-token'));
      const session = key ? JSON.parse(localStorage.getItem(key) ?? '{}') : {};
      return (await fetch(`${api}/api/v1/expectations/${id}`, { method: 'DELETE', headers: { Authorization: `Bearer ${session.access_token}` } })).status;
    }, { id: createdId, api: apiOverride ?? 'http://localhost:8000' });
    if (removed !== 204) { console.log('FAIL browser acceptance row cleanup'); process.exitCode = 1; }
    else console.log('PASS browser acceptance row cleaned');
  }
  try {
    if (completed && !empty) {
      checkingNormalConsole = false; // Deliberate expiry/401 responses below.
      await page.setViewportSize({ width: 1440, height: 1000 });
      const refresh = page.waitForResponse(response => {
        const url = new URL(response.url());
        return url.pathname === '/auth/v1/token' && url.searchParams.get('grant_type') === 'refresh_token';
      });
      await page.evaluate(() => {
        const key = Object.keys(localStorage).find(key => key.startsWith('sb-') && key.endsWith('-auth-token'));
        if (!key) throw new Error('SDK session missing');
        const session = JSON.parse(localStorage.getItem(key));
        session.expires_at = Math.floor(Date.now() / 1000) - 120;
        localStorage.setItem(key, JSON.stringify(session));
      });
      await page.goto(`${base}/dashboard`);
      expect((await refresh).ok()).toBe(true);
      await expect(page.getByText('$162.00', { exact: true })).toBeVisible();
      const rejected = '**/api/v1/expectations?*';
      phase = 'controlled API 401';
      await context.route(rejected, route => route.fulfill({ status: 401, headers: { 'X-CountOn-Test': 'controlled-401' }, contentType: 'application/json', body: JSON.stringify({ error: { message: 'Session expired' } }) }));
      await page.reload(); await expect(page).toHaveURL(/\/login$/);
      await context.unroute(rejected);
      phase = 'relogin after API 401';
      await signIn();
      const expired = '**/auth/v1/token?grant_type=refresh_token';
      phase = 'controlled refresh expiry';
      await context.route(expired, route => route.fulfill({ status: 400, contentType: 'application/json', body: JSON.stringify({ error_code: 'refresh_token_not_found', msg: 'Invalid Refresh Token' }) }));
      await page.evaluate(() => {
        const key = Object.keys(localStorage).find(key => key.startsWith('sb-') && key.endsWith('-auth-token'));
        const session = JSON.parse(localStorage.getItem(key)); session.expires_at = 1;
        localStorage.setItem(key, JSON.stringify(session));
      });
      await page.reload(); await expect(page).toHaveURL(/\/login$/);
      await context.unroute(expired);
      phase = 'relogin after refresh expiry';
      await signIn();
      phase = 'logout';
      await page.getByRole('button', { name: 'Sign out', exact: true }).click();
      await expect(page).toHaveURL(/\/login$/);
      for (const route of protectedRoutes) { await page.goto(`${base}${route}`); await expect(page).toHaveURL(/\/login$/); }
      expect(pageErrors).toHaveLength(0);
      console.log('PASS real SDK token refresh, controlled API 401 and refresh expiry, logout and every protected route');
    }
  } catch (error) {
    console.error('Auth audit response statuses:', failedApiResponses.slice(-8).join(', '));
    console.error('Auth audit current route:', new URL(page.url()).pathname);
    console.error('Auth audit phase:', phase);
    throw error;
  } finally { await browser.close(); }
}
