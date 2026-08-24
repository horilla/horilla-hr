window.tailwind.config = {
  theme: {
    colors: {
      white: '#FFFFFF',
      primary: {
        50: '#f6f6f6',
        100: '#F2F3FD',
        200: '#F5F6FE',
        300: '#EBEDFB',
        400: '#DFE2F9',
        500: '#C8C8FF',
        600: '#3535C8',
        700: '#2E3192',
        800: '#262878',
        900: '#171950',
      },

      dark: {
        50: '#E6E6E6',
        100: '#A8A8A8',
        200: '#515151',
        300: '#1B1D52',
        400: '#64748B',
        500: '#0B0C24',
        600: '#000000',
      },

      secondary: {
        50: '#f8fafc',
        100: '#f1f5f9',
        200: '#e2e8f0',
        300: '#cbd5e1',
        400: '#DFE2F9',
        500: '#C8C8FF',
        600: '#3535C8',
        700: '#334155',
        800: '#1e293b',
        900: '#0f172a',
      },
      success: {
        light: "#86efac",
        DEFAULT: "#22c55e",
        dark: "#15803d",
      },
      warning: {
        light: "#fde68a",
        DEFAULT: "#f59e0b",
        dark: "#b45309",
      },
      danger: {
        light: "#fca5a5",
        DEFAULT: "#ef4444",
        dark: "#b91c1c",
      },

      brand: {
        200: '#F5F6FE',
        300: '#EBEDFB',
        500: '#C8C8FF',
        600: '#3535C8',
        700: '#2E3192',
        800: '#262878',
      },

      color: {
        600: '#374151',
      },
    },
    extend: {
      boxShadow: {
        card: "0px 0px 10px rgba(0, 0, 0, 0.05)",
      },
      spacing: {
        18: "4.5rem",
        72: "18rem",
        84: "21rem",
        96: "24rem",
      },
      borderRadius: {
        "4xl": "2rem",
        "5xl": "2.5rem",
      },
      fontSize: {
        xxs: "0.625rem",
      },
      height: {
        "screen-50": "50vh",
        "screen-75": "75vh",
      },
    },
  },
};
