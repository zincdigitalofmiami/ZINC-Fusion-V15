import type { NextConfig } from 'next'

const nextConfig: NextConfig = {
  // output: 'standalone', // Disabled - Railway cache conflict with standalone
  turbopack: {
    root: __dirname,
  },
}

export default nextConfig
