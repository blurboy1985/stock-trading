import { useEffect, useRef } from "react";
import {
  createChart,
  ColorType,
  CandlestickSeries,
  AreaSeries,
  type IChartApi,
} from "lightweight-charts";
import type { Bar } from "../api/client";

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

    if (variant === "area") {
      const up = bars.length > 1 && bars[bars.length - 1].close >= bars[0].close;
      const series = chart.addSeries(AreaSeries, {
        lineColor: up ? "#1f9e6b" : "#dc4b5a",
        topColor: up ? "rgba(31,158,107,0.28)" : "rgba(220,75,90,0.28)",
        bottomColor: "rgba(255,255,255,0)",
        lineWidth: 2,
        priceLineVisible: false,
      });
      series.setData(
        bars.map((b) => ({ time: b.time.slice(0, 10) as any, value: b.close })),
      );
    } else {
      const series = chart.addSeries(CandlestickSeries, {
        upColor: "#1f9e6b",
        downColor: "#dc4b5a",
        borderVisible: false,
        wickUpColor: "#1f9e6b",
        wickDownColor: "#dc4b5a",
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
  }, [bars, variant]);

  return <div ref={containerRef} className="w-full h-[360px]" />;
}
