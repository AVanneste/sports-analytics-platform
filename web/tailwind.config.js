/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        dark: {
          900: '#0b0f19',
          800: '#111827',
          700: '#1f2937',
          600: '#374151',
        },
        pitch: {
          500: '#10b981',
          600: '#059669',
        },
        court: {
          500: '#38bdf8',
          600: '#0284c7',
        }
      }
    },
  },
  plugins: [],
}
