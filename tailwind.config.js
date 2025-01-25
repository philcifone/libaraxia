/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./templates/**/*.{html,js}",
    "./static/**/*.js",
    "./templates/add_book.html"
  ],
  theme: {
    extend: {
      colors: {
        primary: {
          bg: '#424242',
          DEFAULT: '#424242',
          hover: '#606060'
        },
        secondary: {
          bg: '#2c2c2c',
          DEFAULT: '#2c2c2c'
        },
        accent: {
          DEFAULT: '#4f7d19',
          hover: '#6a9839',
          transparent: '#28a74678'
        },
        content: {
          primary: '#ffffff',
          secondary: '#EEEEEE'
        }
      },
      fontFamily: {
        primary: ['Outfit Variable', 'sans-serif'],
        display: ['Crimson Pro Variable', 'serif']
      }
    }
  },
  variants: {
    extend: {
        display: ['group-hover'],
        opacity: ['group-hover'],
    },
},
  plugins: [],
}