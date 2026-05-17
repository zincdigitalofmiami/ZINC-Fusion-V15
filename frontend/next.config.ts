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
  // Complete puppeteer-extra dependency tree — every transitive package that
  // uses dynamic require() and gets dropped by turbopack tree-shaking.
  // Full chain: puppeteer-extra-plugin-stealth → user-preferences → user-data-dir
  //   → fs-extra → graceful-fs, jsonfile, universalify
  //   → rimraf, debug
  //   → puppeteer-extra-plugin → merge-deep → arr-union, clone-deep, kind-of
  //     → clone-deep → for-own, is-plain-object, kind-of, lazy-cache, shallow-clone
  serverExternalPackages: [
    '@sparticuz/chromium',
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
    'fs-extra',
    'graceful-fs',
    'jsonfile',
    'universalify',
    'rimraf',
    'debug',
    'ms',
  ],

}

export default nextConfig
