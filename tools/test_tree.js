const puppeteer = require('puppeteer-core');
const CHROME = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const URL = 'file:///' + 'C:/tree/troy-family-tree-research/data/exports/tree.html';

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

  const st0 = await page.evaluate(() => window.__tree.state());
  console.log('initial state:', JSON.stringify(st0));

  // zoom in with the wheel over the middle of the canvas
  await page.mouse.move(640, 400);
  await page.evaluate(() => { const cv=document.getElementById('cv');
    for(let i=0;i<5;i++) cv.dispatchEvent(new WheelEvent('wheel',{deltaY:-100,clientX:640,clientY:400,bubbles:true,cancelable:true})); });
  await new Promise(r => setTimeout(r, 200));
  const st1 = await page.evaluate(() => window.__tree.state());
  console.log('after zoom-in:', JSON.stringify(st1));
  console.log('ZOOM WORKS:', st1.k > st0.k);

  // back to the default framing for hit-testing
  await page.evaluate(() => window.__tree.frameRoot());
  await new Promise(r => setTimeout(r, 150));

  // the root (You) should be hit-testable at its on-screen position after frameRoot
  const rootHit = await page.evaluate(() => {
    const st = window.__tree.state();          // root is at world (0,0) -> screen (st.x, st.y)
    return window.__tree.hit(st.x, st.y);
  });
  console.log('root hit (bottom-center):', JSON.stringify(rootHit));

  // probe a grid for boxes; count hits, with-story, notable, photo
  const probe = await page.evaluate(() => {
    let n=0, withId=0, notable=0, photo=0, names=new Set();
    for (let y=20; y<800; y+=5)
      for (let x=5; x<1275; x+=7){ const p=window.__tree.hit(x,y); if(p){ n++; names.add(p.name);
        if(p.id) withId++; if(p.notable) notable++; if(p.photo) photo++; } }
    return { hits:n, distinct:names.size, withId, notable, photo };
  });
  console.log('hit-test probe:', JSON.stringify(probe));

  // whole-tree fit should zoom out (smaller k) and keep boxes hittable
  await page.evaluate(() => window.__tree.fitAll());
  await new Promise(r => setTimeout(r, 150));
  const st2 = await page.evaluate(() => window.__tree.state());
  console.log('after fitAll:', JSON.stringify(st2), 'ZOOMED OUT:', st2.k < st0.k);

  // couple layout: the two parents straddle the child (you) symmetrically
  const px = await page.evaluate(() => window.__tree.parentsX());
  const sym = px.parents.length===2
    && Math.min(...px.parents) < px.root && Math.max(...px.parents) > px.root
    && Math.abs((px.parents[0]-px.root) + (px.parents[1]-px.root)) < 2;  // symmetric about the child
  console.log('parents straddle child:', JSON.stringify(px), 'SYMMETRIC:', sym);

  console.log('\nERRORS (' + errors.length + '):'); errors.slice(0,10).forEach(e=>console.log(' ',e));
  await browser.close();
  process.exit((errors.length || !sym) ? 1 : 0);
})().catch(e => { console.error('TEST CRASHED:', e.message); process.exit(1); });
