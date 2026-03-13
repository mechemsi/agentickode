const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const SENSITIVE_REPLACEMENTS = {
  // Full compound names first (order matters - longest match first)
  'viminkas/prestashop': 'acme/web-store',
  'mechemsi-openbook-core': 'myorg/notebook-app',
  'mechemsi-timetracker': 'myorg/time-tracker',
  'mechemsi/openbook-core': 'myorg/notebook-app',
  'mechemsi/linker': 'myorg/url-shortener',
  'mechemsi/agentickode': 'myorg/agentickode',
  // Org names
  'mechemsi': 'myorg',
  'viminkas': 'acme',
  // Project names / slugs
  'beautygroup': 'web-store',
  'openbook-core': 'notebook-app',
  'openbook': 'notebook',
  'prestashop': 'web-store',
  'linker': 'url-shortener',
  'timetracker': 'time-tracker',
  // IPs
  '192.168.1.183': '10.0.1.xx',
  '192.168.1.235': '10.0.2.xx',
  '192.168.1.81': '10.0.3.xx',
  '192.168.1.': '10.0.x.',
  // Username
  'domas': 'user',
};

async function sanitizeDOM(page) {
  await page.evaluate((replacements) => {
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    while (walker.nextNode()) {
      let text = walker.currentNode.textContent;
      for (const [from, to] of Object.entries(replacements)) {
        text = text.split(from).join(to);
      }
      walker.currentNode.textContent = text;
    }
    document.querySelectorAll('svg text, svg tspan').forEach(el => {
      let text = el.textContent;
      for (const [from, to] of Object.entries(replacements)) {
        text = text.split(from).join(to);
      }
      el.textContent = text;
    });
    document.querySelectorAll('input, textarea').forEach(el => {
      let val = el.value;
      for (const [from, to] of Object.entries(replacements)) {
        val = val.split(from).join(to);
      }
      el.value = val;
    });
  }, SENSITIVE_REPLACEMENTS);
}

async function main() {
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1280, height: 800 } });
  const page = await context.newPage();

  const outDir = __dirname;
  const framesDir = path.join(outDir, 'frames');
  if (!fs.existsSync(framesDir)) fs.mkdirSync(framesDir);

  const pages = [
    { url: 'http://localhost:5173/', name: 'dashboard', file: 'dashboard.png', frames: 10 },
    { url: 'http://localhost:5173/runs/23', name: 'run-detail', file: 'run-detail-top.png', frames: 10 },
    { url: 'http://localhost:5173/projects', name: 'projects', file: 'projects.png', frames: 10 },
    { url: 'http://localhost:5173/workspace-servers', name: 'servers', file: 'workspace-servers.png', frames: 10 },
    { url: 'http://localhost:5173/agents', name: 'agents', file: 'agents.png', frames: 10 },
    { url: 'http://localhost:5173/workflows', name: 'workflows', file: 'workflows.png', frames: 8 },
    { url: 'http://localhost:5173/settings', name: 'settings', file: 'settings.png', frames: 8 },
  ];

  let frameNum = 0;

  for (const pg of pages) {
    console.log(`Capturing ${pg.name}...`);
    await page.goto(pg.url, { waitUntil: 'domcontentloaded', timeout: 15000 });
    await page.waitForTimeout(2000);
    await sanitizeDOM(page);

    await page.screenshot({ path: path.join(outDir, pg.file) });
    console.log(`  Saved ${pg.file}`);

    for (let i = 0; i < pg.frames; i++) {
      const framePath = path.join(framesDir, `frame_${String(frameNum).padStart(4, '0')}.png`);
      await page.screenshot({ path: framePath });
      frameNum++;
    }
  }

  // Agents expanded - click Claude CLI row to expand it
  console.log('Capturing agents-expanded...');
  await page.goto('http://localhost:5173/agents', { waitUntil: 'domcontentloaded', timeout: 15000 });
  await page.waitForTimeout(2000);
  try {
    // The agent rows are divs with chevron icons - click the Claude CLI chevron
    const claudeRow = page.locator('text=Claude CLI').first();
    if (await claudeRow.count() > 0) {
      await claudeRow.click();
      await page.waitForTimeout(800);
    }
  } catch (e) { console.log('  Could not expand Claude row:', e.message); }
  await sanitizeDOM(page);
  await page.screenshot({ path: path.join(outDir, 'agents-expanded.png') });
  console.log('  Saved agents-expanded.png');

  await browser.close();
  console.log(`\nDone! ${frameNum} frames captured for GIF.`);
}

main().catch(e => { console.error(e); process.exit(1); });
