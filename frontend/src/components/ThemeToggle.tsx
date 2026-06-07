import { useState } from "react";
import { resolveInitialTheme, setTheme, type Theme } from "../theme";

export function ThemeToggle() {
  const [theme, setThemeState] = useState<Theme>(() => resolveInitialTheme());

  const toggle = () => {
    const next: Theme = theme === "dark" ? "light" : "dark";
    setTheme(next);
    setThemeState(next);
  };

  const isDark = theme === "dark";
  return (
    <button
      onClick={toggle}
      title={`Switch to ${isDark ? "light" : "dark"} theme`}
      aria-label={`Switch to ${isDark ? "light" : "dark"} theme`}
      className="text-sm px-2.5 py-1.5 rounded-full border border-edge text-slate-400 hover:bg-panel2 hover:text-slate-200 transition-colors"
    >
      {isDark ? "☀" : "☾"}
    </button>
  );
}
