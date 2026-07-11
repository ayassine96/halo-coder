// HALO Factory — Full E2E Playwright Test Suite (Pass 2)
// Tests Factory Floor UI, Supervisor API integration, and kube-coder integration
const { chromium } = require('playwright');

const BASE = 'http://localhost:8888';

const tests = [];
let passed = 0;
let failed = 0;

function test(name, fn) { tests.push({ name, fn }); }

async function run() {
  const browser = await chromium.launch({ headless: true, args: ['--no-sandbox'] });
  const context = await browser.newContext();
  const page = await context.newPage();

  for (const { name, fn } of tests) {
    try {
      await fn(page);
      console.log(`  ✓ ${name}`);
      passed++;
    } catch (e) {
      console.log(`  ✗ ${name}`);
      console.log(`    ${e.message.split('\n')[0].substring(0, 120)}`);
      failed++;
      // Recreate page if it was closed
      if (page.isClosed && page.isClosed()) {
        try { await context.newPage(); } catch (_) {}
        // Replace page reference
        const newPage = await context.newPage();
        // Reassign page for next tests
        page = newPage;
      }
    }
  }

  await browser.close();
  console.log(`\n${passed} passed, ${failed} failed`);
  process.exit(failed > 0 ? 1 : 0);
}

// Helper: wait for the SPA to render (WITHOUT networkidle because SSE keeps network busy)
async function waitForApp(page) {
  await page.goto(BASE, { waitUntil: 'domcontentloaded', timeout: 10000 });
  await page.waitForSelector('#topbar', { state: 'visible', timeout: 5000 });
  await page.waitForTimeout(1500); // Let JS modules + fetchState run
}

// Helper: make an API call from within the page context
async function apiCall(page, url, options = {}) {
  return await page.evaluate(async (params) => {
    const { url, ...opts } = params;
    const resp = await fetch(url, opts);
    const ct = resp.headers.get('content-type') || '';
    if (ct.includes('application/json')) return await resp.json();
    return await resp.text();
  }, { url, ...options });
}

// === Page Load Tests ===

test('Page loads with correct title', async (page) => {
  await page.goto(BASE, { waitUntil: 'domcontentloaded', timeout: 10000 });
  const title = await page.title();
  if (title !== 'HALO Factory Floor') throw new Error(`title="${title}"`);
});

test('Root returns HTML with HALO topbar', async (page) => {
  await page.goto(BASE, { waitUntil: 'domcontentloaded', timeout: 10000 });
  await page.waitForSelector('#topbar', { state: 'visible', timeout: 5000 });
  const h1 = await page.textContent('#topbar h1');
  if (h1 !== 'HALO Factory Floor') throw new Error(`h1="${h1}"`);
});

test('Static CSS loads with dark mode variables', async (page) => {
  const resp = await page.goto(`${BASE}/static/styles.css`, { waitUntil: 'domcontentloaded', timeout: 10000 });
  if (resp.status() !== 200) throw new Error(`CSS status=${resp.status()}`);
  const content = await resp.text();
  if (!content.includes('--bg')) throw new Error('CSS missing dark mode variables');
});

test('Static app.js loads as ES module', async (page) => {
  const resp = await page.goto(`${BASE}/static/app.js`, { waitUntil: 'domcontentloaded', timeout: 10000 });
  if (resp.status() !== 200) throw new Error(`app.js status=${resp.status()}`);
});

test('Static graph.js loads with renderGraph export', async (page) => {
  const resp = await page.goto(`${BASE}/static/graph.js`, { waitUntil: 'domcontentloaded', timeout: 10000 });
  if (resp.status() !== 200) throw new Error(`graph.js status=${resp.status()}`);
  const content = await resp.text();
  if (!content.includes('renderGraph')) throw new Error('graph.js missing renderGraph');
});

// === Navigation Tests ===

test('All 6 navigation buttons present', async (page) => {
  await waitForApp(page);
  const buttons = await page.$$('#topbar nav button');
  if (buttons.length !== 6) throw new Error(`Expected 6, got ${buttons.length}`);
});

test('Click each nav button switches view', async (page) => {
  await waitForApp(page);
  const views = ['kanban', 'graph', 'logs', 'approvals', 'devpods', 'models'];
  for (const v of views) {
    await page.click(`[data-view="${v}"]`);
    await page.waitForTimeout(200);
    const cls = await page.getAttribute(`#view-${v}`, 'class');
    if (cls === null || cls.includes('hidden')) throw new Error(`View ${v} not visible`);
  }
});

test('Kanban is default active view', async (page) => {
  await waitForApp(page);
  const cls = await page.getAttribute('#view-kanban', 'class');
  if (cls === null || cls.includes('hidden')) throw new Error('Kanban should be visible');
  const btn = await page.getAttribute('[data-view="kanban"]', 'class');
  if (btn === null || !btn.includes('active')) throw new Error('Kanban button not active');
});

