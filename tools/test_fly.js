const puppeteer = require('puppeteer-core');
const path = require('path');

const CHROME = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const URL = 'file:///' + 'C:/troytree-dist/pub/graph_3d.html';

(async () => {
  const browser = await puppeteer.launch({
    executablePath: CHROME,
    headless: 'new',
    args: ['--no-sandbox', '--enable-webgl', '--ignore-gpu-blocklist',
           '--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader',
           '--window-size=1280,800'],
  });
  const page = await browser.newPage();
  await page.setViewport({ width: 1280, height: 800 });
  const errors = [];
  page.on('pageerror', e => errors.push('PAGEERROR: ' + e.message));
  page.on('console', m => { if (m.type()==='error') errors.push('CONSOLE.ERROR: ' + m.text()); });

  await page.goto(URL, { waitUntil: 'load', timeout: 30000 });
  await new Promise(r => setTimeout(r, 5000));   // let the force sim settle

  const read = () => page.evaluate(() => ({
    cam: (window.__camxyz ? window.__camxyz() : '(no hook)'),
    flyBtnText: (document.getElementById('flyBtn')||{}).textContent || '(no btn)',
    hasForceGraph: typeof window.ForceGraph3D,
    labelCount: document.querySelectorAll('#labels .nlab').length,
    visibleLabels: [...document.querySelectorAll('#labels .nlab')].filter(e=>e.style.display!=='none').length,
  }));

  const before = await read();
  console.log('=== ON LOAD ===');
  console.log(JSON.stringify(before));

  // dismiss the help overlay the way a user does, then click the Fly button
  await page.evaluate(() => { const h=document.getElementById('help'); if(h){h.style.display='none'; h.classList.add('hide');} });
  await page.click('#flyBtn');
  const enabled = await read();
  console.log('\n=== FLY ENABLED ===');
  console.log('flyBtn text:', enabled.flyBtnText, '| fly flag:', enabled.cam[3]);

  // hold each WASD key in turn and measure camera movement
  for (const key of ['w','s','d','a']) {
    const a = (await read()).cam;
    await page.keyboard.down(key);
    await new Promise(r => setTimeout(r, 900));
    await page.keyboard.up(key);
    await new Promise(r => setTimeout(r, 150));
    const b = (await read()).cam;
    const moved = Math.hypot(b[0]-a[0], b[1]-a[1], b[2]-a[2]);
    console.log(`key ${key.toUpperCase()}: ${a.slice(0,3)} -> ${b.slice(0,3)}  (moved ${moved.toFixed(0)} units)`);
  }
  const after = await read();
  console.log('visible labels:', after.visibleLabels, '/', after.labelCount);

  console.log('\n=== ERRORS (' + errors.length + ') ===');
  errors.slice(0, 15).forEach(e => console.log(e));

  await browser.close();
})().catch(e => { console.error('TEST CRASHED:', e.message); process.exit(1); });
