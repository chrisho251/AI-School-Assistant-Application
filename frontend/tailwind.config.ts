import type { Config } from 'tailwindcss';

// Tailwind only owns layout/responsive utilities. Colours/radius/shadow stay in
// CSS variables (src/styles/tokens.css + app.css) so the design pixel-matches.
// The tokens exposed here are convenience aliases, not a replacement system.
const config: Config = {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        brand: 'var(--fr-accent)',
        page: 'var(--fr-page)',
      },
      fontFamily: {
        sans: 'var(--font-sans)',
        mono: 'var(--font-mono)',
      },
    },
  },
  plugins: [],
};

export default config;
