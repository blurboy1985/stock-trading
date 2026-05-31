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
  conviction?: number;
  agreement?: number;
  rank_score?: number;
  regime_score?: number | null;
  regime_multiplier?: number;
  regime_label?: string;
  atr_pct?: number | null;
  suggested_qty?: number | null;
  suggested_weight_pct?: number;
  liquidity_warning?: string;
  price?: number;
  in_watchlist?: boolean;
  reasons: string[];
  breakdown: Record<string, SignalBreakdown>;
}

export interface RegimeComponent {
  name: string;
  contribution: number;
  detail: string;
}

export interface Regime {
  label: "risk_on" | "neutral" | "risk_off";
  score: number;
  multiplier: number;
  reasons: string[];
  components?: RegimeComponent[];
  metrics: Record<string, number | string | boolean | null>;
}

export interface RecoResponse {
  generated_at: string | null;
  regime?: Regime | null;
  recommendations: Recommendation[];
  top_buys: Recommendation[];
  top_sells: Recommendation[];
}

export interface Proposal {
  id: number;
  created_at: string | null;
  decided_at: string | null;
  symbol: string;
  side: "buy" | "sell";
  qty: number;
  price: number;
  est_cost: number;
  equity_pct?: number | null;
  conviction?: number | null;
  atr_pct?: number | null;
  rationale: string;
  reasons: string[];
  regime?: string | null;
  blocked_reason?: string | null;
  status: "pending" | "executed" | "rejected" | "failed" | "expired";
  result?: string | null;
  source: string;
  is_paper: boolean;
}

export interface Position {
  symbol: string;
  qty: number;
  qty_available: number;
  avg_entry_price: number;
  current_price: number;
  lastday_price: number;
  market_value: number;
  cost_basis: number;
  unrealized_pl: number;
  unrealized_plpc: number;
  unrealized_intraday_pl: number;
  unrealized_intraday_plpc: number;
  change_today: number;
  asset_class: string;
  exchange: string;
  side: string;
}

export interface Account {
  account_number?: string;
  equity: number;
  last_equity: number;
  cash: number;
  buying_power: number;
  portfolio_value: number;
  long_market_value: number;
  short_market_value: number;
  position_market_value: number;
  regt_buying_power: number;
  daytrading_buying_power: number;
  initial_margin: number;
  maintenance_margin: number;
  accrued_fees: number;
  daytrade_count: number;
  pattern_day_trader: boolean;
  trading_blocked: boolean;
  account_blocked: boolean;
  currency: string;
  is_paper: boolean;
  status: string;
}

export interface OrderRow {
  id: string;
  symbol: string;
  qty: number;
  filled_qty: number;
  filled_avg_price: number | null;
  side: string;
  type: string;
  order_class: string;
  time_in_force: string;
  limit_price: number | null;
  stop_price: number | null;
  status: string;
  extended_hours: boolean;
  submitted_at: string | null;
  filled_at: string | null;
}

export interface Activity {
  id: string;
  activity_type: string;
  symbol: string;
  side: string;
  qty: number;
  cum_qty: number;
  leaves_qty: number;
  price: number;
  net_amount: number;
  order_status: string;
  description: string;
  date: string | null;
}

export interface PortfolioResponse {
  configured: boolean;
  message?: string;
  account: Account | null;
  positions: Position[];
}

export interface PortfolioHistory {
  period: string;
  timeframe: string;
  base_value: number | null;
  total_pl: number | null;
  total_pl_pct: number | null;
  points: {
    time: string;
    equity: number;
    profit_loss: number | null;
    profit_loss_pct: number | null;
  }[];
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
  exposure_pct?: number;
  turnover?: number;
  avg_holding_period?: number;
  attribution?: Record<string, number>;
  by_exit_reason?: Record<string, { count: number; pnl: number }>;
}

export interface CorrelationMatrix {
  symbols: string[];
  matrix: (number | null)[][];
}

export interface BacktestResult {
  run_id?: number;
  metrics: BacktestMetrics;
  equity_curve: { date: string; equity: number; invested_pct?: number }[];
  benchmark_curve: { date: string; equity: number }[];
  trades: Trade[];
  symbols: string[];
  correlation?: CorrelationMatrix;
}

export interface WalkForwardFold {
  fold: number;
  chosen_threshold: number;
  test_metrics: BacktestMetrics;
}

