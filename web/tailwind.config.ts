import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        ink:    "#0A0E16", // fond principal — bleu nuit profond
        slate:  "#111825", // panneaux
        line:   "#1E293B", // bordures fines
        mist:   "#7C8AA0", // texte secondaire
        chalk:  "#E8EEF6", // texte principal
        pitch:  "#22C77E", // vert pelouse — domicile / positif
        signal: "#FFB020", // ambre — highlights, value
        clay:   "#FF5A6A", // rouge — extérieur / négatif
        royal:  "#3B82F6", // bleu — nul / neutre
      },
      fontFamily: {
        display: ["var(--font-display)", "system-ui", "sans-serif"],
        sans:    ["var(--font-body)", "system-ui", "sans-serif"],
        mono:    ["var(--font-mono)", "ui-monospace", "monospace"],
      },
      borderRadius: {
        card: "10px",
      },
    },
  },
  plugins: [],
};
export default config;
