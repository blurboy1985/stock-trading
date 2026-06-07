import { useEffect, useRef, useSyncExternalStore } from "react";
import {
  createChart,
  ColorType,
  CandlestickSeries,
  AreaSeries,
  type IChartApi,
} from "lightweight-charts";
import type { Bar } from "../api/client";
import { chartTheme, getThemeVersion, subscribeTheme } from "../theme";

// Price chart via TradingView lightweight-charts. Candles for short windows;
// a smoother area line once the range is long enough that wicks turn to noise.
export function PriceChart({
  bars,
  variant = "candles",
}: {
  bars: Bar[];
  variant?: "candles" | "area";
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  // Rebuild the chart with fresh palette colors whenever the theme changes.
  const themeVersion = useSyncExternalStore(subscribeTheme, getThemeVersion);

  useEffect(() => {
    if (!containerRef.current) return;
    const c = chartTheme();
    const chart = createChart(containerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: c.background },
        textColor: c.text,
      },
      grid: {
        vertLines: { color: c.grid },
        horzLines: { color: c.grid },
      },
      rightPriceScale: { borderColor: c.border },
      timeScale: { borderColor: c.border, timeVisible: false },
      autoSize: true,
    });
    chartRef.current = chart;

    if (variant === "area") {
      const up = bars.length > 1 && bars[bars.length - 1].close >= bars[0].close;
      const series = chart.addSeries(AreaSeries, {
        lineColor: up ? c.buy : c.sell,
        topColor: up ? c.buyFill : c.sellFill,
        bottomColor: c.transparent,
        lineWidth: 2,
        priceLineVisible: false,
      });
      series.setData(
        bars.map((b) => ({ time: b.time.slice(0, 10) as any, value: b.close })),
      );
    } else {
      const series = chart.addSeries(CandlestickSeries, {
        upColor: c.buy,
        downColor: c.sell,
        borderVisible: false,
        wickUpColor: c.buy,
        wickDownColor: c.sell,
      });
      series.setData(
        bars.map((b) => ({
          time: b.time.slice(0, 10) as any,
          open: b.open,
          high: b.high,
          low: b.low,
          close: b.close,
        })),
      );
    }
    chart.timeScale().fitContent();
    return () => chart.remove();
  }, [bars, variant, themeVersion]);

  return <div ref={containerRef} className="w-full h-[360px]" />;
}
