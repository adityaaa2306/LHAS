/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        // Primary: Coral/Pink
        primary: {
          50: "#fff5f7",
          100: "#ffe4e9",
          500: "#f43f5e",
          600: "#e11d48",
          700: "#be123c",
        },
        // Secondary: Blue
        secondary: {
          500: "#3b82f6",
          600: "#2563eb",
        },
        // Accent: Purple
        accent: {
          500: "#8b5cf6",
          600: "#7c3aed",
        },
        // Neutral
        neutral: {
          50: "#fafafa",
          100: "#f3f4f6",
          200: "#e5e7eb",
          300: "#d1d5db",
          400: "#9ca3af",
          500: "#6b7280",
          600: "#4b5563",
          700: "#374151",
          800: "#1f2937",
          900: "#111827",
        },
        // Status
        status: {
          healthy: "#10b981",
          watch: "#f59e0b",
          degraded: "#ef4444",
          critical: "#991b1b",
          alert: "#dc2626",
        },
      },
      borderRadius: {
        card: "8px",
        pill: "999px",
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
      },
    },
  },
  plugins: [],
}
