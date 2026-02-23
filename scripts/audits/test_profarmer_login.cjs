#!/usr/bin/env node
/**
 * Test ProFarmer login locally using the SAME stack as production:
 *   puppeteer-extra + stealth plugin + keyboard-based login flow.
 *
 * Run from repo root:
 *   node tests/test_profarmer_login.js
 *
 * Requires: frontend/.env.local with PROFARMER_USERNAME + PROFARMER_PASSWORD
 */

const path = require("path");
require("dotenv").config({
  path: path.join(__dirname, "../frontend/.env.local"),
});

// Use the same packages as production (from frontend/node_modules)
const puppeteerExtra = require(
  path.join(__dirname, "../frontend/node_modules/puppeteer-extra"),
);
const StealthPlugin = require(
  path.join(
    __dirname,
    "../frontend/node_modules/puppeteer-extra-plugin-stealth",
  ),
);

puppeteerExtra.use(StealthPlugin());

const PROFARMER_LOGIN_URL = "https://www.profarmer.com/r/sign-in";
const CHROME_PATH =
  "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function testLogin() {
  const user = process.env.PROFARMER_USERNAME;
  const pass = process.env.PROFARMER_PASSWORD;

  if (!user || !pass) {
    console.error(
      "PROFARMER_USERNAME and PROFARMER_PASSWORD required in frontend/.env.local",
    );
    process.exit(1);
  }

  console.log(`[test] username: ${user}`);
  console.log(`[test] chrome: ${CHROME_PATH}`);

  const browser = await puppeteerExtra.launch({
    headless: "new",
    executablePath: CHROME_PATH,
    args: ["--no-sandbox", "--disable-setuid-sandbox", "--disable-gpu"],
    defaultViewport: { width: 1920, height: 1080 },
  });

  const page = await browser.newPage();

  await page.setUserAgent(
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
  );

  await page.setExtraHTTPHeaders({
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    Accept:
      "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
    Connection: "keep-alive",
    "Upgrade-Insecure-Requests": "1",
  });

  // --- Step 1: Navigate to login page ---
  console.log("\n[test] Step 1: navigating to login page...");
  await page.goto(PROFARMER_LOGIN_URL, {
    waitUntil: "networkidle2",
    timeout: 60000,
  });
  await sleep(1500); // SPA hydration wait

  // --- Step 2: Check for CAPTCHA ---
  const hasCaptcha = await page.evaluate(() => {
    return !!document.querySelector(
      'iframe[src*="recaptcha"], .g-recaptcha, [class*="captcha"]',
    );
  });
  console.log(`[test] CAPTCHA detected: ${hasCaptcha}`);

  if (hasCaptcha) {
    await page.screenshot({ path: "/tmp/profarmer_captcha.png" });
    console.log("[test] Screenshot: /tmp/profarmer_captcha.png");
    await browser.close();
    process.exit(1);
  }

  // --- Step 3: Keyboard login (same as production) ---
  console.log("[test] Step 3: keyboard login (focus → type → Tab → type → Enter)...");

  const foundForm = await page.evaluate(() => {
    const forms = document.querySelectorAll("form");
    for (const form of forms) {
      const emailInput = form.querySelector('input[type="email"]');
      if (emailInput && form.querySelector('input[type="password"]')) {
        emailInput.focus();
        emailInput.click();
        return true;
      }
    }
    return false;
  });

  if (!foundForm) {
    console.error("[test] FAIL: Could not find login form");
    await page.screenshot({ path: "/tmp/profarmer_no_form.png" });
    await browser.close();
    process.exit(1);
  }
  console.log("[test]   form found, email field focused");

  await page.keyboard.type(user, { delay: 80 });
  console.log("[test]   email typed");
  await sleep(500);

  await page.keyboard.press("Tab");
  console.log("[test]   Tab pressed (→ password field)");
  await sleep(500);

  await page.keyboard.type(pass, { delay: 80 });
  console.log("[test]   password typed");
  await sleep(500);

  await page.keyboard.press("Enter");
  console.log("[test]   Enter pressed, waiting 8s for redirect...");
  await sleep(8000);

  // --- Step 4: Check login result ---
  const finalUrl = page.url();
  console.log(`[test] Step 4: post-login URL: ${finalUrl}`);

  await page.screenshot({ path: "/tmp/profarmer_result.png" });
  console.log("[test] Screenshot: /tmp/profarmer_result.png");

  const loginSuccess =
    !finalUrl.includes("sign-in") && !finalUrl.includes("login");
  console.log(`\n[test] LOGIN ${loginSuccess ? "SUCCESS" : "FAILED"}`);

  if (!loginSuccess) {
    const errorText = await page.evaluate(() => {
      const el = document.querySelector(
        '.error, .alert-danger, [class*="error"]',
      );
      return el?.textContent?.trim() || null;
    });
    if (errorText) console.log(`[test] Error message: ${errorText}`);
    await browser.close();
    process.exit(1);
  }

  // --- Step 5: Test content access with updated URLs ---
  const testUrls = [
    {
      name: "First Thing Today",
      url: "https://www.profarmer.com/topics/first-thing-today",
    },
    {
      name: "Daily Advice Monitor",
      url: "https://www.profarmer.com/news/advice-monitor/pro-farmers-daily-advice-monitor",
    },
  ];

  for (const test of testUrls) {
    console.log(`\n[test] Step 5: accessing ${test.name}...`);
    await page.goto(test.url, { waitUntil: "networkidle2", timeout: 30000 });

    const pageTitle = await page.title();
    const articleCount = await page.evaluate(() => {
      return document.querySelectorAll('a[href*="/news/"]').length;
    });
    console.log(`[test]   title: ${pageTitle}`);
    console.log(`[test]   article links found: ${articleCount}`);
  }

  // --- Step 6: Test single article scrape with ProFarmer selectors ---
  console.log("\n[test] Step 6: testing article content extraction...");
  const firstArticleUrl = await page.evaluate(() => {
    const links = document.querySelectorAll('a[href*="/news/"]');
    for (const a of links) {
      const href = a.href;
      const pathParts = href
        .replace("https://www.profarmer.com", "")
        .split("/")
        .filter(Boolean);
      if (pathParts.length >= 3 && !href.includes("/r/")) return href;
    }
    return null;
  });

  if (firstArticleUrl) {
    console.log(`[test]   navigating to: ${firstArticleUrl}`);
    await page.goto(firstArticleUrl, {
      waitUntil: "networkidle2",
      timeout: 20000,
    });
    await sleep(300);

    const articleData = await page.evaluate(() => {
      // Date
      let date = "";
      const metaDate = document.querySelector(
        'meta[property="article:published_time"]',
      );
      if (metaDate) date = metaDate.getAttribute("content") || "";
      if (!date) {
        const dateEl = document.querySelector(".Page-datePublished");
        if (dateEl) date = dateEl.textContent?.trim() || "";
      }

      // Author
      let author = "";
      const authorEl = document.querySelector(
        '.Page-authorName a, .byline a, [rel="author"]',
      );
      if (authorEl) author = authorEl.textContent?.trim() || "";

      // Content
      let content = "";
      const sels = [
        ".Page-articleBody",
        ".RichTextArticleBody",
        ".RichTextBody",
        ".Page-content",
        "article",
      ];
      for (const sel of sels) {
        const el = document.querySelector(sel);
        if (el?.textContent && el.textContent.length > 100) {
          content = el.textContent.trim().slice(0, 200) + "...";
          break;
        }
      }

      return { date, author, contentLength: content.length, contentPreview: content.slice(0, 120) };
    });

    console.log(`[test]   date: ${articleData.date || "(not found)"}`);
    console.log(`[test]   author: ${articleData.author || "(not found)"}`);
    console.log(`[test]   content length: ${articleData.contentLength} chars`);
    console.log(`[test]   preview: ${articleData.contentPreview}`);
  } else {
    console.log("[test]   no article links found to test");
  }

  await browser.close();
  console.log("\n[test] All steps passed.");
  process.exit(0);
}

testLogin().catch((err) => {
  console.error("[test] FATAL:", err.message);
  process.exit(1);
});
