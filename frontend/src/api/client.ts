// Typed API client for the FastAPI backend (same-origin via Vite proxy).

export interface SignalBreakdown {
  score: number;
  reasons: string[];
  metrics: Record<string, number | string | null>;
  weight: number;
}

export interface Recommendation {
  symbol: string;
  action: "BUY" | "SELL" | "HOLD";
  score: number;
  confidence: number;
  price?: number;
  reasons: string[];
  breakdown: Record<string, SignalBreakdown>;
}

export interface RecoResponse {
  generated_at: string | null;
  recommendations: Recommendation[];
  top_buys: Recommendation[];
  top_sells: Recommendation[];
  auto_actions: { symbol: string; side: string; status: string; reason?: string }[];
}

export interface Position {
  symbol: string;
  qty: number;
  avg_entry_price: number;
  current_price: number;
  market_value: number;
  unrealized_pl: number;
  unrealized_plpc: number;
  side: string;
}

export interface Account {
  equity: number;
  cash: number;
  buying_power: number;
  portfolio_value: number;
  last_equity: number;
  currency: string;
  is_paper: boolean;
  status: string;
}

export interface PortfolioResponse {
  configured: boolean;
  message?: string;
  account: Account | null;
  positions: Position[];
}

export interface Bar {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface BacktestMetrics {
  starting_cash: number;
  final_equity: number;
  total_return: number;
  cagr: number;
  sharpe: number;
  sortino: number;
  max_drawdown: number;
  num_trades: number;
  win_rate: number;
  profit_factor: number | null;
  avg_win: number;
  avg_loss: number;
  benchmark_return?: number;
  alpha_vs_benchmark?: number;
}

export interface BacktestResult {
  run_id?: number;
  metrics: BacktestMetrics;
  equity_curve: { date: string; equity: number }[];
  benchmark_curve: { date: string; equity: number }[];
  trades: Trade[];
  symbols: string[];
}

export interface Trade {
  symbol: string;
  qty: number;
  entry_date: string;
  entry_price: number;
  exit_date: string;
  exit_price: number;
  pnl: number;
  return_pct: number;
  exit_reason: string;
}

export interface AppSettings {
  settings: {
    weights: Record<string, number>;
    max_position_pct: number;
    max_total_exposure_pct: number;
    stop_loss_pct: number;
    take_profit_pct: number;
    auto_trade: boolean;
    buy_threshold: number;
    sell_threshold: number;
  };
  watchlist: string[];
  broker: {
    has_credentials: boolean;
    is_paper: boolean;
    live_trading_enabled: boolean;
  };
}

async function req<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
  return res.json() as Promise<T>;
}

export const api = {
  health: () => req<{ status: string }>("/health"),
  recommendations: (refresh = false) =>
    req<RecoResponse>(`/api/recommendations?refresh=${refresh}`),
  recoHistory: (symbol?: string) =>
    req<{ history: any[] }>(
      `/api/recommendations/history${symbol ? `?symbol=${symbol}` : ""}`,
    ),
  portfolio: () => req<PortfolioResponse>("/api/portfolio"),
  orders: (status = "all") =>
    req<{ orders: any[] }>(`/api/portfolio/orders?status=${status}`),
  placeOrder: (body: {
    symbol: string;
    side: string;
    qty?: number | null;
    order_type?: string;
    limit_price?: number | null;
    confirm_live?: boolean;
  }) => req<any>("/api/portfolio/order", { method: "POST", body: JSON.stringify(body) }),
  bars: (symbol: string, days = 180) =>
    req<{ symbol: string; bars: Bar[] }>(`/api/market/bars/${symbol}?days=${days}`),
  quote: (symbol: string) => req<any>(`/api/market/quote/${symbol}`),
  news: (symbols: string) => req<{ news: any[] }>(`/api/market/news?symbols=${symbols}`),
  settings: () => req<AppSettings>("/api/settings"),
  updateSettings: (body: Record<string, unknown>) =>
    req<any>("/api/settings", { method: "PUT", body: JSON.stringify(body) }),
  addSymbol: (s: string) =>
    req<{ watchlist: string[] }>(`/api/settings/watchlist/${s}`, { method: "POST" }),
  removeSymbol: (s: string) =>
    req<{ watchlist: string[] }>(`/api/settings/watchlist/${s}`, { method: "DELETE" }),
  runBacktest: (body: Record<string, unknown>) =>
    req<BacktestResult>("/api/backtest/run", { method: "POST", body: JSON.stringify(body) }),
  backtestRuns: () => req<{ runs: any[] }>("/api/backtest/runs"),
};
