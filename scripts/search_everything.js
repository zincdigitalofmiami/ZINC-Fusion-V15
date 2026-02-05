const puppeteer = require('puppeteer');
const path = require('path');
const crypto = require('crypto');
require('dotenv').config({ path: path.join(__dirname, '../frontend/.env.local') });

const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));

async function searchAll() {
  const user = process.env.PROFARMER_USERNAME;
  const pass = process.env.PROFARMER_PASSWORD;
  const { Pool } = require('pg');
  const pool = new Pool({ connectionString: process.env.DATABASE_URL, ssl: { rejectUnauthorized: false } });

  const browser = await puppeteer.launch({
    headless: 'new',
    args: ['--no-sandbox'],
    defaultViewport: { width: 1920, height: 2000 },
  });

  const page = await browser.newPage();
  await page.setUserAgent('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36');

  // LOGIN
  console.log('=== LOGGING IN ===');
  await page.goto('https://www.profarmer.com/r/sign-in', { waitUntil: 'networkidle2' });
  await sleep(1000);
  await page.evaluate(() => {
    document.querySelectorAll('form').forEach(f => {
      const e = f.querySelector('input[type="email"]');
      if (e && f.querySelector('input[type="password"]')) e.focus();
    });
  });
  await page.keyboard.type(user, { delay: 40 });
  await page.keyboard.press('Tab');
  await page.keyboard.type(pass, { delay: 40 });
  await page.keyboard.press('Enter');
  await sleep(5000);
  console.log('LOGGED IN\n');

  const allUrls = new Set();

  // Search for EVERYTHING with multiple keywords
  const searchTerms = [
    'soybean', 'corn', 'wheat', 'cattle', 'hogs', 'cotton', 'weather', 'USDA',
    'trade', 'tariff', 'China', 'export', 'ethanol', 'biofuel', 'grain', 'crop',
    'farm', 'price', 'market', 'futures', 'drought', 'rain', 'harvest', 'planting',
    'beef', 'pork', 'livestock', 'dairy', 'milk', 'oilseed', 'meal', 'oil',
    'crush', 'spread', 'basis', 'cash', 'contract', 'delivery', 'storage',
    '2024', '2025', '2026', 'January', 'February', 'March', 'April', 'May', 'June',
    'July', 'August', 'September', 'October', 'November', 'December',
    'Trump', 'Biden', 'policy', 'EPA', 'RFS', 'RIN', 'E15',
  ];

  console.log('=== SEARCHING FOR ALL ARTICLES ===');
  
  for (const term of searchTerms) {
    try {
      await page.goto(`https://www.profarmer.com/search?q=${encodeURIComponent(term)}`, { 
        waitUntil: 'networkidle2', 
        timeout: 20000 
      });
      await sleep(500);
      
      // Scroll to load more results
      for (let i = 0; i < 10; i++) {
        await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
        await sleep(300);
      }

      const links = await page.evaluate(() => {
        const urls = [];
        document.querySelectorAll('a[href*="/news/"]').forEach(a => {
          const h = a.href;
          if (!h.includes('/topics/') && !h.includes('/r/')) {
            const parts = h.replace('https://www.profarmer.com', '').split('/').filter(Boolean);
            if (parts.length >= 3) urls.push(h);
          }
        });
        return urls;
      });

      const before = allUrls.size;
      links.forEach(u => allUrls.add(u));
      const added = allUrls.size - before;
      
      if (added > 0) {
        console.log(`  "${term}": +${added} (total: ${allUrls.size})`);
      }
    } catch {}
  }

  // Also try browsing newsletter archive
  console.log('\n=== CHECKING NEWSLETTER ARCHIVE ===');
  const newsletters = ['/newsletter', '/newsletters', '/archive', '/archive/newsletters', '/topics/newsletter'];
  for (const path of newsletters) {
    try {
      await page.goto(`https://www.profarmer.com${path}`, { waitUntil: 'networkidle2', timeout: 10000 });
      const links = await page.evaluate(() => {
        return [...document.querySelectorAll('a[href*="/news/"]')].map(a => a.href).filter(h => !h.includes('/topics/'));
      });
      const before = allUrls.size;
      links.forEach(u => allUrls.add(u));
      if (allUrls.size > before) console.log(`  ${path}: +${allUrls.size - before}`);
    } catch {}
  }

  console.log(`\nTOTAL UNIQUE ARTICLE URLS FOUND: ${allUrls.size}\n`);

  // Now scrape all with full metadata
  console.log('=== SCRAPING FULL METADATA ===\n');
  
  let inserted = 0;
  const urlArray = [...allUrls];

  for (const url of urlArray) {
    const rowHash = crypto.createHash('sha256').update(`profarmer|${url}`).digest('hex');
    
    const exists = await pool.query('SELECT 1 FROM alt.news_1d WHERE row_hash = $1', [rowHash]);
    if (exists.rows.length > 0) continue;

    try {
      await page.goto(url, { waitUntil: 'networkidle2', timeout: 20000 });
      await sleep(100);

      const meta = await page.evaluate(() => {
        const data = {};
        
        // All meta tags
        data.publishedAt = document.querySelector('meta[property="article:published_time"]')?.getAttribute('content');
        data.modifiedAt = document.querySelector('meta[property="article:modified_time"]')?.getAttribute('content');
        data.description = document.querySelector('meta[name="description"]')?.getAttribute('content');
        data.section = document.querySelector('meta[property="article:section"]')?.getAttribute('content');
        data.ogTitle = document.querySelector('meta[property="og:title"]')?.getAttribute('content');
        data.ogDescription = document.querySelector('meta[property="og:description"]')?.getAttribute('content');
        data.ogImage = document.querySelector('meta[property="og:image"]')?.getAttribute('content');
        
        // Tags from meta
        data.metaTags = [];
        document.querySelectorAll('meta[property="article:tag"]').forEach(m => {
          const t = m.getAttribute('content');
          if (t) data.metaTags.push(t);
        });

        // Keywords
        const kw = document.querySelector('meta[name="keywords"]')?.getAttribute('content');
        data.keywords = kw ? kw.split(',').map(k => k.trim()) : [];

        // JSON-LD
        document.querySelectorAll('script[type="application/ld+json"]').forEach(s => {
          try {
            const j = JSON.parse(s.textContent);
            if (j.datePublished && !data.publishedAt) data.publishedAt = j.datePublished;
            if (j.headline) data.schemaHeadline = j.headline;
            if (j.author) data.schemaAuthor = typeof j.author === 'string' ? j.author : j.author.name;
            if (j['@graph']) {
              j['@graph'].forEach(item => {
                if (item.datePublished && !data.publishedAt) data.publishedAt = item.datePublished;
                if (item.headline) data.schemaHeadline = item.headline;
              });
            }
          } catch {}
        });

        // Page content
        data.headline = document.querySelector('h1')?.textContent?.trim();
        const authorEl = document.querySelector('.Page-authorName a, .Page-authorName, [rel="author"]');
        data.author = authorEl?.textContent?.trim();
        
        data.topics = [];
        document.querySelectorAll('.Page-breadcrumbs a').forEach(a => {
          const t = a.textContent?.trim();
          if (t && t !== 'Home' && t !== 'News') data.topics.push(t);
        });

        data.pageTags = [];
        document.querySelectorAll('.Page-tags a').forEach(a => {
          const t = a.textContent?.trim();
          if (t) data.pageTags.push(t);
        });

        let content = '';
        ['.Page-articleBody', '.RichTextArticleBody', '.Page-content'].forEach(sel => {
          if (!content) {
            const el = document.querySelector(sel);
            if (el) content = el.textContent?.trim()?.slice(0, 60000);
          }
        });
        data.content = content;

        data.articleId = window.location.pathname.split('/').filter(Boolean).pop();

        return data;
      });

      if (!meta.content || meta.content.length < 50 || !meta.publishedAt) continue;

      const pubDate = new Date(meta.publishedAt);
      if (isNaN(pubDate.getTime())) continue;

      const eventDate = pubDate.toISOString().split('T')[0];
      const fullText = (meta.headline + ' ' + meta.description + ' ' + meta.metaTags?.join(' ') + ' ' + meta.topics?.join(' ')).toLowerCase();
      
      const specialistTags = [];
      if (/soy|crush|bean|meal|oil/.test(fullText)) specialistTags.push('crush');
      if (/china|asia|export/.test(fullText)) specialistTags.push('china');
      if (/corn|ethanol|biofuel|rin|epa|e15/.test(fullText)) specialistTags.push('biofuel');
      if (/tariff|trade|policy|trump|usda/.test(fullText)) specialistTags.push('tariff', 'trump_effect');
      if (/weather|rain|drought|storm/.test(fullText)) specialistTags.push('palm', 'crush');
      if (/wheat|canola|palm/.test(fullText)) specialistTags.push('substitutes');
      if (/energy|crude/.test(fullText)) specialistTags.push('energy');
      if (/fed|rate|dollar/.test(fullText)) specialistTags.push('fed', 'fx');
      if (/volatil|risk/.test(fullText)) specialistTags.push('volatility');
      if (!specialistTags.length) specialistTags.push('crush');

      const isTrump = /trump|tariff|trade war|section 301/i.test(fullText);

      const rawPayload = {
        scraped_at: new Date().toISOString(),
        meta_description: meta.description,
        og_title: meta.ogTitle,
        og_description: meta.ogDescription,
        og_image: meta.ogImage,
        section: meta.section,
        topics: meta.topics,
        meta_tags: meta.metaTags,
        page_tags: meta.pageTags,
        keywords: meta.keywords,
        schema_headline: meta.schemaHeadline,
        schema_author: meta.schemaAuthor,
        modified_at: meta.modifiedAt,
      };

      await pool.query(
        `INSERT INTO alt.news_1d 
         (article_id, event_date, published_at, headline, content, url, author, source, 
          is_trump_related, specialist_tags, row_hash, raw_payload, knowledge_time, ingested_at)
         VALUES ($1, $2::date, $3::timestamptz, $4, $5, $6, $7, 'profarmer', $8, $9, $10, $11::jsonb, NOW(), NOW())
         ON CONFLICT (row_hash) DO NOTHING`,
        [meta.articleId, eventDate, meta.publishedAt, meta.headline?.slice(0,1000), meta.content, url, 
         meta.author || meta.schemaAuthor, isTrump, [...new Set(specialistTags)], rowHash, JSON.stringify(rawPayload)]
      );
      
      inserted++;
      console.log(`[${inserted}] ${eventDate} | ${(meta.headline || '').slice(0, 50)}`);
    } catch {}
  }

  console.log(`\n==========================================`);
  console.log(`TOTAL INSERTED: ${inserted}`);
  
  const count = await pool.query("SELECT COUNT(*), MIN(event_date), MAX(event_date) FROM alt.news_1d WHERE source = 'profarmer'");
  console.log(`PROFARMER IN DB: ${count.rows[0].count} | ${count.rows[0].min} to ${count.rows[0].max}`);
  console.log(`==========================================`);

  await browser.close();
  await pool.end();
}

searchAll().catch(console.error);
