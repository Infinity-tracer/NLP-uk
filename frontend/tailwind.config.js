/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // MediLab Medical Theme Colors
        'primary': '#1977cc',
        'primary-dark': '#2c4964',
        'accent': '#1977cc',
        'heading': '#2c4964',
        'text': '#444444',
        'success': '#059652',
        'error': '#df1529',
        'warning': '#ffc107',
        // Legacy NHS aliases (mapped to MediLab)
        'nhs-blue': '#1977cc',
        'nhs-dark': '#2c4964',
        'nhs-warm': '#768692',
        'nhs-green': '#059652',
        'nhs-red': '#df1529',
        'nhs-yellow': '#ffc107',
      },
      fontFamily: {
        'sans': ['Roboto', 'system-ui', '-apple-system', 'Segoe UI', 'sans-serif'],
        'heading': ['Poppins', 'sans-serif'],
        'nav': ['Raleway', 'sans-serif'],
      },
      boxShadow: {
        'medilab': '0px 2px 15px rgba(0, 0, 0, 0.1)',
        'medilab-lg': '0px 2px 35px rgba(0, 0, 0, 0.1)',
        'medilab-header': '0px 0 18px rgba(0, 0, 0, 0.1)',
      },
      borderRadius: {
        'pill': '50px',
      },
    },
  },
  plugins: [],
}