// === Real Data Tests (with Supervisor API proxy) ===

test('Factory Floor /api/state returns real specs from Supervisor', async (page) => {
  await waitForApp(page);
  const data = await apiCall(page, `${BASE}/api/state`);
  if (data.paused === undefined) throw new Error('Missing paused field');
  if (!Array.isArray(data.specs)) throw new Error('specs not array');
  if (data.specs.length === 0) throw new Error('No specs loaded');
  if (!data.specs[0].id) throw new Error('Spec missing id');
  if (!data.specs[0].status) throw new Error('Spec missing status');
});

test('Kanban board renders spec cards from real state', async (page) => {
  await waitForApp(page);
  await page.waitForTimeout(2000); // Wait for fetchState to complete
  const cards = await page.$$('.kanban-card');
  if (cards.length === 0) throw new Error('No kanban cards rendered');
  const firstCard = await page.textContent('.kanban-card');
  if (!firstCard.includes('SPEC')) throw new Error(`Card doesn't contain SPEC: "${firstCard.substring(0, 60)}"`);
});

test('Graph view renders SVG or empty state', async (page) => {
  await waitForApp(page);
  await page.waitForTimeout(2000);
  await page.click('[data-view="graph"]');
  await page.waitForTimeout(500);
  const html = await page.innerHTML('#graph-container');
  if (html.trim() === '') throw new Error('Graph container empty');
  const hasSvg = html.includes('svg') || html.includes('empty-state');
  if (!hasSvg) throw new Error('Graph rendered neither SVG nor empty state');
});

test('Models view renders metric cards', async (page) => {
  await waitForApp(page);
  await page.waitForTimeout(1000);
  await page.click('[data-view="models"]');
  await page.waitForTimeout(500);
  const container = await page.$('#model-util');
  if (!container) throw new Error('Models container missing');
  const html = await page.innerHTML('#model-util');
  if (html.trim() === '') throw new Error('Models view empty');
});

test('DevPods view renders', async (page) => {
  await waitForApp(page);
  await page.waitForTimeout(1000);
  await page.click('[data-view="devpods"]');
  await page.waitForTimeout(500);
  const container = await page.$('#devpod-status');
  if (!container) throw new Error('DevPods container missing');
});

// === CSRF + Mutation Tests ===

test('CSRF token endpoint works via proxy', async (page) => {
  await waitForApp(page);
  const data = await apiCall(page, `${BASE}/api/csrf-token`);
  if (!data.csrf_token) throw new Error('No csrf_token in response');
  if (data.csrf_token.length < 20) throw new Error('CSRF token too short');
});

test('Pause button toggles state via proxy to Supervisor', async (page) => {
  await waitForApp(page);
  await page.waitForTimeout(1000);
  const origText = await page.textContent('#pause-btn');
  await page.click('#pause-btn');
  await page.waitForTimeout(1000);
  const newText = await page.textContent('#pause-btn');
  if (newText === origText) throw new Error(`Button didn't change: "${origText}" → "${newText}"`);
  // Restore
  await page.click('#pause-btn');
  await page.waitForTimeout(1000);
  const restored = await page.textContent('#pause-btn');
  if (restored !== origText) throw new Error(`Not restored: "${restored}" !== "${origText}"`);
});

// === Command Palette Tests ===

test('Ctrl+K opens command palette', async (page) => {
  await waitForApp(page);
  await page.keyboard.down('Control');
  await page.keyboard.press('k');
  await page.keyboard.up('Control');
  await page.waitForTimeout(300);
  const cls = await page.getAttribute('#command-palette', 'class');
  if (cls !== null && cls.includes('hidden')) throw new Error('Palette should be visible');
});

test('Escape closes command palette', async (page) => {
  await waitForApp(page);
  await page.keyboard.down('Control');
  await page.keyboard.press('k');
  await page.keyboard.up('Control');
  await page.waitForTimeout(200);
  await page.keyboard.press('Escape');
  await page.waitForTimeout(200);
  const cls = await page.getAttribute('#command-palette', 'class');
  if (cls === null || !cls.includes('hidden')) throw new Error('Palette should be hidden');
});

test('Command "> logs" switches to Logs view', async (page) => {
  await waitForApp(page);
  await page.keyboard.down('Control');
  await page.keyboard.press('k');
  await page.keyboard.up('Control');
  await page.waitForTimeout(200);
  await page.fill('#cmd-input', '> logs');
  await page.keyboard.press('Enter');
  await page.waitForTimeout(300);
  const cls = await page.getAttribute('#view-logs', 'class');
  if (cls === null || cls.includes('hidden')) throw new Error('Logs view should be visible');
});

// === Backend Service Health (via Factory Floor proxy — same origin, no CORS) ===

