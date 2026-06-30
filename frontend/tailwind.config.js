/** @type {import('tailwindcss').Config} */
// GlowStar theme. Color tokens live as CSS variables in src/index.css and are
// mapped here so utilities like `bg-bg`, `text-accent`, `border-line` work and
// a future dark theme only needs to re-declare the variables.
export default {
  content: ['./index.html', './src/**/*.{js,jsx,ts,tsx}'],
  theme: {
    extend: {
      colors: {
        bg: 'var(--bg)',
        'bg-ambient': 'var(--bg-ambient)',
        sidebar: 'var(--sidebar)',
        line: 'var(--border)',
        'line-sidebar': 'var(--border-sidebar)',
        text: 'var(--text)',
        'text-muted': 'var(--text-muted)',
        accent: 'var(--accent)',
        'accent-strong': 'var(--accent-strong)',
      },
      backgroundImage: {
        'greeting-gradient': 'linear-gradient(90deg, #C5B6F5, #A582EA)',
        'send-gradient': 'linear-gradient(135deg, #C9B6F5, #A582EA)',
      },
      boxShadow: {
        card: '0 1px 2px rgba(17,17,17,.04), 0 6px 24px rgba(120,90,200,.06)',
        composer: '0 4px 24px rgba(120,90,200,.08)',
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'Segoe UI', 'Roboto', 'sans-serif'],
      },
      keyframes: {
        'orb-float': {
          '0%,100%': { transform: 'translateY(0)' },
          '50%': { transform: 'translateY(-6px)' },
        },
        'fade-in': {
          from: { opacity: '0', transform: 'translateY(4px)' },
          to: { opacity: '1', transform: 'translateY(0)' },
        },
      },
      animation: {
        'orb-float': 'orb-float 7s ease-in-out infinite',
        'fade-in': 'fade-in .25s ease both',
      },
    },
  },
  plugins: [],
}
