const puppeteer = require('puppeteer');
const path = require('path');
require('dotenv').config({ path: path.join(__dirname, '../frontend/.env.local') });

const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));

async function diagnose() {
  const user = process.env.PROFARMER_USERNAME;
  const pass = process.env.PROFARMER_PASSWORD;

  const browser = await puppeteer.launch({
    headless: 'new',
    args: ['--no-sandbox'],
    defaultViewport: { width: 1920, height: 1080 },
  });

  const page = await browser.newPage();
  await page.setUserAgent('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36');

  console.log('🔐 Logging in...');
  await page.goto('https://www.profarmer.com/r/sign-in', { waitUntil: 'networkidle2' });
  await sleep(1500);

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
  await sleep(500);
  await page.keyboard.press('Tab');
  await sleep(500);
  await page.keyboard.type(pass, { delay: 80 });
  await sleep(500);
  await page.keyboard.press('Enter');
  await sleep(8000);

  console.log('✅ Logged in\n');

  // Get a sample article from the homepage
  await page.goto('https://www.profarmer.com/news', { waitUntil: 'networkidle2' });
  await sleep(1000);

  const firstArticle = await page.evaluate(() => {
    const links = document.querySelectorAll('a[href*="/news/"]');
    for (const a of links) {
      if (a.href.includes('/r/') || a.href.includes('subscribe')) continue;
      const pathParts = a.href.replace('https://www.profarmer.com', '').split('/').filter(Boolean);
      if (pathParts.length < 3) continue;
      return { url: a.href, title: a.textContent?.trim() };
    }
    return null;
  });

  if (!firstArticle) {
    console.log('❌ No articles found');
    await browser.close();
    return;
  }

  console.log('📰 Sample article:', firstArticle.title);
  console.log('🔗 URL:', firstArticle.url);
  console.log('\n' + '='.repeat(60));

  await page.goto(firstArticle.url, { waitUntil: 'networkidle2' });
  await sleep(1000);

  const diagnostics = await page.evaluate(() => {
    const result = {
      url: window.location.href,
      meta: {},
      jsonLd: [],
      pageElements: {},
      content: {},
      htmlSnippet: ''
    };

    // Meta tags
    const metaDate = document.querySelector('meta[property="article:published_time"]');
    if (metaDate) result.meta.articlePublishedTime = metaDate.getAttribute('content');
    
    // JSON-LD
    const scripts = document.querySelectorAll('script[type="application/ld+json"]');
    scripts.forEach(s => {
      try {
        const json = JSON.parse(s.textContent);
        result.jsonLd.push(json);
      } catch {}
    });

    // Page elements
    const selectors = {
      '.Page-datePublished': 'Page-datePublished',
      'time[datetime]': 'time-datetime',
      '.Page-authorName': 'Page-authorName',
      '.Page-articleBody': 'Page-articleBody',
      '.RichTextArticleBody': 'RichTextArticleBody',
      '.Page-content': 'Page-content',
    };
    
    for (const [selector, name] of Object.entries(selectors)) {
      const el = document.querySelector(selector);
      if (el) {
        result.pageElements[name] = {
          textContent: el.textContent?.trim().slice(0, 200),
          innerHTML: el.innerHTML?.slice(0, 500),
          attributes: {}
        };
        for (const attr of el.attributes) {
          result.pageElements[name].attributes[attr.name] = attr.value;
        }
      }
    }

    // Content selectors
    const contentSelectors = [
      '.Page-articleBody',
      '.RichTextArticleBody',
      '.RichTextBody',
      '.Page-content article',
      'article .content',
      'article'
    ];
    
    for (const sel of contentSelectors) {
      const el = document.querySelector(sel);
      if (el) {
        result.content[sel] = {
          exists: true,
          length: el.textContent?.length,
          preview: el.textContent?.trim().slice(0, 300)
        };
      }
    }

    // HTML snippet
    result.htmlSnippet = document.body.innerHTML.slice(0, 2000);

    return result;
  });

  console.log('🔍 DIAGNOSTICS:\n');
  console.log('META TAGS:');
  console.log(JSON.stringify(diagnostics.meta, null, 2));
  
  console.log('\n📅 JSON-LD DATA:');
  console.log(JSON.stringify(diagnostics.jsonLd, null, 2));
  
  console.log('\n📍 PAGE ELEMENTS:');
  console.log(JSON.stringify(diagnostics.pageElements, null, 2));
  
  console.log('\n📝 CONTENT SELECTORS:');
  console.log(JSON.stringify(diagnostics.content, null, 2));
  
  console.log('\n🌐 HTML SNIPPET (first 500 chars):');
  console.log(diagnostics.htmlSnippet.slice(0, 500));

  await browser.close();
}

diagnose().catch(e => console.error('ERROR:', e));
