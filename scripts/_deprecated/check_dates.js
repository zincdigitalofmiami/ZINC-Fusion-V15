const puppeteer = require('puppeteer');
const path = require('path');
require('dotenv').config({ path: path.join(__dirname, '../frontend/.env.local') });

const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));

async function check() {
  const user = process.env.PROFARMER_USERNAME;
  const pass = process.env.PROFARMER_PASSWORD;

  const browser = await puppeteer.launch({ headless: 'new', args: ['--no-sandbox'] });
  const page = await browser.newPage();
  await page.setUserAgent('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36');

  // Login
  await page.goto('https://www.profarmer.com/r/sign-in', { waitUntil: 'networkidle2' });
  await sleep(1000);
  await page.evaluate(() => {
    const forms = document.querySelectorAll('form');
    for (const form of forms) {
      const e = form.querySelector('input[type="email"]');
      if (e && form.querySelector('input[type="password"]')) { e.focus(); return; }
    }
  });
  await page.keyboard.type(user, { delay: 80 });
  await page.keyboard.press('Tab');
  await page.keyboard.type(pass, { delay: 80 });
  await page.keyboard.press('Enter');
  await sleep(5000);

  // Check a few articles
  const urls = [
    'https://www.profarmer.com/news/first-thing-today/first-thing-today-trump-picks-warsh-chair-fed-markets-react',
    'https://www.profarmer.com/news/first-thing-today/first-thing-today-grains-see-follow-through-buying-overnight',
  ];

  for (const url of urls) {
    console.log('\n=== ' + url.split('/').pop() + ' ===');
    await page.goto(url, { waitUntil: 'networkidle2' });
    await sleep(500);

    const dates = await page.evaluate(() => {
      const results = {};
      
      // Meta tag
      const meta = document.querySelector('meta[property="article:published_time"]');
      results.meta = meta?.getAttribute('content') || 'NOT FOUND';
      
      // JSON-LD
      const scripts = document.querySelectorAll('script[type="application/ld+json"]');
      for (const s of scripts) {
        try {
          const json = JSON.parse(s.textContent);
          if (json.datePublished) results.jsonld = json.datePublished;
          if (json['@graph']) {
            for (const item of json['@graph']) {
              if (item.datePublished) results.jsonld = item.datePublished;
            }
          }
        } catch {}
      }
      
      // Visible date on page
      const dateEl = document.querySelector('.Page-datePublished, time, .date');
      results.visible = dateEl?.textContent?.trim() || 'NOT FOUND';
      
      // Page title
      results.title = document.title;
      
      return results;
    });

    console.log('META TAG:', dates.meta);
    console.log('JSON-LD:', dates.jsonld || 'NOT FOUND');
    console.log('VISIBLE:', dates.visible);
    console.log('TITLE:', dates.title);
  }

  await browser.close();
}

check().catch(console.error);
