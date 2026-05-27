// Headless check for the Timeline research-gap color mode.
const puppeteer = require('puppeteer-core');
const CHROME = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const URL = 'file:///' + 'C:/tree/troy-family-tree-research/data/exports/timeline.html';

(async () => {
  const browser = await puppeteer.launch({ executablePath: CHROME, headless: 'new',
    args: ['--no-sandbox','--window-size=1280,800'] });
  const page = await browser.newPage();
  await page.setViewport({ width: 1280, height: 800 });
  const errors = [];
  page.on('pageerror', e => errors.push('PAGEERROR: ' + e.message));
  page.on('console', m => { if (m.type()==='error') errors.push('CONSOLE.ERROR: ' + m.text()); });
  await page.goto(URL, { waitUntil: 'load', timeout: 30000 });
  await new Promise(r => setTimeout(r, 800));

  // dataset has gap levels for everyone, spread across the 0..3 buckets
  const dist = await page.evaluate(() => {
    const c=[0,0,0,0]; for (const p of PEOPLE) c[p.gap==null?3:p.gap]++; return c;
  });
  console.log('gap distribution [none,weak,partly,well]:', JSON.stringify(dist));

  const st0 = await page.evaluate(() => window.__tl.state());
  console.log('default mode:', st0.cmode);

  // flip to gap mode via the on-page button and confirm state + legend update
  await page.evaluate(() => { for (const b of document.querySelectorAll('#cmode button')) if (b.dataset.m==='gap') b.click(); });
  await new Promise(r => setTimeout(r, 150));
  const st1 = await page.evaluate(() => window.__tl.state());
  const legend = await page.evaluate(() => document.getElementById('legend').textContent);
  console.log('after toggle, mode:', st1.cmode);
  console.log('legend shows gaps:', /Research gaps/.test(legend), '|', legend.replace(/\s+/g,' ').trim());

  console.log('\nERRORS (' + errors.length + '):'); errors.slice(0,10).forEach(e=>console.log(' ',e));
  await browser.close();
  process.exit((errors.length || st1.cmode!=='gap' || dist.every(x=>x===0)) ? 1 : 0);
})().catch(e => { console.error('TEST CRASHED:', e.message); process.exit(1); });
