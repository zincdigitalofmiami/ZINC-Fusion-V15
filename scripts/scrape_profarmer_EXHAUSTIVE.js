const puppeteer = require('puppeteer');
const path = require('path');
const crypto = require('crypto');
const axios = require('axios');
const xml2js = require('xml2js');
require('dotenv').config({ path: path.join(__dirname, '../frontend/.env.local') });

const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));

async function exhaustiveScrape() {
  const user = process.env.PROFARMER_USERNAME;
  const pass = process.env.PROFARMER_PASSWORD;
  const dbUrl = process.env.DATABASE_URL;

  const { Pool } = require('pg');
  const pool = new Pool({ connectionString: dbUrl, ssl: { rejectUnauthorized: false } });

  const browser = await puppeteer.launch({
    headless: 'new',
    args: ['--no-sandbox', '--disable-setuid-sandbox'],
    defaultViewport: { width: 1920, height: 1080 },
  });

  const page = await browser.newPage();

  console.log('🔐 Logging in...');
  await page.goto('https://www.profarmer.com/r/sign-in', { waitUntil: 'networkidle2' });
  await sleep(1500);

  await page.evaluate(() => {
    const email = document.querySelector('input[type="email"]');
    if (email) email.focus();
  });

  await page.keyboard.type(user, { delay: 80 });
  await page.keyboard.press('Tab');
  await sleep(500);
  await page.keyboard.type(pass, { delay: 80 });
  await page.keyboard.press('Enter');
  await sleep(8000);

  console.log('✅ Logged in\n');

  let totalInserted = 0;
  let totalSkipped = 0;
  const seenUrls = new Set();

  function getSpecialists(title, url, keywords = []) {
    const text = (title + ' ' + url + ' ' + keywords.join(' ')).toLowerCase();
    const specs = [];
    if (text.match(/soy|crush|bean|meal|oil/)) specs.push('crush');
    if (text.match(/china|chinese|asia|export/)) specs.push('china');
    if (text.match(/corn|ethanol|biofuel|rin|epa/)) specs.push('biofuel');
    if (text.match(/tariff|trade|policy|trump|washington/)) specs.push('tariff', 'trump_effect');
    if (text.match(/weather|rain|drought|crop/)) specs.push('palm', 'crush');
    if (text.match(/wheat|canola|palm/)) specs.push('substitutes');
    if (text.match(/energy|crude|oil/)) specs.push('energy');
    if (text.match(/fed|rate|dollar|currency/)) specs.push('fed', 'fx');
    if (text.match(/volatil|market|risk/)) specs.push('volatility');
    return specs.length > 0 ? [...new Set(specs)] : ['crush'];
  }

  // EXHAUSTIVE: All available sitemaps from 2016 to 2026
  const sitemaps = [];
  
  // 2016-2026 (all months that exist)
  for (let year = 2016; year <= 2026; year++) {
    for (let month = 1; month <= 12; month++) {
      if (year === 2026 && month > 1) break;
      if (year === 2016 && month < 11) continue; // They started Nov 2016
      const ym = `${year}${String(month).padStart(2, '0')}`;
      sitemaps.push(`https://www.profarmer.com/sitemap-${ym}.xml`);
    }
  }

  console.log(`🗺️  EXHAUSTIVE SCRAPING: ${sitemaps.length} monthly sitemaps (2016-2026)\n`);
  console.log(`🎯 Goal: Scrape EVERY article from ALL available sitemaps\n`);
  console.log('='.repeat(70) + '\n');

  let processedMonths = 0;

  for (const sitemapUrl of sitemaps) {
    const yearMonth = sitemapUrl.match(/sitemap-(\d{6})/)[1];
    console.log(`📅 ${yearMonth.slice(0, 4)}-${yearMonth.slice(4)}`);

    try {
      const response = await axios.get(sitemapUrl, { timeout: 30000 });
      const parser = new xml2js.Parser();
      const result = await parser.parseStringPromise(response.data);

      const urls = result.urlset?.url || [];
      const newsUrls = urls
        .map(u => u.loc[0])
        .filter(url => url.includes('/news/') && !url.includes('/topics/'));

      console.log(`  Found ${newsUrls.length} news URLs`);

      let monthInserted = 0;

      for (const articleUrl of newsUrls) {
        if (seenUrls.has(articleUrl)) {
          totalSkipped++;
          continue;
        }
        seenUrls.add(articleUrl);

        const rowHash = crypto.createHash('sha256').update(`profarmer|${articleUrl}`).digest('hex');

        const exists = await pool.query('SELECT 1 FROM alt.profarmer_news WHERE row_hash = $1', [rowHash]);
        if (exists.rows.length > 0) {
          totalSkipped++;
          continue;
        }

        try {
          await page.goto(articleUrl, { waitUntil: 'networkidle2', timeout: 25000 });
          await sleep(250);

          const data = await page.evaluate(() => {
            const metadata = {
              date: '', author: '', content: '', title: '',
              description: '', keywords: [], categories: [],
              tags: [], section: '', imageUrl: '', modifiedDate: ''
            };

            // Extract from JSON-LD
            const scripts = document.querySelectorAll('script[type="application/ld+json"]');
            for (const s of scripts) {
              try {
                const json = JSON.parse(s.textContent);
                if (!metadata.date && json.datePublished) metadata.date = json.datePublished;
                if (!metadata.modifiedDate && json.dateModified) metadata.modifiedDate = json.dateModified;
                if (!metadata.author && json.author) {
                  if (Array.isArray(json.author) && json.author[0]?.name) {
                    metadata.author = json.author[0].name;
                  } else if (json.author.name) metadata.author = json.author.name;
                }
                if (!metadata.title && (json.headline || json.name)) {
                  metadata.title = json.headline || json.name;
                }
                if (!metadata.description && json.description) {
                  metadata.description = json.description;
                }
                if (!metadata.imageUrl && json.image) {
                  if (Array.isArray(json.image) && json.image[0]?.url) {
                    metadata.imageUrl = json.image[0].url;
                  } else if (typeof json.image === 'string') metadata.imageUrl = json.image;
                  else if (json.image.url) metadata.imageUrl = json.image.url;
                }
                if (json.articleSection) {
                  const sections = Array.isArray(json.articleSection) ? json.articleSection : [json.articleSection];
                  metadata.categories.push(...sections);
                }
                if (json.about) {
                  const about = Array.isArray(json.about) ? json.about : [json.about];
                  about.forEach(item => {
                    if (typeof item === 'string') metadata.tags.push(item);
                    else if (item.name) metadata.tags.push(item.name);
                  });
                }
                if (json.keywords) {
                  const kw = Array.isArray(json.keywords) ? json.keywords : json.keywords.split(',');
                  metadata.keywords.push(...kw.map(k => k.trim()));
                }
              } catch {}
            }

            // Fallback to meta tags
            if (!metadata.date) {
              const metaDate = document.querySelector('meta[property="article:published_time"]');
              if (metaDate) metadata.date = metaDate.getAttribute('content');
            }
            if (!metadata.description) {
              const metaDesc = document.querySelector('meta[name="description"], meta[property="og:description"]');
              if (metaDesc) metadata.description = metaDesc.getAttribute('content');
            }
            if (!metadata.title) {
              const h1 = document.querySelector('h1');
              if (h1) metadata.title = h1.textContent.trim();
            }

            // Content
            const contentEl = document.querySelector('.Page-articleBody');
            if (contentEl) metadata.content = contentEl.textContent.trim().slice(0, 50000);

            // Breadcrumbs
            const breadcrumbs = document.querySelectorAll('.Page-breadcrumbs a');
            breadcrumbs.forEach(bc => {
              const text = bc.textContent.trim();
              if (text && text !== 'Pro Farmer' && text !== 'News') {
                metadata.categories.push(text);
              }
            });

            metadata.keywords = [...new Set(metadata.keywords)];
            metadata.tags = [...new Set(metadata.tags)];
            metadata.categories = [...new Set(metadata.categories)];

            return metadata;
          });

          if (!data.content || data.content.length < 50) continue;
          if (!data.date) continue;

          const pubDate = new Date(data.date).toISOString().split('T')[0];
          const title = data.title || articleUrl.split('/').pop();
          const specialists = getSpecialists(title, articleUrl, [...data.keywords, ...data.tags, ...data.categories]);

          const rawPayload = {
            scraped_at: new Date().toISOString(),
            source: 'sitemap',
            url: articleUrl,
            summary: data.description,
            keywords: data.keywords,
            tags: data.tags,
            categories: data.categories,
            section: data.section,
            image_url: data.imageUrl,
            modified_date: data.modifiedDate,
            topics: [...data.categories, ...data.tags].filter(Boolean)
          };

          await pool.query(
            `INSERT INTO alt.profarmer_news 
             (event_date, section, headline, content, url, author, specialist_tags, row_hash, raw_payload)
             VALUES ($1::date, $2, $3, $4, $5, $6, $7, $8, $9::jsonb)
             ON CONFLICT (row_hash) DO NOTHING`,
            [
              pubDate,
              data.section || yearMonth.slice(0, 4) + '-' + yearMonth.slice(4),
              title.slice(0, 1000),
              data.content,
              articleUrl,
              data.author,
              specialists,
              rowHash,
              JSON.stringify(rawPayload)
            ]
          );

          totalInserted++;
          monthInserted++;

          if (totalInserted % 100 === 0) {
            console.log(`  📊 Progress: ${totalInserted} total articles inserted`);
          }
        } catch (e) {
          // Continue
        }
      }

      console.log(`  📊 Month: ${monthInserted} articles (${totalInserted} total)\n`);
      processedMonths++;

      if (processedMonths % 12 === 0) {
        console.log(`\n🔄 Processed ${processedMonths} months, ${totalInserted} articles inserted\n`);
      }

    } catch (e) {
      console.log(`  ⚠️  Sitemap not available: ${e.message.slice(0, 50)}\n`);
    }
  }

  console.log('='.repeat(70));
  console.log('🎉 EXHAUSTIVE SCRAPING COMPLETE');
  console.log('='.repeat(70));
  console.log(`✅ INSERTED:  ${totalInserted}`);
  console.log(`⏭️  SKIPPED:   ${totalSkipped}`);
  console.log(`🔗 TOTAL URLS: ${seenUrls.size}`);
  console.log(`📅 MONTHS PROCESSED: ${processedMonths}`);
  console.log('='.repeat(70));

  await browser.close();
  await pool.end();
}

exhaustiveScrape().catch(e => {
  console.error('💥 ERROR:', e);
  process.exit(1);
});
