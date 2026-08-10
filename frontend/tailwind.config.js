/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        ink: "var(--ink)",
        muted: "var(--muted)",
        accent: {
          DEFAULT: "var(--accent)",
          deep: "var(--accent-deep)",
          soft: "var(--accent-soft)",
        },
        signal: {
          DEFAULT: "var(--signal)",
          soft: "var(--signal-soft)",
        },
        champagne: {
          DEFAULT: "var(--champagne)",
          deep: "var(--champagne-deep)",
        },
        platinum: {
          DEFAULT: "var(--platinum)",
          deep: "var(--platinum-deep)",
        },
        mist: {
          a: "var(--mist-a)",
          b: "var(--mist-b)",
          c: "var(--mist-c)",
        },
        highlight: "var(--highlight)",
        panel: "var(--panel)",
        line: "var(--line)",
        soft: "var(--soft)",
        online: "var(--online)",
        warn: "var(--warn)",
      },
      fontFamily: {
        display: ["Syne", "sans-serif"],
        sans: ["Manrope", "sans-serif"],
      },
      boxShadow: {
        panel: "0 16px 36px rgba(6, 16, 28, 0.1)",
      },
    },
  },
  plugins: [],
};
