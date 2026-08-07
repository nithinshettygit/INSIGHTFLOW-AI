/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        ink: "var(--ink)",
        muted: "var(--muted)",
        accent: "var(--accent)",
        panel: "var(--panel)",
        line: "var(--line)",
        soft: "var(--soft)",
      },
      fontFamily: {
        display: ["Syne", "sans-serif"],
        sans: ["Manrope", "sans-serif"],
      },
      boxShadow: {
        panel: "0 18px 40px rgba(15, 35, 40, 0.08)",
      },
    },
  },
  plugins: [],
};
