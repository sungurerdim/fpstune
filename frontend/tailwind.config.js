/** @type {import('tailwindcss').Config} */
export default {
  darkMode: ["class"],
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      // Every colour goes through a CSS custom property (declared per theme
      // in index.css). A literal here would be invisible to theming — and to
      // the E9 gate, which polices the components. Keep this list and the two
      // blocks in index.css in lockstep; theme.test.ts pins the pairing.
      colors: {
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        card: "hsl(var(--card))",
        "card-elevated": "hsl(var(--card-elevated))",
        "card-foreground": "hsl(var(--card-foreground))",
        popover: "hsl(var(--popover))",
        "popover-foreground": "hsl(var(--popover-foreground))",
        primary: "hsl(var(--primary))",
        "primary-foreground": "hsl(var(--primary-foreground))",
        secondary: "hsl(var(--secondary))",
        "secondary-foreground": "hsl(var(--secondary-foreground))",
        muted: "hsl(var(--muted))",
        "muted-foreground": "hsl(var(--muted-foreground))",
        accent: "hsl(var(--accent))",
        "accent-foreground": "hsl(var(--accent-foreground))",
        destructive: "hsl(var(--destructive))",
        "destructive-foreground": "hsl(var(--destructive-foreground))",
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        success: "hsl(var(--success))",
        warning: "hsl(var(--warning))",
        "warning-foreground": "hsl(var(--warning-foreground))",
        "score-low": "hsl(var(--score-low))",
        "score-mid": "hsl(var(--score-mid))",
        "score-high": "hsl(var(--score-high))",
        "domain-hardware": "hsl(var(--domain-hardware))",
        "domain-software": "hsl(var(--domain-software))",
        "domain-game": "hsl(var(--domain-game))",
      },
      borderRadius: {
        lg: "0.5rem",
        md: "calc(0.5rem - 2px)",
        sm: "calc(0.5rem - 4px)",
      },
      // Elevation: three levels are the whole vocabulary. More levels than a
      // reader can rank is decoration.
      boxShadow: {
        raised: "0 1px 2px 0 rgb(0 0 0 / 0.25)",
        overlay: "0 4px 12px -2px rgb(0 0 0 / 0.35)",
        modal: "0 12px 32px -4px rgb(0 0 0 / 0.45)",
      },
      // Layering: named strata instead of ad-hoc z-[60]s. Each layer sits
      // above everything that must never cover it.
      zIndex: {
        sticky: "20",
        dropdown: "40",
        overlay: "50",
        modal: "60",
        toast: "70",
      },
      // Motion: one duration pair. prefers-reduced-motion handling is E7's.
      transitionDuration: {
        quick: "150ms",
        deliberate: "300ms",
      },
    },
  },
  plugins: [],
};
