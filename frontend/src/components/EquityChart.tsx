import { useEffect, useRef } from "react";
import { createChart, ColorType, LineSeries, type IChartApi } from "lightweight-charts";

interface Point {
  date: string;
  equity: number;
}

// Strategy vs. benchmark equity-curve line chart.
export function EquityChart({
  strategy,
  benchmark,
}: {
  strategy: Point[];
  benchmark?: Point[];
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);

  useEffect(() => {
    if (!containerRef.current) return;
    const chart = createChart(containerRef.current, {
      layout: {
        background: { type: ColorType.Solid, color: "#141a24" },
        textColor: "#94a3b8",
      },
      grid: { vertLines: { color: "#1c2430" }, horzLines: { color: "#1c2430" } },
      rightPriceScale: { borderColor: "#2a3543" },
      timeScale: { borderColor: "#2a3543" },
      autoSize: true,
    });
    chartRef.current = chart;

    const stratSeries = chart.addSeries(LineSeries, { color: "#3b82f6", lineWidth: 2 });
    stratSeries.setData(
      strategy.map((p) => ({ time: p.date.slice(0, 10) as any, value: p.equity })),
    );

    if (benchmark && benchmark.length) {
      const benchSeries = chart.addSeries(LineSeries, {
        color: "#64748b",
        lineWidth: 1,
        lineStyle: 2,
      });
      benchSeries.setData(
        benchmark.map((p) => ({ time: p.date.slice(0, 10) as any, value: p.equity })),
      );
    }
    chart.timeScale().fitContent();
    return () => chart.remove();
  }, [strategy, benchmark]);

  return <div ref={containerRef} className="w-full h-[340px]" />;
}
