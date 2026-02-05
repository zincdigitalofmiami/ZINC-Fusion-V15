const puppeteer = require('puppeteer');
const path = require('path');
require('dotenv').config({ path: path.join(__dirname, '../frontend/.env.local') });

const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));

async function test() {
  const user = process.env.PROFARMER_USERNAME;
  const pass = process.env.PROFARMER_PASSWORD;

  const browser = await puppeteer.launch({
    headless: 'new',
    args: ['--no-sandbox'],
  });

  const page = await browser.newPage();

  // Login
  console.log('🔐 Logging in...');
  await page.goto('https://www.profarmer.com/r/sign-in', { waitUntil: 'networkidle2' });
  await sleep(1500);
  
  await page.evaluate(() => {
    const forms = document.querySelectorAll('form');
    for (const form of forms) {
      const emailInput = form.querySelector('input[type="email"]');
      if (emailInput) {
        emailInput.focus();
        return;
      }
    }
  });
  
  await page.keyboard.type(user, { delay: 80 });
  await page.keyboard.press('Tab');
  await sleep(500);
  await page.keyboard.type(pass, { delay: 80 });
  await page.keyboard.press('Enter');
  await sleep(8000);

  console.log('✅ Logged in\n');

  // Get articles from page 5 (older content)
  console.log('📄 Getting articles from page 5...\n');
  await page.goto('https://www.profarmer.com/news?page=5', { waitUntil: 'networkidle2' });
  await sleep(1000);

  const articles = await page.evaluate(() => {
    const results = [];
    document.querySelectorAll('a[href*="/news/"]').forEach(a => {
      if (a.href.includes('/r/') || a.href.includes('subscribe') || a.href.includes('/topics/')) return;
      const parts = a.href.replace('https://www.profarmer.com', '').split('/').filter(Boolean);
      if (parts.length < 3) return;
      const title = a.textContent?.trim();
      if (title && title.length > 15 && title.length < 200) {
        results.push({ url: a.href, title });
      }
    });
    return results.slice(0, 5);
  });

  console.log(`Found ${articles.length} articles to test:\n`);

  for (let i = 0; i < articles.length; i++) {
    const article = articles[i];
    console.log(`${i + 1}. ${article.title}`);
    console.log(`   URL: ${article.url}`);

    await page.goto(article.url, { waitUntil: 'networkidle2', timeout: 25000 });
    await sleep(500);

    const data = await page.evaluate(() => {
      // Date extraction
      let date = '';
      const meta = document.querySelector('meta[property="article:published_time"]');
      if (meta) date = meta.getAttribute('content');

      if (!date) {
        const scripts = document.querySelectorAll('script[type="application/ld+json"]');
        for (const s of scripts) {
          try {
            const json = JSON.parse(s.textContent);
            if (json.datePublished) {
              date = json.datePublished;
              break;
            }
          } catch {}
        }
      }

      // Content extraction
      let content = '';
      const contentEl = document.querySelector('.Page-articleBody');
      if (contentEl) content = contentEl.textContent?.trim();

      // Author extraction
      let author = '';
      const scripts = document.querySelectorAll('script[type="application/ld+json"]');
      for (const s of scripts) {
        try {
          const json = JSON.parse(s.textContent);
          if (json.author && json.author[0] && json.author[0].name) {
            author = json.author[0].name;
            break;
          }
        } catch {}
      }

      return { date, contentLength: content.length, author };
    });

    if (data.date) {
      const parsed = new Date(data.date);
      const formatted = parsed.toISOString().split('T')[0];
      console.log(`   ✅ Date: ${formatted}`);
    } else {
      console.log(`   ❌ No date found`);
    }

    console.log(`   📝 Content: ${data.contentLength} chars`);
    console.log(`   ✍️  Author: ${data.author || 'N/A'}`);
    console.log('');
  }

  await browser.close();
}

test().catch(e => console.error('ERROR:', e));