export interface WalkForwardResult {
  folds: WalkForwardFold[];
  oos_metrics: BacktestMetrics;
  oos_equity_curve: { date: string; equity: number }[];
  oos_trades: Trade[];
}

export interface SweepCell {
  threshold: number;
  tilt: number;
  sharpe: number | null;
  total_return: number | null;
  max_drawdown: number | null;
  num_trades: number | null;
}

export interface SweepResult {
  thresholds: number[];
  tilts: number[];
  cells: SweepCell[];
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
  driver?: string;
  bars_held?: number;
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
    regime_filter?: boolean;
    benchmark_symbol?: string;
    universe_source?: "most_active" | "watchlist";
    universe_size?: number;
    use_vol_sizing?: boolean;
    target_risk_pct?: number;
    min_dollar_volume?: number;
    min_price?: number;
    sentiment_backend?: "lexicon" | "llm";
    sentiment_halflife_days?: number;
    sentiment_lm_weight?: number;
    fundamentals_sector_relative?: boolean;
    news_sources?: string[];
    news_scope?: "watchlist" | "universe";
    news_per_source_limit?: number;
  };
  watchlist: string[];
  news?: {
    all_sources: string[];
    available_sources: string[];
  };
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
  proposals: (status = "pending") =>
    req<{ proposals: Proposal[] }>(`/api/proposals?status=${status}`),
  confirmProposal: (id: number) =>
    req<{ proposal: Proposal; order?: any }>(`/api/proposals/${id}/confirm`, {
      method: "POST",
    }),
  rejectProposal: (id: number) =>
    req<{ proposal: Proposal }>(`/api/proposals/${id}/reject`, { method: "POST" }),
  confirmAllProposals: () =>
    req<{ results: { proposal_id: number; symbol: string; side: string; ok: boolean; order?: any; error?: string }[] }>(
      "/api/proposals/confirm-all",
      { method: "POST" },
    ),
  portfolio: () => req<PortfolioResponse>("/api/portfolio"),
  orders: (status = "all") =>
    req<{ orders: OrderRow[] }>(`/api/portfolio/orders?status=${status}`),
  activities: (page_size = 100) =>
    req<{ activities: Activity[] }>(`/api/portfolio/activities?page_size=${page_size}`),
  cancelOrder: (id: string) =>
    req<{ cancelled: string }>(`/api/portfolio/order/${id}`, { method: "DELETE" }),
  closePosition: (symbol: string) =>
    req<any>(`/api/portfolio/position/${symbol}/close`, { method: "POST" }),
  portfolioHistory: (period = "1M") =>
    req<PortfolioHistory>(`/api/portfolio/history?period=${period}`),
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
  asset: (symbol: string) =>
    req<{
      symbol: string;
      name: string;
      exchange: string;
      tradable: boolean;
      fractionable: boolean;
    }>(`/api/market/asset/${symbol}`),
  news: (symbols: string) => req<{ news: any[] }>(`/api/market/news?symbols=${symbols}`),
  settings: () => req<AppSettings>("/api/settings"),
  updateSettings: (body: Record<string, unknown>) =>
    req<any>("/api/settings", { method: "PUT", body: JSON.stringify(body) }),
  addSymbol: (s: string) =>
    req<{ watchlist: string[] }>(`/api/settings/watchlist/${s}`, { method: "POST" }),
  removeSymbol: (s: string) =>
    req<{ watchlist: string[] }>(`/api/settings/watchlist/${s}`, { method: "DELETE" }),
  syncWatchlist: () =>
    req<{ name: string; symbols: string[]; action: string }>(
      "/api/settings/watchlist/sync",
      { method: "POST" },
    ),
  runBacktest: (body: Record<string, unknown>) =>
    req<BacktestResult>("/api/backtest/run", { method: "POST", body: JSON.stringify(body) }),
  walkForward: (body: Record<string, unknown>) =>
    req<WalkForwardResult>("/api/backtest/walkforward", {
      method: "POST",
      body: JSON.stringify(body),
    }),
  sweep: (body: Record<string, unknown>) =>
    req<SweepResult>("/api/backtest/sweep", { method: "POST", body: JSON.stringify(body) }),
  backtestRuns: () => req<{ runs: any[] }>("/api/backtest/runs"),
  regime: () => req<{ configured: boolean; regime: Regime | null }>("/api/market/regime"),
};
