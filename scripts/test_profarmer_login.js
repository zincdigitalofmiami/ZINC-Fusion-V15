#!/usr/bin/env node
/**
 * Test ProFarmer login locally with Puppeteer
 */

const puppeteer = require('puppeteer');
const path = require('path');
require('dotenv').config({ path: path.join(__dirname, '../frontend/.env.local') });

const PROFARMER_LOGIN_URL = 'https://www.profarmer.com/r/sign-in';

const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));

async function testLogin() {
  const user = process.env.PROFARMER_USERNAME;
  const pass = process.env.PROFARMER_PASSWORD;

  if (!user || !pass) {
    console.error('PROFARMER_USERNAME and PROFARMER_PASSWORD required');
    process.exit(1);
  }

  console.log(`Testing login with username: ${user}`);

  const browser = await puppeteer.launch({
    headless: 'new',
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-gpu'],
    defaultViewport: { width: 1920, height: 1080 },
  });

  const page = await browser.newPage();
  
  await page.setUserAgent(
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
  );

  console.log('Navigating to login page...');
  await page.goto(PROFARMER_LOGIN_URL, { waitUntil: 'networkidle2', timeout: 60000 });
  await sleep(2000);

  // Check for captcha
  const hasCaptcha = await page.evaluate(() => {
    return !!document.querySelector('iframe[src*="recaptcha"], .g-recaptcha, [class*="captcha"]');
  });
  console.log('Captcha detected:', hasCaptcha);

  if (hasCaptcha) {
    console.log('CAPTCHA detected - cannot proceed without solving');
    await page.screenshot({ path: '/tmp/profarmer_captcha.png' });
    await browser.close();
    process.exit(1);
  }

  // Use page.evaluate to find and fill the visible login form
  console.log('Filling login form via JavaScript...');
  
  const loginResult = await page.evaluate(async (username, password) => {
    // Find all email inputs
    const emailInputs = document.querySelectorAll('input[name="email"], input[type="email"]');
    const passInputs = document.querySelectorAll('input[name="password"], input[type="password"]');
    
    // Find the visible ones (not in search box)
    let emailInput = null;
    let passInput = null;
    
    for (const el of emailInputs) {
      const rect = el.getBoundingClientRect();
      const style = window.getComputedStyle(el);
      if (rect.height > 0 && rect.width > 0 && style.display !== 'none' && style.visibility !== 'hidden') {
        // Check if it's in the main form (not header search)
        const parent = el.closest('form');
        if (parent && parent.querySelector('input[type="password"]')) {
          emailInput = el;
          break;
        }
      }
    }
    
    for (const el of passInputs) {
      const rect = el.getBoundingClientRect();
      const style = window.getComputedStyle(el);
      if (rect.height > 0 && rect.width > 0 && style.display !== 'none' && style.visibility !== 'hidden') {
        passInput = el;
        break;
      }
    }
    
    if (!emailInput || !passInput) {
      return { success: false, error: 'Could not find visible login form fields' };
    }
    
    // Set values directly
    emailInput.value = username;
    emailInput.dispatchEvent(new Event('input', { bubbles: true }));
    emailInput.dispatchEvent(new Event('change', { bubbles: true }));
    
    passInput.value = password;
    passInput.dispatchEvent(new Event('input', { bubbles: true }));
    passInput.dispatchEvent(new Event('change', { bubbles: true }));
    
    // Find submit button
    const form = emailInput.closest('form');
    const submitBtn = form?.querySelector('button[type="submit"], input[type="submit"]');
    
    if (submitBtn) {
      submitBtn.click();
      return { success: true, message: 'Form submitted' };
    }
    
    return { success: false, error: 'Could not find submit button' };
  }, user, pass);

  console.log('Login form result:', loginResult);

  // Wait for navigation
  await sleep(5000);
  
  const finalUrl = page.url();
  console.log('Final URL:', finalUrl);
  
  await page.screenshot({ path: '/tmp/profarmer_result.png' });
  console.log('Screenshot saved to /tmp/profarmer_result.png');
  
  const loginSuccess = !finalUrl.includes('sign-in') && !finalUrl.includes('login');
  console.log('LOGIN SUCCESSFUL:', loginSuccess);

  if (loginSuccess) {
    // Try to access a report page
    console.log('\nTesting access to Daily Advice Monitor...');
    await page.goto('https://www.profarmer.com/daily-advice-monitor/', { waitUntil: 'networkidle2', timeout: 30000 });
    
    const pageTitle = await page.title();
    console.log('Page title:', pageTitle);
    
    const articleCount = await page.evaluate(() => {
      return document.querySelectorAll('article, .post, [class*="article"]').length;
    });
    console.log('Articles found:', articleCount);
    
    await page.screenshot({ path: '/tmp/profarmer_content.png' });
    console.log('Content screenshot: /tmp/profarmer_content.png');
  }

  await browser.close();
  console.log('\nTest complete.');
  process.exit(loginSuccess ? 0 : 1);
}

testLogin().catch(err => {
  console.error('Test failed:', err);
  process.exit(1);
});
