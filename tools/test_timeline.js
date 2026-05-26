const puppeteer = require('puppeteer-core');
const CHROME = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
const URL = 'file:///' + 'C:/troytree-dist/pub/timeline.html';

(async () => {
  const browser = await puppeteer.launch({ executablePath: CHROME, headless: 'new',
    args: ['--no-sandbox','--enable-webgl','--use-gl=angle','--use-angle=swiftshader','--enable-unsafe-swiftshader','--window-size=1280,800'] });
  const page = await browser.newPage();
  await page.setViewport({ width: 1280, height: 800 });
  const errors = [];
  page.on('pageerror', e => errors.push('PAGEERROR: ' + e.message));
  page.on('console', m => { if (m.type()==='error') errors.push('CONSOLE.ERROR: ' + m.text()); });
  await page.goto(URL, { waitUntil: 'load', timeout: 30000 });
  await new Promise(r => setTimeout(r, 1500));

  const st0 = await page.evaluate(() => window.__tl.state());
  console.log('initial state:', JSON.stringify(st0));

  // zoom in with the wheel over the middle of the canvas
  await page.mouse.move(640, 400);
  for (let i=0;i<5;i++) await page.evaluate(() => window.dispatchEvent ? null : null);
  await page.evaluate(() => { const cv=document.getElementById('tl');
    for(let i=0;i<5;i++) cv.dispatchEvent(new WheelEvent('wheel',{deltaY:-100,clientX:640,clientY:400,bubbles:true,cancelable:true})); });
  await new Promise(r => setTimeout(r, 300));
  const st1 = await page.evaluate(() => window.__tl.state());
  console.log('after zoom-in:', JSON.stringify(st1));
  console.log('ZOOM WORKS:', st1.scaleX > st0.scaleX);

  // probe a grid of points for hit-testing; report a found person with a story
  const probe = await page.evaluate(() => {
    let found=null, withStory=null, n=0;
    for (let y=40; y<780 && n<4000; y+=6)
      for (let x=10; x<1270; x+=8){ const p=window.__tl.hit(x,y); if(p){ n++; found=found||{n:p.n,st:p.st,id:!!p.id};
        if(p.st && !withStory) withStory={n:p.n}; } }
    return { hits:n, found, withStory };
  });
  console.log('hit-test probe:', JSON.stringify(probe));

  console.log('\nERRORS (' + errors.length + '):'); errors.slice(0,10).forEach(e=>console.log(' ',e));
  await browser.close();
})().catch(e => { console.error('TEST CRASHED:', e.message); process.exit(1); });
