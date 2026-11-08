/** @type {import('tailwindcss').Config} */

// Everything that differs between styles and modes comes from CSS variables
// in static/styles.css. <html data-style="house|classic" data-mode="system|light|dark">
// picks the set. Colours are stored as RGB channels so `bg-accent/20` etc. work.
const v = (name) => `rgb(var(--${name}) / <alpha-value>)`;

// Corner radius per style: House is square, Classic uses Tailwind's defaults.
const radius = {
  none: '0',
  sm: 'var(--r-sm)', DEFAULT: 'var(--r)', md: 'var(--r-md)', lg: 'var(--r-lg)',
  xl: 'var(--r-xl)', '2xl': 'var(--r-2xl)', '3xl': 'var(--r-3xl)',
  pill: 'var(--r-pill)', // badges and the FAB: round in Classic, square in House
  full: '9999px',        // avatars and status dots, always round
};
// Shadows per style: House has none (plus a hard offset), Classic has soft blurs.
const shadow = {
  sm: 'var(--sh-sm)', DEFAULT: 'var(--sh)', md: 'var(--sh-md)', lg: 'var(--sh-lg)',
  xl: 'var(--sh-xl)', '2xl': 'var(--sh-2xl)', inner: 'var(--sh-inner)', none: 'none',
  hard: 'var(--sh-hard)', // FAB and modals
};

module.exports = {
  content: [
    "./templates/**/*.{html,js}",
    "./static/**/*.js",
  ],
  theme: {
    borderRadius: radius,
    boxShadow: shadow,
    extend: {
      colors: {
        primary: { bg: v('paper'), DEFAULT: v('paper'), hover: v('fill') },
        secondary: { bg: v('surface'), DEFAULT: v('surface') },
        accent: { DEFAULT: v('accent'), hover: v('accent-hover'), transparent: 'rgb(var(--accent) / 0.25)' },
        content: { primary: v('ink'), secondary: v('ink-2'), tertiary: v('faint') },
        rule: { DEFAULT: v('rule'), strong: v('rule-strong') },
        card: 'var(--card-border)', // card/bar/button outlines: strong in House, invisible in Classic
        'on-accent': v('on-accent'),
        muted: v('muted'),

        // Tailwind defaults used in templates, re-pointed at the theme
        white: v('ink'),
        black: v('black'),
        gray: {
          100: v('fill'), 300: v('ink-2'), 400: v('muted'), 500: v('faint'),
          600: v('rule'), 700: v('fill'), 800: v('ink-2'), 900: v('ink'),
        },
        red: {
          300: v('red'), 400: v('red'), 500: v('red'), 600: v('red-strong'),
          700: v('red-strong'), 800: v('red-strong'), 900: v('red'),
        },
        yellow: {
          100: v('ink'), 300: v('yellow'), 400: v('yellow'), 500: v('yellow'),
          600: v('yellow'), 700: v('yellow'), 900: v('yellow'),
        },
        green: {
          400: v('green'), 500: v('green'), 600: v('accent'), 700: v('accent-hover'), 900: v('green'),
        },
        blue: {
          300: v('blue'), 400: v('blue'), 500: v('blue'), 600: v('blue-strong'), 700: v('blue-strong'),
        },
        orange: { 600: v('orange'), 700: v('orange') },
        purple: { 400: v('purple'), 500: v('purple') },
      },
      // Accent text has its own token: the same as the accent except in OG
      // dark mode, where the accent is too dark to read on the greys.
      textColor: {
        accent: { DEFAULT: v('accent-text'), hover: v('accent-text-hover') },
      },
      fontFamily: {
        primary: 'var(--font-body)',
        display: ['"Young Serif"', 'serif'],
      },
    },
  },
  plugins: [],
}
