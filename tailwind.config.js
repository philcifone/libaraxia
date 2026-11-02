/** @type {import('tailwindcss').Config} */

// Colours come from the Gruvbox CSS variables in static/styles.css (light in :root,
// dark under prefers-color-scheme). Stored as RGB channels so `bg-accent/20` etc. work.
const v = (name) => `rgb(var(--${name}) / <alpha-value>)`;

// Every square: replace (not extend) radius and shadow scales.
const square = {
  none: '0', sm: '0', DEFAULT: '0', md: '0', lg: '0', xl: '0', '2xl': '0', '3xl': '0',
  full: '9999px', // avatars and status dots only
};
const flat = {
  sm: 'none', DEFAULT: 'none', md: 'none', lg: 'none', xl: 'none', '2xl': 'none', inner: 'none', none: 'none',
  hard: '4px 4px 0 rgb(var(--ink))', // FAB, dropdowns, modals
};

module.exports = {
  content: [
    "./templates/**/*.{html,js}",
    "./static/**/*.js",
  ],
  theme: {
    borderRadius: square,
    boxShadow: flat,
    extend: {
      colors: {
        primary: { bg: v('paper'), DEFAULT: v('paper'), hover: v('fill') },
        secondary: { bg: v('surface'), DEFAULT: v('surface') },
        accent: { DEFAULT: v('accent'), hover: v('accent-hover'), transparent: 'rgb(var(--accent) / 0.25)' },
        content: { primary: v('ink'), secondary: v('ink-2'), tertiary: v('faint') },
        rule: { DEFAULT: v('rule'), strong: v('rule-strong') },
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
          300: v('blue'), 400: v('blue'), 500: v('blue'), 600: v('blue'), 700: v('blue'),
        },
        orange: { 600: v('orange'), 700: v('orange') },
        purple: { 400: v('purple'), 500: v('purple') },
      },
      fontFamily: {
        primary: ['"Courier Prime"', '"Courier New"', 'monospace'],
        display: ['"Young Serif"', 'serif'],
      },
    },
  },
  plugins: [],
}
