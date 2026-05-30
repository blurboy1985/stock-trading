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
        background: { type: ColorType.Solid, color: "#ffffff" },
        textColor: "#6e6886",
      },
      grid: {
        vertLines: { color: "#efedf6" },
        horzLines: { color: "#efedf6" },
      },
      rightPriceScale: { borderColor: "#e7e4f1" },
      timeScale: { borderColor: "#e7e4f1", timeVisible: false },
      autoSize: true,
    });
    chartRef.current = chart;
    const series = chart.addSeries(CandlestickSeries, {
      upColor: "#1f9e6b",
      downColor: "#dc4b5a",
      borderVisible: false,
      wickUpColor: "#1f9e6b",
      wickDownColor: "#dc4b5a",
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
