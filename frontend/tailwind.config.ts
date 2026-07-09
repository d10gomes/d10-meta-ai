import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        brand: {
          50: "#eff6ff",
          500: "#1d6fee",
          600: "#1557d4",
          700: "#1044b0",
          900: "#0a2d80",
        },
        surface: {
          DEFAULT: "#0d1117",
          card: "#161b22",
          border: "#21262d",
        },
      },
      fontFamily: {
        sans: ["Inter", "sans-serif"],
      },
    },
  },
  plugins: [],
  darkMode: "class",
};

export default config;
