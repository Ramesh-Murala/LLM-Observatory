// Optional browser verification: npm install --no-save playwright, then start the API.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const path = require('node:path');

(async () => {
  const browser = await chromium.launch({headless: true});
  let page;
  try {
    page = await browser.newPage({viewport: {width: 1440, height: 1000}});
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(process.env.OBSERVATORY_URL || 'http://127.0.0.1:8000');
    await page.locator('#dataset').waitFor();
    await page.locator('#dataset-name').fill('browser-schema-smoke');
    await page.locator('#dataset-file').setInputFiles(
      path.resolve(__dirname, '../observatory/data/structured-contracts-v1.jsonl'));
    const uploaded = page.waitForResponse(r => r.url().endsWith('/api/datasets') && r.request().method() === 'POST');
    await page.locator('#upload-dataset').click();
    const dataset = await (await uploaded).json();
    await page.waitForFunction(id => document.getElementById('dataset').value === id, dataset.id);
    async function run(scenario) {
      await page.locator('#scenario').selectOption(scenario);
      const pending = page.waitForResponse(r => r.url().endsWith('/api/runs') && r.request().method() === 'POST');
      await page.locator('#run-button').click();
      const response = await pending;
      assert.equal(response.status(), 201);
      const result = await response.json();
      await page.waitForFunction(passed => document.getElementById('decision').textContent === (passed ? 'Approved' : 'Blocked'), result.gate.passed);
      return result;
    }
    const stable = await run('stable');
    assert.equal(stable.summaries.candidate.cases, 12);
    const regression = await run('regression');
    assert.equal(regression.summaries.candidate.pass_rate, 5 / 12);
    await page.locator('#compare-baseline').selectOption(stable.id);
    await page.locator('#compare-button').click();
    await page.waitForFunction(() => document.getElementById('comparison-result').textContent.startsWith('7 regressions'));
    assert.equal(await page.locator('#comparison-cases tr').count(), 12);
    await page.locator('#failed-only').check();
    assert.equal(await page.locator('#traces-body tr').count(), 7);
    await page.locator('#traces-body button').first().click();
    assert.equal(await page.locator('#trace-dialog').isVisible(), true);
    await page.locator('#close-dialog').click();
    const csv = await page.request.get(await page.locator('#export-csv').getAttribute('href'));
    assert.equal(csv.status(), 200);
    assert.ok((await csv.text()).startsWith('case_id,category'));
    await page.screenshot({path: '/tmp/observatory-workspace-desktop.png', fullPage: true});
    await page.setViewportSize({width: 390, height: 844});
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
    await page.screenshot({path: '/tmp/observatory-workspace-mobile.png', fullPage: true});
    assert.deepEqual(errors, []);
    console.log('Browser smoke passed: upload, stable/blocked runs, comparisons, filters, traces, export, mobile layout.');
  } catch (error) {
    if (page) await page.screenshot({path: '/tmp/observatory-workspace-failure.png', fullPage: true});
    throw error;
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
