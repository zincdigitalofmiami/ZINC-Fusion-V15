const puppeteer = require('puppeteer');
const path = require('path');
require('dotenv').config({ path: path.join(__dirname, '../frontend/.env.local') });

const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));

async function debug() {
  const user = process.env.PROFARMER_USERNAME;
  const pass = process.env.PROFARMER_PASSWORD;

  const browser = await puppeteer.launch({ headless: 'new', args: ['--no-sandbox'] });
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
  await page.keyboard.type(user, { delay: 30 });
  await page.keyboard.press('Tab');
  await page.keyboard.type(pass, { delay: 30 });
  await page.keyboard.press('Enter');
  await sleep(5000);
  console.log('Logged in, URL:', page.url());

  // Go to an article
  const articleUrl = 'https://www.profarmer.com/news/first-thing-today/first-thing-today-trump-picks-warsh-chair-fed-markets-react';
  console.log('\\nGoing to article:', articleUrl);
  await page.goto(articleUrl, { waitUntil: 'networkidle2' });
  await sleep(1000);

  // Debug content extraction
  const debug = await page.evaluate(() => {
    const selectors = [
      '.RichTextArticleBody',
      '.RichTextBody',
      '.ArticleBody',
      'article .content',
      'article',
      '.Page-article',
      '.Page-content',
      'main',
    ];
    
    const results = [];
    for (const sel of selectors) {
      const el = document.querySelector(sel);
      if (el) {
        results.push({
          selector: sel,
          exists: true,
          length: el.textContent?.length || 0,
          preview: el.textContent?.trim().slice(0, 200)
        });
      } else {
        results.push({ selector: sel, exists: false });
      }
    }
    return results;
  });

  console.log('\\n=== CONTENT SELECTORS ===');
  debug.forEach(d => {
    console.log(`${d.selector}: ${d.exists ? `EXISTS (${d.length} chars)` : 'NOT FOUND'}`);
    if (d.preview) console.log(`  Preview: "${d.preview.slice(0, 100)}..."`);
  });

  // Also check the raw page HTML structure
  const mainContent = await page.evaluate(() => {
    const main = document.querySelector('main');
    if (!main) return 'No main element';
    
    // Get child element types
    const children = Array.from(main.children).map(c => ({
      tag: c.tagName,
      class: c.className?.toString().slice(0, 50),
      textLen: c.textContent?.length
    }));
    return children;
  });

  console.log('\\n=== MAIN ELEMENT CHILDREN ===');
  console.log(JSON.stringify(mainContent, null, 2));

  await browser.close();
}

debug().catch(console.error);
