import { useEffect, useRef } from "react";
import { createChart, ColorType, CandlestickSeries, type IChartApi } from "lightweight-charts";
import type { Bar } from "../api/client";

// Candlestick chart via TradingView lightweight-charts.
export function PriceChart({ bars }: { bars: Bar[] }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;
    const chart = createChart(containerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: "#141a24" },
        textColor: "#94a3b8",
      },
      grid: {
        vertLines: { color: "#1c2430" },
        horzLines: { color: "#1c2430" },
      },
      rightPriceScale: { borderColor: "#2a3543" },
      timeScale: { borderColor: "#2a3543", timeVisible: false },
      autoSize: true,
    });
    chartRef.current = chart;
    const series = chart.addSeries(CandlestickSeries, {
      upColor: "#22c55e",
      downColor: "#ef4444",
      borderVisible: false,
      wickUpColor: "#22c55e",
      wickDownColor: "#ef4444",
    });
    series.setData(
      bars.map((b) => ({
        time: (b.time.slice(0, 10)) as any,
        open: b.open,
        high: b.high,
        low: b.low,
        close: b.close,
      })),
    );
    chart.timeScale().fitContent();
    return () => chart.remove();
  }, [bars]);

  return <div ref={containerRef} className="w-full h-[360px]" />;
}
