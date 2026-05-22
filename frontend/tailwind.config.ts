import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        surface: {
          DEFAULT: "#0f1117",
          raised: "#161922",
          overlay: "#1c2030",
        },
        accent: {
          DEFAULT: "#6366f1",
          hover: "#818cf8",
          muted: "#4338ca",
        },
        agent: {
          director: "#f59e0b",
          writer: "#10b981",
          lorekeeper: "#8b5cf6",
          npc: "#3b82f6",
          system: "#6b7280",
        },
      },
    },
  },
  plugins: [],
};

export default config;
