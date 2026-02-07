const puppeteer = require('puppeteer');
const path = require('path');
require('dotenv').config({ path: path.join(__dirname, '../frontend/.env.local') });

const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));

async function findDate() {
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

  // Go to an article
  await page.goto('https://www.profarmer.com/news/first-thing-today/first-thing-today-trump-picks-warsh-chair-fed-markets-react', { waitUntil: 'networkidle2' });
  await sleep(1000);

  // Find ALL elements that might contain a date
  const dateInfo = await page.evaluate(() => {
    const results = [];
    
    // Check all elements with common date-related patterns
    const allElements = document.querySelectorAll('*');
    for (const el of allElements) {
      const text = el.textContent?.trim();
      const className = el.className || '';
      
      // Look for date patterns in text
      if (text && text.length < 100) {
        // Check for month names
        if (text.match(/January|February|March|April|May|June|July|August|September|October|November|December/i)) {
          results.push({
            tag: el.tagName,
            class: className.toString().slice(0, 50),
            text: text.slice(0, 80),
            datetime: el.getAttribute('datetime')
          });
        }
        // Check for date patterns like 1/30/2026 or 01-30-2026
        if (text.match(/\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4}/)) {
          results.push({
            tag: el.tagName,
            class: className.toString().slice(0, 50),
            text: text.slice(0, 80),
            datetime: el.getAttribute('datetime')
          });
        }
      }
    }
    
    // Also check meta tags
    const metaTags = document.querySelectorAll('meta');
    for (const m of metaTags) {
      const prop = m.getAttribute('property') || m.getAttribute('name') || '';
      const content = m.getAttribute('content') || '';
      if (prop.match(/date|time|publish/i) || content.match(/\d{4}-\d{2}-\d{2}/)) {
        results.push({
          tag: 'META',
          class: prop,
          text: content.slice(0, 80),
          datetime: null
        });
      }
    }
    
    // Check JSON-LD
    const scripts = document.querySelectorAll('script[type="application/ld+json"]');
    for (const s of scripts) {
      try {
        const json = JSON.parse(s.textContent);
        if (json.datePublished) {
          results.push({ tag: 'JSON-LD', class: 'datePublished', text: json.datePublished, datetime: null });
        }
        if (json.dateModified) {
          results.push({ tag: 'JSON-LD', class: 'dateModified', text: json.dateModified, datetime: null });
        }
      } catch {}
    }
    
    return results;
  });

  console.log('=== DATE ELEMENTS FOUND ===');
  dateInfo.forEach((d, i) => {
    console.log(`${i+1}. <${d.tag} class="${d.class}">`);
    console.log(`   text: "${d.text}"`);
    if (d.datetime) console.log(`   datetime: "${d.datetime}"`);
  });

  await browser.close();
}

findDate().catch(console.error);
