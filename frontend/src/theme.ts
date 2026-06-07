// Light/dark theme handling. The active theme is a `.dark` class on <html>;
// the choice persists in localStorage and otherwise follows the OS preference.
export type Theme = "light" | "dark";

const STORAGE_KEY = "stocksim-theme";

export function getStoredTheme(): Theme | null {
  const v = localStorage.getItem(STORAGE_KEY);
  return v === "light" || v === "dark" ? v : null;
}

export function resolveInitialTheme(): Theme {
  const stored = getStoredTheme();
  if (stored) return stored;
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export function applyTheme(theme: Theme): void {
  document.documentElement.classList.toggle("dark", theme === "dark");
}

let themeVersion = 0;
const listeners = new Set<() => void>();

export function setTheme(theme: Theme): void {
  localStorage.setItem(STORAGE_KEY, theme);
  applyTheme(theme);
  themeVersion += 1;
  listeners.forEach((l) => l());
}

// Subscription used by imperative widgets (e.g. lightweight-charts) that can't
// consume Tailwind classes and must rebuild with fresh colors on theme change.
export function subscribeTheme(cb: () => void): () => void {
  listeners.add(cb);
  return () => listeners.delete(cb);
}

export function getThemeVersion(): number {
  return themeVersion;
}

// Resolve a `--c-<name>` palette variable to an `rgb(...)` string for canvas
// widgets. Reads the live computed value so it reflects the active theme.
function channelRaw(name: string): string {
  return getComputedStyle(document.documentElement)
    .getPropertyValue(`--c-${name}`)
    .trim();
}

function channel(name: string, alpha = 1): string {
  const raw = channelRaw(name);
  if (!raw) return "";
  const rgb = raw.split(/\s+/).join(", ");
  return alpha >= 1 ? `rgb(${rgb})` : `rgba(${rgb}, ${alpha})`;
}

export function chartTheme() {
  return {
    background: channel("panel"),
    text: channel("slate-400"),
    grid: channel("panel2"),
    border: channel("edge"),
    accent: channel("accent"),
    muted: channel("slate-500"),
    buy: channel("buy"),
    sell: channel("sell"),
    buyFill: channel("buy", 0.28),
    sellFill: channel("sell", 0.28),
    transparent: "rgba(0, 0, 0, 0)",
  };
}

// Apply the initial theme as early as possible to avoid a flash of the wrong
// palette before React mounts.
export function initTheme(): void {
  applyTheme(resolveInitialTheme());
}
