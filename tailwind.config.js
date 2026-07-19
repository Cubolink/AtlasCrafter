const colors = {
  primary: "#2563eb",
  secondary: "#0f766e",
  accent: "#f59e0b",
  neutral: "#1f2937",
  base100: "#f8fafc",
  base200: "#eef2f7",
  base300: "#dbe4ee",
  info: "#0ea5e9",
  success: "#16a34a",
  warning: "#f59e0b",
  error: "#dc2626",
};

module.exports = {
  content: [
    "./templates/**/*.html",
    "./accounts/**/*.py",
    "./projects/**/*.py",
    "./viewer/**/*.py",
    "./renders/**/*.py",
    "./bluemap_configs/**/*.py",
  ],
  theme: {
    extend: {
      spacing: {
        sidebar: "17rem",
        header: "4rem",
      },
      colors: {
        app: {
          sidebar: "var(--app-sidebar-bg)",
          code: "var(--app-code-bg)",
        },
      },
    },
  },
  daisyui: {
    themes: [
      {
        bluemap: {
          primary: colors.primary,
          secondary: colors.secondary,
          accent: colors.accent,
          neutral: colors.neutral,
          "base-100": colors.base100,
          "base-200": colors.base200,
          "base-300": colors.base300,
          info: colors.info,
          success: colors.success,
          warning: colors.warning,
          error: colors.error,
        },
      },
    ],
  },
  plugins: [require("daisyui")],
};
