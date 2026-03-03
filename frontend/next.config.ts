import type { NextConfig } from 'next'
import path from 'path'

const nextConfig: NextConfig = {
  // output: 'standalone', // Disabled for Vercel deployment

  // Align outputFileTracingRoot with turbopack.root to avoid build warning
  // Both must point to the same directory (monorepo root)
  outputFileTracingRoot: path.join(__dirname, '..'),
  turbopack: {
    root: path.join(__dirname, '..'),
  },

  // Force ALL puppeteer-extra transitive deps to load at runtime, not bundled.
  // These packages use dynamic require() which turbopack drops during tree-shaking.
  // Dependency chain: puppeteer-extra-plugin → merge-deep → kind-of, clone-deep
  //                   clone-deep → is-plain-object, kind-of, shallow-clone, for-own, lazy-cache
  serverExternalPackages: [
    'puppeteer-core',
    'puppeteer-extra',
    'puppeteer-extra-plugin',
    'puppeteer-extra-plugin-stealth',
    'puppeteer-extra-plugin-user-preferences',
    'puppeteer-extra-plugin-user-data-dir',
    'merge-deep',
    'clone-deep',
    'is-plain-object',
    'kind-of',
    'shallow-clone',
    'for-own',
    'lazy-cache',
    'arr-union',
    'deepmerge',
  ],

  // Force Vercel output file tracing to include nested node_modules copies.
  // merge-deep and clone-deep each have their own node_modules/kind-of (v3)
  // which differs from the top-level kind-of (v6). Without this, turbopack
  // marks them external but Vercel's trace misses the nested copies → runtime crash.
  outputFileTracingIncludes: {
    '/api/inngest': [
      './node_modules/puppeteer-extra/**/*',
      './node_modules/puppeteer-extra-plugin/**/*',
      './node_modules/puppeteer-extra-plugin-stealth/**/*',
      './node_modules/puppeteer-extra-plugin-user-preferences/**/*',
      './node_modules/puppeteer-extra-plugin-user-data-dir/**/*',
      './node_modules/merge-deep/**/*',
      './node_modules/clone-deep/**/*',
      './node_modules/is-plain-object/**/*',
      './node_modules/kind-of/**/*',
      './node_modules/shallow-clone/**/*',
      './node_modules/for-own/**/*',
      './node_modules/lazy-cache/**/*',
      './node_modules/arr-union/**/*',
      './node_modules/deepmerge/**/*',
      './node_modules/puppeteer-core/**/*',
      './node_modules/@sparticuz/chromium/**/*',
    ],
  },
}

export default nextConfig
