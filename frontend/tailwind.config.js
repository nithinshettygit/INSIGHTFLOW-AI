/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        ink: "var(--ink)",
        "ink-deep": "var(--ink-deep)",
        "surface-dark": "var(--surface-dark)",
        page: "var(--page)",
        muted: {
          DEFAULT: "var(--muted)",
          light: "var(--muted-light)",
        },
        accent: {
          DEFAULT: "var(--accent)",
          deep: "var(--accent-deep)",
          soft: "var(--accent-soft)",
        },
        ai: {
          DEFAULT: "var(--ai)",
          soft: "var(--ai-soft)",
        },
        amber: {
          DEFAULT: "var(--amber)",
          soft: "var(--amber-soft)",
        },
        panel: "var(--panel)",
        line: "var(--line)",
        soft: "var(--soft)",
        success: "var(--success)",
        warn: "var(--warn)",
        error: "var(--error)",
      },
      fontFamily: {
        display: ["Manrope", "system-ui", "sans-serif"],
        sans: ["Manrope", "system-ui", "sans-serif"],
      },
      borderRadius: {
        panel: "12px",
      },
      boxShadow: {
        panel: "0 1px 2px rgba(24, 24, 27, 0.04), 0 8px 24px rgba(24, 24, 27, 0.06)",
      },
    },
  },
  plugins: [],
};
