const puppeteer = require('puppeteer');
const path = require('path');
const crypto = require('crypto');
require('dotenv').config({ path: path.join(__dirname, '../frontend/.env.local') });

const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));

async function scrape() {
  const user = process.env.PROFARMER_USERNAME;
  const pass = process.env.PROFARMER_PASSWORD;
  const { Pool } = require('pg');
  const pool = new Pool({ connectionString: process.env.DATABASE_URL, ssl: { rejectUnauthorized: false } });

  const browser = await puppeteer.launch({
    headless: 'new',
    args: ['--no-sandbox'],
    defaultViewport: { width: 1920, height: 1080 },
  });

  const page = await browser.newPage();
  await page.setUserAgent('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36');

  // Get sitemap URLs first
  console.log('=== FETCHING SITEMAP ===');
  await page.goto('https://www.profarmer.com/sitemap.xml', { waitUntil: 'networkidle2' });
  const sitemapXml = await page.content();
  
  // Extract all URLs from sitemap
  const urlMatches = sitemapXml.match(/<loc>([^<]+)<\/loc>/g) || [];
  const allUrls = urlMatches.map(m => m.replace('<loc>', '').replace('</loc>', ''));
  const newsUrls = allUrls.filter(u => u.includes('/news/') && !u.includes('/topics/'));
  console.log(`Sitemap has ${allUrls.length} total URLs, ${newsUrls.length} news articles\n`);

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

  const getTags = (text) => {
    text = text.toLowerCase();
    const tags = [];
    if (/soy|crush|bean|meal|oil/.test(text)) tags.push('crush');
    if (/china|asia|export|chinese/.test(text)) tags.push('china');
    if (/corn|ethanol|biofuel|rin|epa|e15|rfs/.test(text)) tags.push('biofuel');
    if (/tariff|trade|policy|trump|usda|washington/.test(text)) tags.push('tariff', 'trump_effect');
    if (/weather|rain|drought|storm|flood/.test(text)) tags.push('palm', 'crush');
    if (/wheat|canola|palm|sunflower/.test(text)) tags.push('substitutes');
    if (/energy|crude|gasoline|diesel/.test(text)) tags.push('energy');
    if (/fed|rate|dollar|currency|interest/.test(text)) tags.push('fed', 'fx');
    if (/volatil|risk|uncertainty/.test(text)) tags.push('volatility');
    return tags.length ? [...new Set(tags)] : ['crush'];
  };

  const isTrumpRelated = (text) => {
    return /trump|tariff|trade war|china trade|section 301/i.test(text);
  };

  let inserted = 0;
  let skipped = 0;

  console.log('=== SCRAPING ALL ARTICLES ===');
  
  for (const url of newsUrls) {
    const rowHash = crypto.createHash('sha256').update(`profarmer|${url}`).digest('hex');

    // Check if already exists
    const exists = await pool.query('SELECT 1 FROM alt.news_1d WHERE row_hash = $1 LIMIT 1', [rowHash]);
    if (exists.rows.length > 0) {
      skipped++;
      continue;
    }

    try {
      await page.goto(url, { waitUntil: 'networkidle2', timeout: 20000 });
      await sleep(200);

      const data = await page.evaluate(() => {
        // Published date - multiple sources
        let publishedAt = null;
        const metaDate = document.querySelector('meta[property="article:published_time"]');
        if (metaDate) publishedAt = metaDate.getAttribute('content');
        
        if (!publishedAt) {
          document.querySelectorAll('script[type="application/ld+json"]').forEach(s => {
            try {
              const j = JSON.parse(s.textContent);
              if (j.datePublished) publishedAt = j.datePublished;
              if (j['@graph']) j['@graph'].forEach(i => { if (i.datePublished) publishedAt = i.datePublished; });
            } catch {}
          });
        }

        // Headline
        let headline = document.querySelector('h1')?.textContent?.trim() || 
                       document.querySelector('meta[property="og:title"]')?.getAttribute('content') || '';

        // Author
        let author = '';
        const authorEl = document.querySelector('.Page-authorName a, [rel="author"], .author, .byline');
        if (authorEl) author = authorEl.textContent?.trim() || '';

        // Content
        let content = '';
        ['.Page-articleBody', '.RichTextArticleBody', '.Page-content', 'article'].forEach(sel => {
          if (!content || content.length < 200) {
            const el = document.querySelector(sel);
            if (el) content = el.textContent?.trim()?.slice(0, 50000) || '';
          }
        });

        // Article ID from URL
        const articleId = window.location.pathname.split('/').pop();

        return { publishedAt, headline, author, content, articleId };
      });

      if (!data.content || data.content.length < 50) continue;
      if (!data.publishedAt) continue;

      const pubDate = new Date(data.publishedAt);
      if (isNaN(pubDate.getTime())) continue;

      const eventDate = pubDate.toISOString().split('T')[0];
      const tags = getTags(data.headline + ' ' + data.content.slice(0, 500));
      const trump = isTrumpRelated(data.headline + ' ' + data.content.slice(0, 1000));

      await pool.query(
        `INSERT INTO alt.news_1d 
         (article_id, event_date, published_at, headline, content, url, author, source, 
          sentiment_score, zl_sentiment, is_trump_related, specialist_tags, row_hash, raw_payload, knowledge_time)
         VALUES ($1, $2::date, $3::timestamptz, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14::jsonb, NOW())
         ON CONFLICT (row_hash) DO NOTHING`,
        [
          data.articleId,
          eventDate,
          data.publishedAt,
          data.headline.slice(0, 1000),
          data.content,
          url,
          data.author || null,
          'profarmer',
          null, // sentiment_score - to be calculated
          null, // zl_sentiment - to be calculated  
          trump,
          tags,
          rowHash,
          JSON.stringify({ scraped_at: new Date().toISOString(), source_type: 'sitemap' })
        ]
      );
      inserted++;
      console.log(`[${inserted}] ${eventDate} | ${data.headline.slice(0, 50)}`);
    } catch (e) {
      console.log(`ERROR: ${url.slice(-40)} - ${e.message.slice(0, 30)}`);
    }
  }

  console.log(`\n========================================`);
  console.log(`INSERTED: ${inserted}`);
  console.log(`SKIPPED (existing): ${skipped}`);
  console.log(`========================================`);

  // Show count
  const count = await pool.query("SELECT COUNT(*) FROM alt.news_1d WHERE source = 'profarmer'");
  console.log(`\nTOTAL PROFARMER IN alt.news_1d: ${count.rows[0].count}`);

  await browser.close();
  await pool.end();
}

scrape().catch(console.error);
