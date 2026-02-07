const puppeteer = require('puppeteer');
const path = require('path');
require('dotenv').config({ path: path.join(__dirname, '../frontend/.env.local') });

const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));

async function inspect() {
  const user = process.env.PROFARMER_USERNAME;
  const pass = process.env.PROFARMER_PASSWORD;

  const browser = await puppeteer.launch({
    headless: 'new',
    args: ['--no-sandbox'],
    defaultViewport: { width: 1920, height: 1080 },
  });

  const page = await browser.newPage();
  await page.setUserAgent('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36');

  // LOGIN
  await page.goto('https://www.profarmer.com/r/sign-in', { waitUntil: 'networkidle2' });
  await sleep(1000);
  await page.evaluate(() => {
    const forms = document.querySelectorAll('form');
    for (const form of forms) {
      const e = form.querySelector('input[type="email"]');
      if (e && form.querySelector('input[type="password"]')) { e.focus(); return; }
    }
  });
  await page.keyboard.type(user, { delay: 40 });
  await page.keyboard.press('Tab');
  await page.keyboard.type(pass, { delay: 40 });
  await page.keyboard.press('Enter');
  await sleep(5000);
  console.log('Logged in, URL:', page.url());

  // Go to topics page
  await page.goto('https://www.profarmer.com/topics/first-thing-today', { waitUntil: 'networkidle2' });
  await sleep(1000);

  // Get ALL links
  const allLinks = await page.evaluate(() => {
    return Array.from(document.querySelectorAll('a')).map(a => ({
      href: a.href,
      text: a.textContent?.trim()?.slice(0, 80)
    })).filter(l => l.href.includes('profarmer.com') && l.text && l.text.length > 5);
  });

  console.log('\n=== ALL PROFARMER LINKS ON PAGE ===');
  allLinks.slice(0, 50).forEach((l, i) => {
    console.log(`${i+1}. ${l.href}`);
    console.log(`   "${l.text}"`);
  });

  // Get page HTML structure
  console.log('\n=== PAGE STRUCTURE ===');
  const structure = await page.evaluate(() => {
    const main = document.querySelector('main') || document.body;
    const classes = new Set();
    main.querySelectorAll('*').forEach(el => {
      if (el.className && typeof el.className === 'string') {
        el.className.split(' ').forEach(c => {
          if (c.length > 3) classes.add(c);
        });
      }
    });
    return Array.from(classes).sort().slice(0, 100);
  });
  console.log('CSS classes found:', structure.join(', '));

  await browser.close();
}

inspect().catch(console.error);
