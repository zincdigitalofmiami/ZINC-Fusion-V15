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
    args: ['--no-sandbox', '--disable-setuid-sandbox'],
    defaultViewport: { width: 1920, height: 1080 },
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
  
  // Crawl ALL topic pages deeply
  const sections = [
    '/news', '/topics/first-thing-today', '/topics/ahead-open', '/topics/after-bell',
    '/topics/daily-advice-monitor', '/topics/weekly-outlook', '/topics/policy-update',
    '/topics/pro-farmer-editors', '/topics/pro-farmer-crop-tour', '/topics/corn',
    '/topics/soybeans', '/topics/wheat', '/topics/cattle', '/topics/hogs', '/topics/cotton',
    '/topics/energy', '/topics/weather', '/topics/trade', '/topics/markets', '/topics/usda',
    '/topics/exports', '/topics/planting', '/topics/harvest', '/topics/livestock',
    '/topics/grains', '/topics/oilseeds', '/topics/dairy', '/topics/biofuels',
  ];

  console.log('=== COLLECTING ALL ARTICLE URLS ===');
  for (const section of sections) {
    for (let pg = 1; pg <= 50; pg++) {
      const url = pg === 1 ? `https://www.profarmer.com${section}` : `https://www.profarmer.com${section}?page=${pg}`;
      try {
        await page.goto(url, { waitUntil: 'networkidle2', timeout: 15000 });
        await sleep(200);
        
        const links = await page.evaluate(() => {
          const urls = [];
          document.querySelectorAll('a[href*="/news/"]').forEach(a => {
            const h = a.href;
            if (!h.includes('/topics/') && !h.includes('/r/') && !h.includes('subscribe')) {
              const parts = h.replace('https://www.profarmer.com', '').split('/').filter(Boolean);
              if (parts.length >= 3) urls.push(h);
            }
          });
          return urls;
        });
        
        const before = allUrls.size;
        links.forEach(u => allUrls.add(u));
        const added = allUrls.size - before;
        
        if (added === 0) break;
        console.log(`  ${section.slice(0,25).padEnd(25)} pg${pg}: +${added} (total: ${allUrls.size})`);
      } catch { break; }
    }
  }

  console.log(`\nTOTAL UNIQUE URLS: ${allUrls.size}\n`);
  console.log('=== SCRAPING FULL METADATA ===\n');

  let inserted = 0;
  const urlArray = [...allUrls];

  for (const url of urlArray) {
    const rowHash = crypto.createHash('sha256').update(`profarmer|${url}`).digest('hex');

    // Skip if exists
    const exists = await pool.query('SELECT 1 FROM alt.news_1d WHERE row_hash = $1 LIMIT 1', [rowHash]);
    if (exists.rows.length > 0) continue;

    try {
      await page.goto(url, { waitUntil: 'networkidle2', timeout: 20000 });
      await sleep(150);

      // Extract EVERYTHING
      const meta = await page.evaluate(() => {
        const data = {
          // Core dates
          publishedAt: null,
          modifiedAt: null,
          
          // Content
          headline: null,
          description: null,
          content: null,
          
          // Attribution
          author: null,
          authorUrl: null,
          
          // Categorization
          section: null,
          topics: [],
          tags: [],
          keywords: [],
          
          // OpenGraph
          ogTitle: null,
          ogDescription: null,
          ogImage: null,
          ogType: null,
          
          // Twitter
          twitterTitle: null,
          twitterDescription: null,
          
          // Schema.org JSON-LD
          schemaType: null,
          schemaHeadline: null,
          schemaDescription: null,
          schemaAuthor: null,
          schemaPublisher: null,
          
          // Article ID
          articleId: null,
        };

        // Meta tags
        data.publishedAt = document.querySelector('meta[property="article:published_time"]')?.getAttribute('content');
        data.modifiedAt = document.querySelector('meta[property="article:modified_time"]')?.getAttribute('content');
        data.description = document.querySelector('meta[name="description"]')?.getAttribute('content');
        data.ogTitle = document.querySelector('meta[property="og:title"]')?.getAttribute('content');
        data.ogDescription = document.querySelector('meta[property="og:description"]')?.getAttribute('content');
        data.ogImage = document.querySelector('meta[property="og:image"]')?.getAttribute('content');
        data.ogType = document.querySelector('meta[property="og:type"]')?.getAttribute('content');
        data.twitterTitle = document.querySelector('meta[name="twitter:title"]')?.getAttribute('content');
        data.twitterDescription = document.querySelector('meta[name="twitter:description"]')?.getAttribute('content');
        
        // Keywords meta
        const keywordsMeta = document.querySelector('meta[name="keywords"]')?.getAttribute('content');
        if (keywordsMeta) data.keywords = keywordsMeta.split(',').map(k => k.trim()).filter(k => k);

        // Section from article:section meta
        data.section = document.querySelector('meta[property="article:section"]')?.getAttribute('content');
        
        // Tags from article:tag meta
        document.querySelectorAll('meta[property="article:tag"]').forEach(m => {
          const tag = m.getAttribute('content');
          if (tag) data.tags.push(tag);
        });

        // JSON-LD Schema
        document.querySelectorAll('script[type="application/ld+json"]').forEach(s => {
          try {
            const j = JSON.parse(s.textContent);
            if (j['@type']) {
              data.schemaType = j['@type'];
              data.schemaHeadline = j.headline;
              data.schemaDescription = j.description;
              if (j.author) data.schemaAuthor = typeof j.author === 'string' ? j.author : j.author.name;
              if (j.publisher) data.schemaPublisher = typeof j.publisher === 'string' ? j.publisher : j.publisher.name;
              if (!data.publishedAt && j.datePublished) data.publishedAt = j.datePublished;
            }
            if (j['@graph']) {
              j['@graph'].forEach(item => {
                if (item['@type'] === 'Article' || item['@type'] === 'NewsArticle') {
                  data.schemaType = item['@type'];
                  data.schemaHeadline = item.headline;
                  data.schemaDescription = item.description;
                  if (item.author) data.schemaAuthor = typeof item.author === 'string' ? item.author : (item.author.name || item.author[0]?.name);
                  if (!data.publishedAt && item.datePublished) data.publishedAt = item.datePublished;
                }
              });
            }
          } catch {}
        });

        // Headline from H1 or title
        data.headline = document.querySelector('h1')?.textContent?.trim() || 
                        document.querySelector('title')?.textContent?.trim()?.replace(' - Pro Farmer', '');

        // Author from page elements
        const authorEl = document.querySelector('.Page-authorName a, .Page-authorName, [rel="author"], .author, .byline a');
        if (authorEl) {
          data.author = authorEl.textContent?.trim();
          data.authorUrl = authorEl.href || null;
        }

        // Topics from breadcrumbs
        document.querySelectorAll('.Page-breadcrumbs a, .breadcrumb a, nav.breadcrumb a').forEach(a => {
          const topic = a.textContent?.trim();
          if (topic && topic !== 'Home' && topic !== 'News') data.topics.push(topic);
        });

        // Tags from page elements
        document.querySelectorAll('.Page-tags a, .tags a, .article-tags a').forEach(a => {
          const tag = a.textContent?.trim();
          if (tag) data.tags.push(tag);
        });

        // Content
        let content = '';
        ['.Page-articleBody', '.RichTextArticleBody', '.RichTextBody', '.Page-content'].forEach(sel => {
          if (!content || content.length < 200) {
            const el = document.querySelector(sel);
            if (el) content = el.textContent?.trim()?.slice(0, 60000) || '';
          }
        });
        data.content = content;

        // Article ID from URL
        data.articleId = window.location.pathname.split('/').filter(Boolean).pop();

        return data;
      });

      if (!meta.content || meta.content.length < 50) continue;
      if (!meta.publishedAt) continue;

      const pubDate = new Date(meta.publishedAt);
      if (isNaN(pubDate.getTime())) continue;

      const eventDate = pubDate.toISOString().split('T')[0];
      
      // Build specialist tags
      const fullText = (meta.headline + ' ' + meta.description + ' ' + meta.tags.join(' ') + ' ' + meta.topics.join(' ')).toLowerCase();
      const specialistTags = [];
      if (/soy|crush|bean|meal|oil/.test(fullText)) specialistTags.push('crush');
      if (/china|asia|export|chinese/.test(fullText)) specialistTags.push('china');
      if (/corn|ethanol|biofuel|rin|epa|e15|rfs/.test(fullText)) specialistTags.push('biofuel');
      if (/tariff|trade|policy|trump|usda|washington/.test(fullText)) specialistTags.push('tariff', 'trump_effect');
      if (/weather|rain|drought|storm|flood/.test(fullText)) specialistTags.push('palm', 'crush');
      if (/wheat|canola|palm|sunflower/.test(fullText)) specialistTags.push('substitutes');
      if (/energy|crude|gasoline|diesel/.test(fullText)) specialistTags.push('energy');
      if (/fed|rate|dollar|currency|interest/.test(fullText)) specialistTags.push('fed', 'fx');
      if (/volatil|risk|uncertain/.test(fullText)) specialistTags.push('volatility');
      if (specialistTags.length === 0) specialistTags.push('crush');

      const isTrump = /trump|tariff|trade war|china trade|section 301/i.test(meta.headline + ' ' + meta.content.slice(0, 2000));

      // Full raw payload with ALL metadata
      const rawPayload = {
        scraped_at: new Date().toISOString(),
        source_url: url,
        meta_description: meta.description,
        og_title: meta.ogTitle,
        og_description: meta.ogDescription,
        og_image: meta.ogImage,
        og_type: meta.ogType,
        twitter_title: meta.twitterTitle,
        twitter_description: meta.twitterDescription,
        schema_type: meta.schemaType,
        schema_headline: meta.schemaHeadline,
        schema_description: meta.schemaDescription,
        schema_author: meta.schemaAuthor,
        schema_publisher: meta.schemaPublisher,
        section: meta.section,
        topics: meta.topics,
        tags: [...new Set(meta.tags)],
        keywords: meta.keywords,
        author_url: meta.authorUrl,
        modified_at: meta.modifiedAt,
      };

      await pool.query(
        `INSERT INTO alt.news_1d 
         (article_id, event_date, published_at, headline, content, url, author, source, 
          is_trump_related, specialist_tags, row_hash, raw_payload, knowledge_time, ingested_at)
         VALUES ($1, $2::date, $3::timestamptz, $4, $5, $6, $7, 'profarmer', 
                 $8, $9, $10, $11::jsonb, NOW(), NOW())
         ON CONFLICT (row_hash) DO NOTHING`,
        [
          meta.articleId,
          eventDate,
          meta.publishedAt,
          meta.headline?.slice(0, 1000) || meta.ogTitle || 'No headline',
          meta.content,
          url,
          meta.author || meta.schemaAuthor || null,
          isTrump,
          [...new Set(specialistTags)],
          rowHash,
          JSON.stringify(rawPayload)
        ]
      );
      
      inserted++;
      console.log(`[${inserted}] ${eventDate} | ${(meta.section || 'News').slice(0,15).padEnd(15)} | ${(meta.headline || '').slice(0, 45)}`);
      
    } catch (e) {
      // Skip errors
    }
  }

  console.log(`\n==========================================`);
  console.log(`TOTAL INSERTED: ${inserted}`);
  console.log(`==========================================`);

  // Final count
  const count = await pool.query("SELECT COUNT(*), MIN(event_date), MAX(event_date) FROM alt.news_1d WHERE source = 'profarmer'");
  console.log(`\nPROFARMER IN alt.news_1d: ${count.rows[0].count} articles`);
  console.log(`DATE RANGE: ${count.rows[0].min} to ${count.rows[0].max}`);

  await browser.close();
  await pool.end();
}

scrape().catch(console.error);
