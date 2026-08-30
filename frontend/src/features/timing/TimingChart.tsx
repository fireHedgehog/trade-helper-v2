import { useEffect, useRef } from "react";
import { useColorScheme, useTheme } from "@mui/material/styles";
import {
  CandlestickSeries,
  ColorType,
  createChart,
  createSeriesMarkers,
  HistogramSeries,
  LineSeries,
  LineStyle,
  type IChartApi,
  type SeriesMarker,
  type Time,
} from "lightweight-charts";

import { CHART_COLORS } from "@/app/theme";

import { kdj, macd, resample, rsi, sma } from "./indicators";
import type { KeyLevel, Marker, Overlays, Bar } from "./types";

export type Timeframe = "D" | "W" | "M";
export type RangeKey = "5D" | "1M" | "6M" | "1Y" | "5Y" | "MAX";

const RANGE_DAYS: Record<RangeKey, number> = {
  "5D": 7,
  "1M": 31,
  "6M": 183,
  "1Y": 366,
  "5Y": 1827,
  MAX: 100000,
};

const MA_COLORS: Record<number, string> = {
  5: "#e0a030",
  20: "#3d8bfd",
  50: "#9c5bd6",
  200: "#7a8390",
};

interface Props {
  bars: Bar[];
  overlays?: Overlays;
  markers: Marker[];
  keyLevels: KeyLevel[];
  timeframe: Timeframe;
  range: RangeKey;
  mas: number[];
  showKeyLevels: boolean;
  height?: number;
}

// The price pane dominates; the study panes sit below it without squashing it.
const PANE_STRETCH = [13, 1.3, 1.9, 1.5, 1.5];

function toMarker(m: Marker): SeriesMarker<Time> {
  const isEntry = m.kind === "entry";
  return {
    time: m.time as Time,
    position: isEntry ? "belowBar" : "aboveBar",
    shape: isEntry ? "arrowUp" : "arrowDown",
    color: m.side === "long" ? (isEntry ? "#1f9d55" : "#7bbf9c") : isEntry ? "#d64545" : "#e39b9b",
    text: m.label ?? `${m.side} ${m.kind}`,
  };
}

