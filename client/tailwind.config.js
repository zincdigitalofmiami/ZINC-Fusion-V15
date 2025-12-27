/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["var(--font-inter)", "ui-sans-serif", "system-ui"],
        mono: ["var(--font-mono)", "ui-monospace", "SFMono-Regular"],
      },
      colors: {
        "app-bg": "#0A0E1A",
        "card-bg": "#111827",
        "card-elevated": "#1F2937",
        primary: "#3B82F6",
        secondary: "#0EA5E9",
        success: "#10B981",
        warning: "#F59E0B",
        danger: "#EF4444",
        "text-primary": "#F9FAFB",
        "text-secondary": "#D1D5DB",
        "text-tertiary": "#9CA3AF",
      },
      backgroundImage: {
        "gradient-blue": "linear-gradient(180deg, #3B82F6 0%, #1E40AF 100%)",
        "gradient-teal": "linear-gradient(180deg, #14B8A6 0%, #0F766E 100%)",
      },
    },
  },
  plugins: [],
};
