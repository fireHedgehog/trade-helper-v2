import { useEffect, useRef } from "react";
import Box from "@mui/material/Box";
import { useColorScheme, useTheme } from "@mui/material/styles";
import {
  ColorType,
  createChart,
  createSeriesMarkers,
  HistogramSeries,
  LineSeries,
  type SeriesMarker,
  type Time,
} from "lightweight-charts";

import { CHART_COLORS } from "@/app/theme";
import { resample, sma } from "@/features/timing/indicators";
import type { Bar } from "@/features/timing/types";

import type { MiniBar, MiniEvent } from "../types";

export type MiniTf = "D" | "W";
export type MiniWindow = "1M" | "3M" | "1Y";

// visible bar count per (timeframe, window)
const WIN_BARS: Record<MiniTf, Record<MiniWindow, number>> = {
  D: { "1M": 22, "3M": 65, "1Y": 252 },
  W: { "1M": 6, "3M": 14, "1Y": 52 },
};

// fast → slow: cool → warm, thin 1px lines
export const MA_RAMP: Record<number, string> = {
  5: "#5b9bd5",
  10: "#4f9d2f",
  50: "#c98a12",
  100: "#d64545",
};

const green = "#1f9d55";
const red = "#d64545";
const grey = "#8a8f98";

function toBar(b: MiniBar): Bar {
  return { time: b.t, open: b.o, high: b.h, low: b.l, close: b.c, volume: b.v };
}

function eventMarkers(events: MiniEvent[], firstVisible: string): SeriesMarker<Time>[] {
  const out: SeriesMarker<Time>[] = [];
  for (const e of events) {
    if (e.entry_date >= firstVisible) {
      out.push({
        time: e.entry_date as Time,
        position: "belowBar",
        shape: "arrowUp",
        color: e.dir === "long" ? green : red,
        text: e.dir === "long" ? "L" : "S",
      });
    }
    if (e.exit_date && e.exit_date >= firstVisible) {
      out.push({ time: e.exit_date as Time, position: "aboveBar", shape: "arrowDown", color: grey, text: "out" });
    }
  }
  return out.sort((a, b) => ((a.time as string) < (b.time as string) ? -1 : 1));
}

interface Props {
  bars: MiniBar[];
  events: MiniEvent[];
  tf: MiniTf;
  windowKey: MiniWindow;
  mas: number[];
  height?: number;
}

export function MiniChart({ bars, events, tf, windowKey, mas, height = 150 }: Props) {
  const ref = useRef<HTMLDivElement | null>(null);
  const theme = useTheme();
  const { mode, systemMode } = useColorScheme();
  const dark = ((mode === "system" ? systemMode : mode) ?? theme.palette.mode) === "dark";

  useEffect(() => {
    const el = ref.current;
    if (!el || bars.length === 0) return;
    const c = dark ? CHART_COLORS.dark : CHART_COLORS.light;
    const view = resample(bars.map(toBar), tf);
    if (view.length === 0) return;

    const want = WIN_BARS[tf][windowKey];
    const firstVisible = view[Math.max(0, view.length - want)].time;
    const lastTime = view[view.length - 1].time;

    const chart = createChart(el, {
      height,
      autoSize: false,
      layout: {
        background: { type: ColorType.Solid, color: c.background },
        textColor: c.text,
        fontSize: 9,
        panes: { separatorColor: c.border },
      },
      grid: { vertLines: { visible: false }, horzLines: { color: c.grid } },
      rightPriceScale: { borderVisible: false, ticksVisible: false, entireTextOnly: true },
      timeScale: { borderVisible: false, ticksVisible: false, fixLeftEdge: true, fixRightEdge: true },
      crosshair: { mode: 0 },
      handleScroll: false,
      handleScale: false,
    });

    const price = chart.addSeries(LineSeries, {
      color: dark ? "#d6dae2" : "#2b2f36",
      lineWidth: 2,
      priceLineVisible: false,
      lastValueVisible: true,
    });
    price.setData(view.map((b) => ({ time: b.time as Time, value: b.close })));

    for (const n of mas) {
      const line = chart.addSeries(LineSeries, {
        color: MA_RAMP[n] ?? grey,
        lineWidth: 1,
        priceLineVisible: false,
        lastValueVisible: false,
        crosshairMarkerVisible: false,
      });
      line.setData(sma(view, n).map((p) => ({ time: p.time as Time, value: p.value })));
    }

    const markers = eventMarkers(events, firstVisible);
    if (markers.length) createSeriesMarkers(price, markers);

    const vol = chart.addSeries(
      HistogramSeries,
      { priceFormat: { type: "volume" }, priceLineVisible: false, lastValueVisible: false },
      1,
    );
    vol.setData(
      view.map((b) => ({
        time: b.time as Time,
        value: b.volume,
        color: b.close >= b.open ? `${green}55` : `${red}55`,
      })),
    );

    const panes = chart.panes();
    panes[0]?.setStretchFactor(3.4);
    panes[1]?.setStretchFactor(1);

    if (firstVisible < lastTime) {
      chart.timeScale().setVisibleRange({ from: firstVisible as Time, to: lastTime as Time });
    } else {
      chart.timeScale().fitContent();
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
    };
  }, [dark, bars, events, tf, windowKey, mas.join(","), height]);

  return <Box ref={ref} sx={{ width: "100%", height }} />;
}
