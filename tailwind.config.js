/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './SCRaices-LLM/dashboard/index_live_v3.html',
    './SCRaices-LLM/dashboard/app_compiled.js',
  ],
  theme: {
    extend: {
      colors: {
        'raices-red': '#8B2332',
        'raices-dark': '#1a1a2e',
      },
      fontFamily: {
        sans: ['IBM Plex Sans', 'sans-serif'],
        mono: ['IBM Plex Mono', 'monospace'],
      },
    },
  },
  plugins: [],
}
