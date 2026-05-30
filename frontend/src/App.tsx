import { NavLink, Route, Routes } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "./api/client";
import { Dashboard } from "./pages/Dashboard";
import { Recommendations } from "./pages/Recommendations";
import { Ticker } from "./pages/Ticker";
import { Backtest } from "./pages/Backtest";
import { Research } from "./pages/Research";
import { Settings } from "./pages/Settings";

const tabs = [
  { to: "/", label: "Dashboard", end: true },
  { to: "/recommendations", label: "Recommendations" },
  { to: "/research", label: "Research" },
  { to: "/backtest", label: "Backtest" },
  { to: "/settings", label: "Settings" },
];

export default function App() {
  const settings = useQuery({ queryKey: ["settings"], queryFn: api.settings });
  const broker = settings.data?.broker;

  return (
    <div className="min-h-full">
      <header className="border-b border-edge bg-panel/60 backdrop-blur sticky top-0 z-10">
        <div className="max-w-6xl mx-auto px-5 flex items-center gap-6 h-14">
          <span className="font-bold text-lg">
            📈 Stock<span className="text-accent">Sim</span>
          </span>
          <nav className="flex gap-1 flex-1">
            {tabs.map((t) => (
              <NavLink
                key={t.to}
                to={t.to}
                end={t.end}
                className={({ isActive }) =>
                  `px-3 py-1.5 rounded-lg text-sm ${
                    isActive ? "bg-accent/20 text-accent" : "text-slate-300 hover:bg-panel2"
                  }`
                }
              >
                {t.label}
              </NavLink>
            ))}
          </nav>
          {broker && (
            <span
              className={`text-xs px-2 py-1 rounded border ${
                broker.live_trading_enabled
                  ? "bg-sell/15 text-sell border-sell/40"
                  : "bg-buy/15 text-buy border-buy/40"
              }`}
            >
              {broker.live_trading_enabled ? "● LIVE" : "● PAPER"}
            </span>
          )}
        </div>
      </header>

      <main className="max-w-6xl mx-auto px-5 py-6">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/recommendations" element={<Recommendations />} />
          <Route path="/research" element={<Research />} />
          <Route path="/ticker/:symbol" element={<Ticker />} />
          <Route path="/backtest" element={<Backtest />} />
          <Route path="/settings" element={<Settings />} />
        </Routes>
      </main>
    </div>
  );
}
