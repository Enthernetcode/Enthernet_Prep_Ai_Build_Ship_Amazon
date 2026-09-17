import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        eprep: {
          bg: "#0a0512",
          surface: "#140923",
          magenta: "#ff2bd6",
          purple: "#7a2bff",
          electric: "#2bb8ff",
          text: "#f5f0ff",
          muted: "#a893c4",
        },
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
      },
    },
  },
  plugins: [],
};

export default config;
