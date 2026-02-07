const puppeteer = require('puppeteer');
const path = require('path');
require('dotenv').config({ path: path.join(__dirname, '../frontend/.env.local') });

const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));

async function test() {
  const user = process.env.PROFARMER_USERNAME;
  const pass = process.env.PROFARMER_PASSWORD;

  const browser = await puppeteer.launch({ 
    headless: 'new', 
    args: ['--no-sandbox', '--disable-setuid-sandbox'] 
  });
  const page = await browser.newPage();
  await page.setUserAgent('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36');

  console.log('Going to login page...');
  await page.goto('https://www.profarmer.com/r/sign-in', { waitUntil: 'networkidle2' });
  await sleep(2000);

  // Use page.type with selectors directly
  console.log('Filling email...');
  await page.type('form input[type="email"]', user, { delay: 50 });
  await sleep(300);

  console.log('Filling password...');
  await page.type('form input[type="password"]', pass, { delay: 50 });
  await sleep(300);

  // Find and click submit button
  console.log('Clicking submit...');
  await Promise.all([
    page.waitForNavigation({ waitUntil: 'networkidle2', timeout: 30000 }).catch(() => {}),
    page.click('form button[type="submit"], form input[type="submit"]'),
  ]);

  await sleep(5000);
  console.log('Final URL:', page.url());
  console.log('Login success:', !page.url().includes('sign-in'));

  if (!page.url().includes('sign-in')) {
    // Test accessing an article
    console.log('\\nTrying to access article...');
    await page.goto('https://www.profarmer.com/news/first-thing-today/first-thing-today-trump-picks-warsh-chair-fed-markets-react', { waitUntil: 'networkidle2' });
    
    const content = await page.evaluate(() => {
      const el = document.querySelector('.Page-articleBody, .Page-content, article');
      return el?.textContent?.length || 0;
    });
    console.log('Article content length:', content);
  }

  await browser.close();
}

test().catch(console.error);
