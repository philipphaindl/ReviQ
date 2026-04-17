/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        ink: {
          DEFAULT: '#2B2B2B',
          light: '#555555',
          muted: '#888888',
        },
        paper: '#FAF8F5',
        surface: '#ffffff',
        rule: '#E5E2DD',
        accent: {
          DEFAULT: '#1E3A5F',
          hover: '#152D4A',
          faint: '#F0F3F7',
        },
        include: '#2D6A4F',
        exclude: '#8B1A1A',
        uncertain: '#8B6914',
        info: '#1E3A5F',
        // Legacy aliases
        navy: {
          DEFAULT: '#2B2B2B',
          light: '#555555',
          muted: '#888888',
        },
        card: '#FAF8F5',
        border: '#E5E2DD',
        masthead: '#1A2332',
      },
      fontFamily: {
        display: ['"Newsreader"', 'Georgia', 'serif'],
        sans: ['"Source Sans 3"', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'Menlo', 'monospace'],
      },
      borderRadius: {
        card: '3px',
        modal: '6px',
      },
      boxShadow: {
        card: 'none',
        'card-hover': '0 2px 8px rgba(0,0,0,0.08)',
        stat: 'none',
        modal: '0 8px 40px rgba(0,0,0,0.15), 0 2px 8px rgba(0,0,0,0.08)',
      },
      fontSize: {
        '2xs': ['0.6875rem', { lineHeight: '1rem' }],
      },
      letterSpacing: {
        label: '0.06em',
      },
      transitionDuration: {
        DEFAULT: '120ms',
      },
    },
  },
  plugins: [],
}
