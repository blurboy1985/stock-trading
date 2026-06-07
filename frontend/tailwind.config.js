/** @type {import('tailwindcss').Config} */

// Semantic color tokens are backed by CSS variables (RGB channel triplets) so
// the whole app can switch between light and dark by toggling a `.dark` class
// on <html> — no per-component class changes needed. The `<alpha-value>`
// placeholder keeps Tailwind's opacity modifiers (e.g. bg-accent/15) working.
const token = (name) => `rgb(var(--c-${name}) / <alpha-value>)`;

export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: token("bg"), // canvas
        panel: token("panel"), // cards
        panel2: token("panel2"), // subtle inset
        edge: token("edge"), // soft borders
        buy: token("buy"),
        sell: token("sell"),
        hold: token("hold"),
        accent: token("accent"),
        // Text ink ramp. In the light theme LOWER index = DARKER ink (an
        // intentional inversion of Tailwind's default `slate`); in the dark
        // theme the same indices map to LIGHTER ink. Components keep using
        // text-slate-100 … text-slate-600 unchanged.
        slate: {
          100: token("slate-100"),
          200: token("slate-200"),
          300: token("slate-300"),
          400: token("slate-400"),
          500: token("slate-500"),
          600: token("slate-600"),
          700: token("slate-700"),
          800: token("slate-800"),
          900: token("slate-900"),
        },
      },
      fontFamily: {
        sans: [
          '"Plus Jakarta Sans"',
          "ui-sans-serif",
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "Roboto",
          "sans-serif",
        ],
      },
      boxShadow: {
        card: "0 1px 2px rgba(27,23,51,0.04), 0 6px 20px rgba(27,23,51,0.06)",
        cardhover: "0 2px 4px rgba(27,23,51,0.05), 0 10px 28px rgba(27,23,51,0.09)",
      },
    },
  },
  plugins: [],
};
