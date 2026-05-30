/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        // ── Endowus-inspired light theme ──────────────────────────────
        bg: "#F6F5FA", // airy lavender-white canvas
        panel: "#FFFFFF", // cards
        panel2: "#F2F0F9", // subtle inset
        edge: "#E7E4F1", // soft borders
        buy: "#1F9E6B", // refined green
        sell: "#DC4B5A", // refined red
        hold: "#8E8AA0", // muted grey-violet
        accent: "#5B2BD9", // deep Endowus-like violet (use sparingly)
        // Light-theme remap of Tailwind's `slate` text ramp: LOWER index =
        // DARKER ink. This is an intentional inversion so the existing
        // text-slate-* classes across the app read as dark-on-light without
        // touching every file. 100 = primary ink … 600 = faint.
        slate: {
          100: "#211B3D",
          200: "#2C2546",
          300: "#4A4463",
          400: "#6E6886",
          500: "#9D97AE",
          600: "#BCB7C9",
          700: "#D6D2E0",
          800: "#E7E4F1",
          900: "#F2F0F9",
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
