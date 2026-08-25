/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./src/**/*.{js,jsx,ts,tsx}",
    "./public/index.html"
  ],
  theme: {
    extend: {
      colors: {
        'coastal-blue': '#2A6478',
        'sand-tan': '#D4C8AE',
        'sea-green': '#3A927D',
        'deep-teal': '#1A535C',
        'wave-blue': '#4ECDC4',
      },
    },
  },
  plugins: [],
}
