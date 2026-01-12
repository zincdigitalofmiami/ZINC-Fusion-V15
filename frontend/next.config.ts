import type { NextConfig } from 'next'

const nextConfig: NextConfig = {
  // output: 'standalone', // Disabled for Vercel deployment
  turbopack: {
    root: __dirname,
  },
}

export default nextConfig
