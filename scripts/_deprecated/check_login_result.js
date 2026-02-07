const puppeteer = require('puppeteer');
const path = require('path');
require('dotenv').config({ path: path.join(__dirname, '../frontend/.env.local') });

const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));

async function checkLogin() {
  const user = process.env.PROFARMER_USERNAME;
  const pass = process.env.PROFARMER_PASSWORD;

  console.log(`Username: ${user}`);
  console.log(`Password: ${pass ? '[SET - ' + pass.length + ' chars]' : '[NOT SET]'}`);

  const browser = await puppeteer.launch({
    headless: 'new',
    args: ['--no-sandbox', '--disable-setuid-sandbox'],
    defaultViewport: { width: 1920, height: 1080 },
  });

  const page = await browser.newPage();
  await page.setUserAgent('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36');

  console.log('Going to login page...');
  await page.goto('https://www.profarmer.com/r/sign-in', { waitUntil: 'networkidle2' });
  await sleep(1000);

  // Type credentials manually character by character
  console.log('Finding and focusing email field...');
  
  // Click on the email field in the main form (not the search box)
  const clicked = await page.evaluate(() => {
    const forms = document.querySelectorAll('form');
    for (const form of forms) {
      const emailInput = form.querySelector('input[type="email"]');
      const passInput = form.querySelector('input[type="password"]');
      if (emailInput && passInput) {
        emailInput.focus();
        emailInput.click();
        return true;
      }
    }
    return false;
  });
  
  if (!clicked) {
    console.log('Could not find login form!');
    await browser.close();
    return;
  }

  console.log('Typing email...');
  await page.keyboard.type(user, { delay: 100 });
  await sleep(500);

  console.log('Pressing Tab to go to password...');
  await page.keyboard.press('Tab');
  await sleep(500);

  console.log('Typing password...');
  await page.keyboard.type(pass, { delay: 100 });
  await sleep(500);

  console.log('Pressing Enter to submit...');
  await page.keyboard.press('Enter');
  
  // Wait for navigation
  console.log('Waiting for response...');
  await sleep(8000);

  // Check current URL and page content
  const url = page.url();
  console.log('Current URL:', url);

  // Check for error messages
  const errorMsg = await page.evaluate(() => {
    const errorEls = document.querySelectorAll('.error, .alert, [class*="error"], [class*="alert"]');
    for (const el of errorEls) {
      const text = el.textContent?.trim();
      if (text && text.length > 5 && text.length < 200) {
        return text;
      }
    }
    return null;
  });

  if (errorMsg) {
    console.log('Error message on page:', errorMsg);
  }

  // Check if logged in by looking for user menu or logout option
  const isLoggedIn = await page.evaluate(() => {
    return !!(document.querySelector('[href*="logout"]') || 
              document.querySelector('[href*="sign-out"]') ||
              document.querySelector('.user-menu') ||
              document.querySelector('[class*="logged-in"]'));
  });

  console.log('Logged in:', isLoggedIn);
  console.log('On login page:', url.includes('sign-in'));

  await page.screenshot({ path: '/tmp/profarmer_final.png' });
  
  await browser.close();
}

checkLogin().catch(console.error);
