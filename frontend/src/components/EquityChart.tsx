import { useEffect, useRef, useSyncExternalStore } from "react";
import { createChart, ColorType, LineSeries, type IChartApi } from "lightweight-charts";
import { chartTheme, getThemeVersion, subscribeTheme } from "../theme";

interface Point {
  date: string;
  equity: number;
}

// lightweight-charts requires data strictly ascending and unique by time.
// History can contain multiple points on the same calendar day, which collapse
// to an identical YYYY-MM-DD time and trip an assertion. Keep the last value
// per day and sort ascending.
function toSeriesData(points: Point[]) {
  const byDay = new Map<string, number>();
  for (const p of points) {
    byDay.set(p.date.slice(0, 10), p.equity);
  }
  return [...byDay.entries()]
    .sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0))
    .map(([time, value]) => ({ time: time as any, value }));
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
      grid: { vertLines: { color: c.grid }, horzLines: { color: c.grid } },
      rightPriceScale: { borderColor: c.border },
      timeScale: { borderColor: c.border },
      autoSize: true,
    });
    chartRef.current = chart;

    const stratSeries = chart.addSeries(LineSeries, { color: c.accent, lineWidth: 2 });
    stratSeries.setData(toSeriesData(strategy));

    if (benchmark && benchmark.length) {
      const benchSeries = chart.addSeries(LineSeries, {
        color: c.muted,
        lineWidth: 1,
        lineStyle: 2,
      });
      benchSeries.setData(toSeriesData(benchmark));
    }
    chart.timeScale().fitContent();
    return () => chart.remove();
  }, [strategy, benchmark, themeVersion]);

  return <div ref={containerRef} className="w-full h-[340px]" />;
}
