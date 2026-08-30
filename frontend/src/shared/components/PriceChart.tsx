import { useEffect, useRef } from "react";
import { useColorScheme, useTheme } from "@mui/material/styles";
import {
  CandlestickSeries,
  ColorType,
  createChart,
  createSeriesMarkers,
  type IChartApi,
  type ISeriesApi,
  type ISeriesMarkersPluginApi,
  type SeriesMarker,
  type Time,
} from "lightweight-charts";

import { CHART_COLORS } from "@/app/theme";

// TradingView Lightweight Charts, fed with our own OHLC bars and our own
// Donchian entry/exit markers. One shared component for the Timing price
// chart (docs/05-timing-page.md) and any other price view.

export interface PriceBar {
  time: string; // "YYYY-MM-DD"
  open: number;
  high: number;
  low: number;
  close: number;
}

export interface TradeMarker {
  time: string; // "YYYY-MM-DD"
  side: "long" | "short";
  kind: "entry" | "exit";
  label?: string;
}

interface PriceChartProps {
  bars: PriceBar[];
  markers?: TradeMarker[];
  height?: number;
}

function toSeriesMarker(m: TradeMarker): SeriesMarker<Time> {
  const isEntry = m.kind === "entry";
  return {
    time: m.time as Time,
    position: isEntry ? "belowBar" : "aboveBar",
    shape: isEntry ? "arrowUp" : "arrowDown",
    // long = green, short = red; exits are muted.
    color: m.side === "long" ? (isEntry ? "#1f9d55" : "#7bbf9c") : isEntry ? "#d64545" : "#e39b9b",
    text: m.label ?? `${m.side} ${m.kind}`,
  };
}

export function PriceChart({ bars, markers = [], height = 380 }: PriceChartProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<ISeriesApi<"Candlestick", Time> | null>(null);
  const markersRef = useRef<ISeriesMarkersPluginApi<Time> | null>(null);

  // Resolve the active light/dark scheme (toggle-aware, falls back to theme).
  const theme = useTheme();
  const { mode, systemMode } = useColorScheme();
  const resolved = (mode === "system" ? systemMode : mode) ?? theme.palette.mode;
  const dark = resolved === "dark";

  // Create (and re-create on theme flip) the chart.
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    const c = dark ? CHART_COLORS.dark : CHART_COLORS.light;

    const chart = createChart(el, {
      height,
      layout: {
        background: { type: ColorType.Solid, color: c.background },
        textColor: c.text,
        fontSize: 12,
      },
      grid: {
        vertLines: { color: c.grid },
        horzLines: { color: c.grid },
      },
      rightPriceScale: { borderColor: c.border },
      timeScale: { borderColor: c.border },
      autoSize: false,
    });

    const series = chart.addSeries(CandlestickSeries, {
      upColor: "#1f9d55",
      downColor: "#d64545",
      wickUpColor: "#1f9d55",
      wickDownColor: "#d64545",
      borderVisible: false,
    });

    chartRef.current = chart;
    seriesRef.current = series;
    markersRef.current = createSeriesMarkers(series, []);

    const resizeObserver = new ResizeObserver((entries) => {
      const width = entries[0]?.contentRect.width;
      if (width) chart.applyOptions({ width });
    });
    resizeObserver.observe(el);
    chart.applyOptions({ width: el.clientWidth });

    return () => {
      resizeObserver.disconnect();
      chart.remove();
      chartRef.current = null;
      seriesRef.current = null;
      markersRef.current = null;
    };
  }, [height, dark]);

  // Push data whenever bars change (or the chart was re-created on theme flip).
  useEffect(() => {
    seriesRef.current?.setData(bars);
    chartRef.current?.timeScale().fitContent();
  }, [bars, dark]);

  // Push markers whenever they change (or the chart was re-created).
  useEffect(() => {
    const sorted = [...markers].sort((a, b) => (a.time < b.time ? -1 : 1));
    markersRef.current?.setMarkers(sorted.map(toSeriesMarker));
  }, [markers, dark]);

  return <div ref={containerRef} style={{ width: "100%" }} />;
}
