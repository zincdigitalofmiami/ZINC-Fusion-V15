const puppeteer = require('puppeteer');
const path = require('path');
require('dotenv').config({ path: path.join(__dirname, '../frontend/.env.local') });

const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));

async function test() {
  const user = process.env.PROFARMER_USERNAME;
  const pass = process.env.PROFARMER_PASSWORD;

  const browser = await puppeteer.launch({ 
    headless: 'new', 
    args: ['--no-sandbox'] 
  });
  const page = await browser.newPage();
  await page.setUserAgent('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36');

  console.log('Going to login page...');
  await page.goto('https://www.profarmer.com/r/sign-in', { waitUntil: 'networkidle2' });
  await sleep(2000);

  // Fill form via JavaScript
  console.log('Filling form via JS...');
  await page.evaluate((u, p) => {
    const forms = document.querySelectorAll('form');
    for (const form of forms) {
      const email = form.querySelector('input[type="email"]');
      const pass = form.querySelector('input[type="password"]');
      if (email && pass) {
        email.value = u;
        email.dispatchEvent(new Event('input', { bubbles: true }));
        pass.value = p;
        pass.dispatchEvent(new Event('input', { bubbles: true }));
        
        // Find submit button
        const btn = form.querySelector('button[type="submit"], input[type="submit"], button');
        console.log('Found button:', btn?.tagName, btn?.textContent);
        if (btn) btn.click();
        else form.submit();
        break;
      }
    }
  }, user, pass);

  // Wait for navigation
  console.log('Waiting...');
  await sleep(10000);
  
  console.log('Final URL:', page.url());
  console.log('Login success:', !page.url().includes('sign-in'));

  await browser.close();
}

test().catch(console.error);
