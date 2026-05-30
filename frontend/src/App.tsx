import { NavLink, Route, Routes } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "./api/client";
import { Dashboard } from "./pages/Dashboard";
import { Recommendations } from "./pages/Recommendations";
import { Automation } from "./pages/Automation";
import { Ticker } from "./pages/Ticker";
import { Backtest } from "./pages/Backtest";
import { Research } from "./pages/Research";
import { History } from "./pages/History";
import { Settings } from "./pages/Settings";
import { DisclaimerFooter } from "./components/Disclosures";
import { TradeWalkthrough, openTradeGuide } from "./components/TradeWalkthrough";

const tabs = [
  { to: "/", label: "Dashboard", end: true },
  { to: "/recommendations", label: "Recommendations" },
  { to: "/automation", label: "Automation" },
  { to: "/research", label: "Research" },
  { to: "/backtest", label: "Backtest" },
  { to: "/history", label: "History" },
  { to: "/settings", label: "Settings" },
];

export default function App() {
  const settings = useQuery({ queryKey: ["settings"], queryFn: api.settings });
  const broker = settings.data?.broker;
  const proposals = useQuery({
    queryKey: ["proposals"],
    queryFn: () => api.proposals("pending"),
    refetchInterval: 30_000,
  });
  const pendingCount = proposals.data?.proposals.length ?? 0;

  return (
    <div className="min-h-full flex flex-col">
      <header className="border-b border-edge bg-panel/80 backdrop-blur-md sticky top-0 z-10">
        <div className="max-w-6xl mx-auto px-5 flex items-center gap-7 h-16">
          <span className="font-extrabold text-lg tracking-tight">
            Stock<span className="text-accent">Sim</span>
          </span>
          <nav className="flex gap-1 flex-1">
            {tabs.map((t) => (
              <NavLink
                key={t.to}
                to={t.to}
                end={t.end}
                className={({ isActive }) =>
                  `px-3.5 py-1.5 rounded-full text-sm font-medium transition-colors ${
                    isActive
                      ? "bg-accent/10 text-accent"
                      : "text-slate-400 hover:bg-panel2 hover:text-slate-200"
                  }`
                }
              >
                {t.label}
                {t.to === "/automation" && pendingCount > 0 && (
                  <span className="ml-1.5 text-[10px] font-bold px-1.5 py-0.5 rounded-full bg-accent/20 text-accent">
                    {pendingCount}
                  </span>
                )}
              </NavLink>
            ))}
          </nav>
          <button
            onClick={openTradeGuide}
            className="text-xs font-semibold px-3 py-1.5 rounded-full border border-accent/40 text-accent bg-accent/10 hover:bg-accent/20 transition-colors"
            title="Walkthrough: how to buy & sell in StockSim"
          >
            How to trade
          </button>
          {broker && (
            <span
              className={`text-xs font-semibold px-2.5 py-1 rounded-full border ${
                broker.live_trading_enabled
                  ? "bg-sell/10 text-sell border-sell/30"
                  : "bg-buy/10 text-buy border-buy/30"
              }`}
            >
              {broker.live_trading_enabled ? "● LIVE" : "● PAPER"}
            </span>
          )}
        </div>
      </header>
      <TradeWalkthrough />

      <main className="max-w-6xl mx-auto w-full px-5 py-7 flex-1">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/recommendations" element={<Recommendations />} />
          <Route path="/automation" element={<Automation />} />
          <Route path="/research" element={<Research />} />
          <Route path="/ticker/:symbol" element={<Ticker />} />
          <Route path="/backtest" element={<Backtest />} />
          <Route path="/history" element={<History />} />
          <Route path="/settings" element={<Settings />} />
        </Routes>
      </main>

      <footer className="border-t border-edge bg-panel/60 mt-10">
        <div className="max-w-6xl mx-auto px-5 py-6">
          <DisclaimerFooter />
        </div>
      </footer>
    </div>
  );
}
