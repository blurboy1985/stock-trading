/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: "#0b0e14",
        panel: "#141a24",
        panel2: "#1c2430",
        edge: "#2a3543",
        buy: "#22c55e",
        sell: "#ef4444",
        hold: "#64748b",
        accent: "#3b82f6",
      },
    },
  },
  plugins: [],
};
