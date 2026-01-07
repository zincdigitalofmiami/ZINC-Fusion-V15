import type { Config } from 'tailwindcss'

const config: Config = {
  content: ['./src/**/*.{js,ts,jsx,tsx,mdx}'],
  theme: {
    extend: {
      colors: {
        bg: '#131722',
        'surface-1': '#0b0f1a',
        'surface-2': '#1e222d',
        'surface-3': '#2a2e39',
        border: 'rgba(255,255,255,0.08)',
        'border-strong': 'rgba(255,255,255,0.14)',
        text: '#d1d4dc',
        'text-strong': '#ffffff',
        'text-muted': '#787b86',
        accent: '#2962ff',
        up: '#4ade80',
        down: '#ef4444',
        warn: '#fbbf24',
      },
    },
  },
  plugins: [],
}
export default config
