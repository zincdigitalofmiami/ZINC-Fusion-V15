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
}

export default nextConfig
