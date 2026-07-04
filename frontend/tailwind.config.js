/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        'nhs-blue': '#005EB8',
        'nhs-dark': '#003087',
        'nhs-warm': '#768692',
        'nhs-green': '#009639',
        'nhs-red': '#DA291C',
        'nhs-yellow': '#FFB81C',
      },
    },
  },
  plugins: [],
}
