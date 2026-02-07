const puppeteer = require('puppeteer');
const path = require('path');
require('dotenv').config({ path: path.join(__dirname, '../frontend/.env.local') });

const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));

async function fullTest() {
  const user = process.env.PROFARMER_USERNAME;
  const pass = process.env.PROFARMER_PASSWORD;

  const browser = await puppeteer.launch({
    headless: 'new',
    args: ['--no-sandbox', '--disable-setuid-sandbox'],
    defaultViewport: { width: 1920, height: 1080 },
  });

  const page = await browser.newPage();
  await page.setUserAgent('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36');

  // LOGIN
  console.log('=== LOGGING IN ===');
  await page.goto('https://www.profarmer.com/r/sign-in', { waitUntil: 'networkidle2' });
  await sleep(1000);

  await page.evaluate(() => {
    const forms = document.querySelectorAll('form');
    for (const form of forms) {
      const emailInput = form.querySelector('input[type="email"]');
      if (emailInput && form.querySelector('input[type="password"]')) {
        emailInput.focus();
        emailInput.click();
        return;
      }
    }
  });

  await page.keyboard.type(user, { delay: 80 });
  await sleep(300);
  await page.keyboard.press('Tab');
  await sleep(300);
  await page.keyboard.type(pass, { delay: 80 });
  await sleep(500);
  await page.keyboard.press('Enter');
  await sleep(5000);

  const url = page.url();
  console.log('After login URL:', url);
  
  if (url.includes('sign-in')) {
    console.log('LOGIN FAILED!');
    await browser.close();
    return;
  }
  console.log('LOGIN SUCCESS!\n');

  // SCRAPE REPORTS
  const reports = [
    { name: 'Daily Advice Monitor', url: 'https://www.profarmer.com/daily-advice-monitor/' },
    { name: 'First Thing Today', url: 'https://www.profarmer.com/first-thing-today/' },
    { name: 'Washington/Ag Policy', url: 'https://www.profarmer.com/washington-ag-policy/' },
    { name: 'After the Bell', url: 'https://www.profarmer.com/after-the-bell/' },
  ];

  for (const report of reports) {
    console.log(`=== ${report.name} ===`);
    await page.goto(report.url, { waitUntil: 'networkidle2', timeout: 30000 });
    await sleep(1000);

    const articles = await page.evaluate(() => {
      const results = [];
      const links = document.querySelectorAll('a[href*="profarmer.com"]');
      const seen = new Set();
      
      for (const link of links) {
        const href = link.href;
        if (seen.has(href)) continue;
        if (href.includes('/r/') || href.includes('sign-in') || href.includes('subscribe')) continue;
        
        const title = link.textContent?.trim();
        if (!title || title.length < 15) continue;
        
        // Check if it looks like an article link
        if (href.match(/\/\d{4}\/\d{2}\//) || href.includes('/topics/')) {
          seen.add(href);
          results.push({ title: title.slice(0, 80), url: href });
        }
      }
      return results.slice(0, 5);
    });

    console.log(`Found ${articles.length} articles:`);
    articles.forEach((a, i) => console.log(`  ${i+1}. ${a.title}`));
    console.log('');
  }

  await browser.close();
  console.log('=== FULL TEST COMPLETE ===');
}

fullTest().catch(console.error);
