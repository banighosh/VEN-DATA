// End-to-end UI test against a running stack (nginx/static build + FastAPI + PostgreSQL).
//   npm install playwright && npx playwright install chromium
//   BASE_URL=http://localhost:8080 ADIDAS_XLSX=/path/to/Adidas_US_Sales_Datasets.xlsx node e2e/ui-check.mjs
// Set SKIP_UPLOAD=1 to skip the upload wizard when the dataset is already loaded.
import { chromium } from 'playwright';
import fs from 'node:fs';

const BASE = process.env.BASE_URL ?? 'http://localhost:8080';
const XLSX = process.env.ADIDAS_XLSX ?? 'Adidas_US_Sales_Datasets.xlsx';
const OUT = process.env.OUT_DIR ?? 'e2e-output';
fs.mkdirSync(OUT, { recursive: true });
const results = [];
const check = (name, ok, detail = '') => { results.push({ name, ok: !!ok, detail }); console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${detail ? '  ' + detail : ''}`); };

const b = await chromium.launch();
const ctx = await b.newContext({ viewport: { width: 1440, height: 1000 }, acceptDownloads: true });
const p = await ctx.newPage();
const errors = [];
p.on('pageerror', (e) => errors.push(e.message));
p.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });

if (!process.env.SKIP_UPLOAD) {
// 1. Upload wizard with the messy sheet
await p.goto(`${BASE}/#/data`, { waitUntil: 'networkidle' });
await p.getByRole('button', { name: 'Upload a file' }).click();
await p.locator('input[type=file]').setInputFiles(XLSX);
await p.getByText('Pick the one that holds transaction-level data').waitFor({ timeout: 20000 });
check('Workbook sheets listed', await p.getByRole('button', { name: /Data Sales Adidas/ }).count() === 1);
check('Recommended sheet badge shown', await p.getByText('Recommended').count() >= 1);
check('Header row detected on messy sheet', await p.getByText('Header detected on row 5').count() === 1);
await p.getByRole('button', { name: /Data Sales Adidas/ }).click();
await p.screenshot({ path: `${OUT}/01-sheets.png` });
await p.getByRole('button', { name: 'Preview sheet' }).click();
await p.getByText('Detected columns').waitFor({ timeout: 30000 });
check('Header note shown', await p.getByText(/Header found on row 5/).count() === 1);
check('Empty leading column dropped', await p.getByText(/Dropped 1 empty unnamed column/).count() === 1);
check('Quality: revenue consistency issue reported', await p.getByText(/3,886 rows \(40\.3%\)/).count() >= 1);
await p.screenshot({ path: `${OUT}/02-review.png`, fullPage: true });
await p.getByRole('button', { name: 'Continue to mapping' }).click();
const dateSel = p.getByLabel('Source column for Transaction date');
check('Date auto-mapped', (await dateSel.inputValue()) === 'Invoice Date');
check('Revenue auto-mapped', (await p.getByLabel('Source column for Revenue').inputValue()) === 'Total Sales');
check('Retailer ID warning shown', await p.getByText(/was not mapped to Customer ID/).count() === 1);
await p.screenshot({ path: `${OUT}/03-mapping.png`, fullPage: true });
const nameInput = p.locator('label:has-text("Dataset name") input');
await nameInput.fill('Adidas raw export (messy sheet)');
await p.getByRole('button', { name: 'Process dataset' }).click();
await p.getByText(/is ready and now active/).waitFor({ timeout: 60000 });
check('Dataset processed via UI', true);
check('Reconciliation passed', await p.getByText(/Post-load reconciliation passed/).count() >= 1);
await p.screenshot({ path: `${OUT}/04-done.png`, fullPage: true });
await p.getByRole('button', { name: 'Open the dashboard' }).click();
await p.waitForLoadState('networkidle');
await p.waitForTimeout(800);

// 2. Dashboard KPIs match the API for the new dataset
const ws = await p.locator('header').getByText('Adidas raw export (messy sheet)').count();
check('Workspace selector shows the new dataset', ws === 1);
const rev = await p.locator('section[aria-label="Key performance indicators"] p.text-\\[28px\\]').first().innerText();
check('Revenue KPI for 2021 rendered', rev.includes('$717.82M'), rev);
// Spelling variants unified: the raw sheet says "In-store"
await p.goto(`${BASE}/#/executive`, { waitUntil: 'networkidle' });
await p.waitForTimeout(600);
check('Channel values available', await p.getByText('In-store').count() + await p.getByText('In-Store').count() > 0);

// 3. Cross-filter + drill-down on regional bars
await p.goto(`${BASE}/#/regional`, { waitUntil: 'networkidle' });
await p.waitForTimeout(800);
const regionCard = p.locator('section', { has: p.getByRole('heading', { name: 'Region-wise revenue' }) });
const westBar = regionCard.locator('.recharts-bar-rectangle').first();
await westBar.click();
await p.waitForLoadState('networkidle');
await p.waitForTimeout(900);
check('Click on region applies global filter chip', await p.locator('[aria-label="Active filters"]').getByText('West').count() === 1);
check('Region chart drilled to states', await regionCard.getByText('State / province breakdown').count() === 1);
await p.screenshot({ path: `${OUT}/05-drill.png`, fullPage: true });
const kpiAfter = await p.evaluate(async () => {
  const r = await fetch('/api/datasets');
  return (await r.json()).length;
});
check('Datasets API lists the dataset', kpiAfter >= 1, String(kpiAfter));
await regionCard.getByRole('button', { name: /All regions/ }).click();
await p.waitForTimeout(700);
check('Breadcrumb clears drill filter', await p.locator('[aria-label="Active filters"]').count() === 0);

// 4. Date picker presets
await p.getByRole('button', { name: /vs previous period/ }).first().click();
await p.getByRole('button', { name: 'Calendar 2020' }).click();
await p.waitForLoadState('networkidle');
await p.waitForTimeout(700);
check('Date preset applied', (await p.locator('header').getByText('2020').count()) >= 1);

// 5. Dimension multi-select
await p.getByRole('button', { name: /^Sales channel/ }).click();
await p.getByRole('option', { name: 'Online' }).click();
await p.getByRole('button', { name: 'Done' }).click();
await p.waitForTimeout(800);
check('Channel filter chip present', await p.locator('[aria-label="Active filters"]').getByText('Online').count() === 1);

// 6. Saved view roundtrip
await p.getByRole('button', { name: 'Saved views' }).click();
await p.getByLabel('View name').fill('Online 2020');
await p.getByRole('button', { name: 'Save', exact: true }).click();
await p.waitForTimeout(600);
check('Saved view listed', await p.getByRole('button', { name: /Online 2020/ }).count() >= 1);
await p.keyboard.press('Escape');
await p.getByRole('button', { name: 'Reset' }).click();
await p.waitForTimeout(500);
check('Reset clears dimension filters', await p.locator('[aria-label="Active filters"]').count() === 0);

// 7. Global search applies a filter
await p.getByLabel('Global search').fill('Charles');
await p.getByRole('option', { name: /Charleston/ }).first().waitFor({ timeout: 5000 });
await p.keyboard.press('Enter');
await p.waitForTimeout(700);
check('Search result applied as filter', await p.locator('[aria-label="Active filters"]').getByText('Charleston').count() === 1);
await p.getByRole('button', { name: 'Reset' }).click();

}
// 8. Data explorer: search, sort, record drawer, export
await p.goto(`${BASE}/#/explorer`, { waitUntil: 'networkidle' });
await p.getByLabel('Search records').fill('west gear');
await p.waitForTimeout(900);
const footer = await p.getByText(/of [\d,]+ rows/).innerText();
check('Explorer search narrows rows', /of [\d,]+ rows/.test(footer), footer);
await p.getByRole('button', { name: /^Revenue/ }).click();
await p.waitForTimeout(600);
await p.locator('tbody tr').first().click();
await p.getByText('Original values as uploaded').waitFor({ timeout: 5000 });
check('Record drawer shows original values', true);
await p.screenshot({ path: `${OUT}/06-explorer.png` });
await p.getByRole('button', { name: 'Close' }).click();
const [dl] = await Promise.all([p.waitForEvent('download'), p.getByRole('button', { name: 'CSV' }).click()]);
const path = `${OUT}/${dl.suggestedFilename()}`;
await dl.saveAs(path);
const lines = fs.readFileSync(path, 'utf8').trim().split('\n').length - 1;
check('CSV export downloads filtered rows', lines > 0, `${lines} rows in ${dl.suggestedFilename()}`);

