/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        // Faro-inspired palette
        navy: {
          DEFAULT: '#1A3A5C',
          light: '#2E6DA4',
          muted: '#4A6FA5',
        },
        card: '#F8FAFC',
        border: '#E5EAF0',
        include: '#27AE60',
        exclude: '#C0392B',
        uncertain: '#E67E22',
        info: '#2E6DA4',
      },
      fontFamily: {
        sans: [
          '-apple-system', 'BlinkMacSystemFont', '"Segoe UI"',
          'Roboto', 'Helvetica', 'Arial', 'sans-serif',
        ],
      },
      borderRadius: {
        card: '8px',
      },
      boxShadow: {
        card: '0 1px 3px 0 rgba(0,0,0,0.07), 0 1px 2px -1px rgba(0,0,0,0.05)',
        'card-hover': '0 4px 6px -1px rgba(0,0,0,0.08), 0 2px 4px -2px rgba(0,0,0,0.05)',
      },
    },
  },
  plugins: [],
}
