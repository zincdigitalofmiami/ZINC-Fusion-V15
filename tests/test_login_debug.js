const puppeteer = require('puppeteer');
const path = require('path');
require('dotenv').config({ path: path.join(__dirname, '../frontend/.env.local') });

const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));

async function test() {
  const user = process.env.PROFARMER_USERNAME;
  const pass = process.env.PROFARMER_PASSWORD;

  console.log('Username:', user);
  console.log('Password length:', pass?.length);

  const browser = await puppeteer.launch({ headless: 'new', args: ['--no-sandbox'] });
  const page = await browser.newPage();
  await page.setUserAgent('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36');

  // Go to login
  console.log('\\n1. Going to login page...');
  await page.goto('https://www.profarmer.com/r/sign-in', { waitUntil: 'networkidle2' });
  console.log('   URL:', page.url());
  await sleep(2000);

  // Find email input directly
  console.log('\\n2. Looking for email input...');
  const emailInputs = await page.$$('input[type="email"]');
  console.log('   Found', emailInputs.length, 'email inputs');

  // Focus on the correct email field (form-based)
  console.log('\\n3. Focusing on form email field...');
  const focused = await page.evaluate(() => {
    const forms = document.querySelectorAll('form');
    for (const form of forms) {
      const email = form.querySelector('input[type="email"]');
      const pass = form.querySelector('input[type="password"]');
      if (email && pass) {
        email.focus();
        email.click();
        return { found: true, formAction: form.action };
      }
    }
    return { found: false };
  });
  console.log('   Focus result:', focused);
  await sleep(500);

  // Type username
  console.log('\\n4. Typing username...');
  await page.keyboard.type(user, { delay: 100 });
  await sleep(500);

  // Tab to password
  console.log('\\n5. Pressing Tab...');
  await page.keyboard.press('Tab');
  await sleep(500);

  // Type password
  console.log('\\n6. Typing password...');
  await page.keyboard.type(pass, { delay: 100 });
  await sleep(500);

  // Screenshot before submit
  await page.screenshot({ path: '/tmp/pf_before_submit.png' });
  console.log('   Screenshot: /tmp/pf_before_submit.png');

  // Submit
  console.log('\\n7. Pressing Enter...');
  await page.keyboard.press('Enter');

  // Wait for navigation
  console.log('\\n8. Waiting for navigation...');
  await sleep(8000);

  // Check result
  const finalUrl = page.url();
  console.log('\\n9. Final URL:', finalUrl);
  console.log('   Login success:', !finalUrl.includes('sign-in'));

  // Screenshot after
  await page.screenshot({ path: '/tmp/pf_after_submit.png' });
  console.log('   Screenshot: /tmp/pf_after_submit.png');

  // Check for errors
  const errorText = await page.evaluate(() => {
    const errors = document.querySelectorAll('.error, .alert-danger, [class*="error"]');
    return Array.from(errors).map(e => e.textContent?.trim()).filter(t => t);
  });
  if (errorText.length) {
    console.log('   Errors found:', errorText);
  }

  await browser.close();
}

test().catch(console.error);