test('Kernel health returns ok with backend reachable', async (page) => {
  await waitForApp(page);
  const health = await apiCall(page, 'http://localhost:13306/health');
  if (!health) throw new Error('No response from Kernel');
  if (health.status !== 'ok') throw new Error(`Kernel status="${health.status}"`);
  if (health.backend_reachable !== true) throw new Error('Lemonade backend not reachable');
});

test('TDAD health returns ok', async (page) => {
  await waitForApp(page);
  const health = await apiCall(page, 'http://localhost:8402/health');
  if (!health || health.status !== 'ok') throw new Error(`TDAD status="${health?.status}"`);
});

test('Agent-Bridge health returns ok', async (page) => {
  await waitForApp(page);
  const health = await apiCall(page, 'http://localhost:19000/health');
  if (!health || health.status !== 'ok') throw new Error(`Bridge status="${health?.status}"`);
});

// === kube-coder Integration (Agent-Bridge endpoints) ===

test('Agent-Bridge serves file tree from HALO project dir', async (page) => {
  await waitForApp(page);
  const data = await apiCall(page, 'http://localhost:19000/api/files');
  if (!data.items) throw new Error('No items in file tree');
  if (data.items.length === 0) throw new Error('Empty file tree — project dir not set');
});

test('Agent-Bridge serves all 4 launcher links', async (page) => {
  await waitForApp(page);
  const data = await apiCall(page, 'http://localhost:19000/api/launchers');
  for (const key of ['terminal', 'vscode', 'files', 'spec']) {
    if (!data[key]) throw new Error(`Missing launcher: ${key}`);
  }
});

// === TDAD Integration (tree-sitter index + analyze) ===

test('TDAD indexes demo project correctly', async (page) => {
  await waitForApp(page);
  const result = await apiCall(page, 'http://localhost:8402/index', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ repo: '/tmp/halo-test/projects/demo', changed_files: [] }),
  });
  if (result.modules === undefined) throw new Error('TDAD index failed');
  if (result.modules === 0) throw new Error('TDAD indexed 0 modules');
});

test('TDAD identifies affected tests for changed source file', async (page) => {
  await waitForApp(page);
  const result = await apiCall(page, 'http://localhost:8402/analyze', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ repo: '/tmp/halo-test/projects/demo', changed_files: ['src/app.py'] }),
  });
  if (!result.affected_tests) throw new Error('Missing affected_tests');
  if (result.affected_tests.length === 0) throw new Error('Expected at least 1 affected test');
});

// === Kernel Real LLM Proxy Test ===

test('Kernel returns real LLM response (not placeholder)', async (page) => {
  await waitForApp(page);
  const data = await apiCall(page, 'http://localhost:13306/v1/chat/completions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      model: 'halo-fast',
      messages: [{ role: 'user', content: 'Say hello in 3 words' }],
    }),
  });
  if (!data.choices) throw new Error('No choices in Kernel response');
  const content = data.choices[0].message.content;
  if (content.includes('[HALO Kernel placeholder response]')) throw new Error('Still placeholder!');
  if (content.length < 1) throw new Error('Empty response');
});

// === Supervisor API Integration ===

test('Supervisor /api/state shows real specs with project field', async (page) => {
  await waitForApp(page);
  const data = await apiCall(page, 'http://localhost:9091/api/state');
  if (!data.specs || data.specs.length === 0) throw new Error('No specs in Supervisor');
  const spec = data.specs[0];
  if (!spec.id) throw new Error('Spec missing id');
  if (!spec.status) throw new Error('Spec missing status');
  if (!spec.project && spec.project !== '') throw new Error('Spec missing project field');
});

test('Supervisor metrics endpoint returns Prometheus format', async (page) => {
  await waitForApp(page);
  const text = await apiCall(page, 'http://localhost:9091/metrics');
  if (!text.includes('halo_supervisor')) throw new Error('Missing halo_supervisor metrics');
});

// === Dark Mode Visual Tests ===

test('Dark mode background is applied (CSS loaded)', async (page) => {
  await waitForApp(page);
  const bg = await page.evaluate(() => getComputedStyle(document.body).backgroundColor);
  if (bg === 'rgb(13, 17, 23)') return;
  if (bg === 'rgba(0, 0, 0, 0)') throw new Error('Background transparent — CSS not loaded');
  throw new Error(`Unexpected bg: ${bg}`);
});

test('Kanban card has colored left border (status color)', async (page) => {
  await waitForApp(page);
  await page.waitForTimeout(2000);
  const card = await page.$('.kanban-card');
  if (!card) throw new Error('No kanban card found');
  const border = await card.evaluate((el) => getComputedStyle(el).borderLeftColor);
  if (border === 'rgba(0, 0, 0, 0)') throw new Error('No border color on kanban card');
});

run();