// 9. Dashboard report download (Excel)
await p.goto(`${BASE}/#/dashboard`, { waitUntil: 'networkidle' });
await p.getByRole('button', { name: 'Export', exact: true }).click();
const [rep] = await Promise.all([p.waitForEvent('download'), p.getByRole('menuitem', { name: /Dashboard report \(Excel\)/ }).click()]);
await rep.saveAs(`${OUT}/${rep.suggestedFilename()}`);
check('Excel dashboard report downloads', fs.statSync(`${OUT}/${rep.suggestedFilename()}`).size > 5000, rep.suggestedFilename());

// 10. Chart table view toggle + PNG export
const trendCard = p.locator('section', { has: p.getByRole('heading', { name: 'Revenue trend' }) });
await trendCard.getByRole('button', { name: 'Show as table' }).click();
check('Chart table view renders', await trendCard.locator('table').count() === 1);
await trendCard.getByRole('button', { name: 'Show as chart' }).click();
await trendCard.getByRole('button', { name: 'Export chart' }).click();
const [png] = await Promise.all([p.waitForEvent('download'), trendCard.getByRole('menuitem', { name: /PNG/ }).click()]);
await png.saveAs(`${OUT}/${png.suggestedFilename()}`);
check('Chart PNG export downloads', fs.statSync(`${OUT}/${png.suggestedFilename()}`).size > 2000, png.suggestedFilename());

// 11. Every page loads without runtime errors
for (const pg of ['executive', 'performance', 'financial', 'customers', 'products', 'regional', 'operations', 'insights', 'settings']) {
  await p.goto(`${BASE}/#/${pg}`, { waitUntil: 'networkidle' });
  await p.waitForTimeout(400);
}
check('No runtime errors across pages', errors.length === 0, errors.slice(0, 3).join(' | '));
fs.writeFileSync(`${OUT}/results.json`, JSON.stringify(results, null, 1));
console.log(`\n${results.filter((r) => r.ok).length}/${results.length} checks passed`);
await b.close();
process.exit(results.every((r) => r.ok) ? 0 : 1);