export function TimingChart({
  bars,
  overlays,
  markers,
  keyLevels,
  timeframe,
  range,
  mas,
  showKeyLevels,
  height = 1040,
}: Props) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);

  const theme = useTheme();
  const { mode, systemMode } = useColorScheme();
  const resolved = (mode === "system" ? systemMode : mode) ?? theme.palette.mode;
  const dark = resolved === "dark";

  useEffect(() => {
    const el = containerRef.current;
    if (!el || bars.length === 0) return;

    const c = dark ? CHART_COLORS.dark : CHART_COLORS.light;
    const view = resample(bars, timeframe);
    const daily = timeframe === "D";

    const chart = createChart(el, {
      height,
      layout: {
        background: { type: ColorType.Solid, color: c.background },
        textColor: c.text,
        fontSize: 12,
        panes: { separatorColor: c.border, separatorHoverColor: c.border },
      },
      grid: { vertLines: { color: c.grid }, horzLines: { color: c.grid } },
      rightPriceScale: { borderColor: c.border },
      timeScale: { borderColor: c.border, rightOffset: 4 },
      crosshair: { mode: 0 },
    });
    chartRef.current = chart;

    // --- pane 0: price ---
    const candles = chart.addSeries(CandlestickSeries, {
      upColor: "#1f9d55",
      downColor: "#d64545",
      wickUpColor: "#1f9d55",
      wickDownColor: "#d64545",
      borderVisible: false,
    });
    candles.setData(
      view.map((b) => ({ time: b.time as Time, open: b.open, high: b.high, low: b.low, close: b.close })),
    );

    for (const n of mas) {
      const line = chart.addSeries(LineSeries, {
        color: MA_COLORS[n] ?? "#888",
        lineWidth: 1,
        priceLineVisible: false,
        lastValueVisible: false,
      });
      line.setData(sma(view, n).map((p) => ({ time: p.time as Time, value: p.value })));
    }

    if (daily && overlays?.dates?.length) {
      const up = chart.addSeries(LineSeries, {
        color: "#5b9bd5aa",
        lineWidth: 1,
        lineStyle: LineStyle.Dotted,
        priceLineVisible: false,
        lastValueVisible: false,
      });
      const dn = chart.addSeries(LineSeries, {
        color: "#5b9bd5aa",
        lineWidth: 1,
        lineStyle: LineStyle.Dotted,
        priceLineVisible: false,
        lastValueVisible: false,
      });
      const stop = chart.addSeries(LineSeries, {
        color: "#d64545",
        lineWidth: 2,
        lineStyle: LineStyle.SparseDotted,
        priceLineVisible: false,
        lastValueVisible: false,
      });
      const pick = (arr: (number | null)[]) =>
        overlays.dates
          .map((d, i) => ({ time: d as Time, value: arr[i] }))
          .filter((p): p is { time: Time; value: number } => p.value != null);
      up.setData(pick(overlays.donchian_up));
      dn.setData(pick(overlays.donchian_dn));
      stop.setData(pick(overlays.stop_line));
    }

    if (daily && markers.length) {
      createSeriesMarkers(
        candles,
        [...markers].sort((a, b) => (a.time < b.time ? -1 : 1)).map(toMarker),
      );
    }

    if (daily && showKeyLevels) {
      for (const lvl of keyLevels) {
        candles.createPriceLine({
          price: lvl.price,
          color: lvl.kind === "stop" ? "#d64545" : lvl.kind.includes("support") ? "#1f9d55" : "#b0872f",
          lineWidth: 1,
          lineStyle: LineStyle.Dashed,
          axisLabelVisible: true,
          title: lvl.label,
        });
      }
    }

    // --- pane 1: volume ---
    const vol = chart.addSeries(
      HistogramSeries,
      { priceFormat: { type: "volume" }, priceLineVisible: false, lastValueVisible: false },
      1,
    );
    vol.setData(
      view.map((b) => ({
        time: b.time as Time,
        value: b.volume,
        color: b.close >= b.open ? "#1f9d5577" : "#d6454577",
      })),
    );

    // --- pane 2: MACD ---
    const mac = macd(view);
    const macHist = chart.addSeries(HistogramSeries, { priceLineVisible: false, lastValueVisible: false }, 2);
    macHist.setData(mac.hist.map((p) => ({ time: p.time as Time, value: p.value, color: p.color })));
    const macLine = chart.addSeries(
      LineSeries,
      { color: "#3d8bfd", lineWidth: 1, priceLineVisible: false, lastValueVisible: false },
      2,
    );
    macLine.setData(mac.line.map((p) => ({ time: p.time as Time, value: p.value })));
    const macSig = chart.addSeries(
      LineSeries,
      { color: "#e0a030", lineWidth: 1, priceLineVisible: false, lastValueVisible: false },
      2,
    );
    macSig.setData(mac.signalLine.map((p) => ({ time: p.time as Time, value: p.value })));

    // --- pane 3: RSI ---
    const rsiLine = chart.addSeries(
      LineSeries,
      { color: "#9c5bd6", lineWidth: 1, priceLineVisible: false, lastValueVisible: false },
      3,
    );
    rsiLine.setData(rsi(view).map((p) => ({ time: p.time as Time, value: p.value })));
    for (const g of [70, 30]) {
      rsiLine.createPriceLine({
        price: g,
        color: c.border,
        lineWidth: 1,
        lineStyle: LineStyle.Dashed,
        axisLabelVisible: false,
      });
    }

    // --- pane 4: KDJ ---
    const k = kdj(view);
    const mk = (data: { time: string; value: number }[], color: string) => {
      const s = chart.addSeries(
        LineSeries,
        { color, lineWidth: 1, priceLineVisible: false, lastValueVisible: false },
        4,
      );
      s.setData(data.map((p) => ({ time: p.time as Time, value: p.value })));
    };
    mk(k.k, "#3d8bfd");
    mk(k.d, "#e0a030");
    mk(k.j, "#d64545");

    // pane sizing — keep the price pane tall
    chart.panes().forEach((p, i) => p.setStretchFactor(PANE_STRETCH[i] ?? 1));

    // range
    const days = RANGE_DAYS[range];
    const last = view[view.length - 1].time;
    const from = new Date(new Date(last + "T00:00:00Z").getTime() - days * 864e5)
      .toISOString()
      .slice(0, 10);
    if (days >= 100000 || from <= view[0].time || from >= last) {
      chart.timeScale().fitContent();
    } else {
      chart.timeScale().setVisibleRange({ from: from as Time, to: last as Time });
    }

    const ro = new ResizeObserver((entries) => {
      const w = entries[0]?.contentRect.width;
      if (w) chart.applyOptions({ width: w });
    });
    ro.observe(el);
    chart.applyOptions({ width: el.clientWidth });

    return () => {
      ro.disconnect();
      chart.remove();
      chartRef.current = null;
    };
  }, [dark, bars, overlays, markers, keyLevels, timeframe, range, mas.join(","), showKeyLevels, height]);

  return <div ref={containerRef} style={{ width: "100%" }} />;
}
