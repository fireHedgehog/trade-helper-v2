import { useEffect, useRef } from "react";
import { useColorScheme, useTheme } from "@mui/material/styles";
import {
  AreaSeries,
  ColorType,
  createChart,
  LineSeries,
  type IChartApi,
  type Time,
} from "lightweight-charts";

import { CHART_COLORS } from "@/app/theme";

import type { EquityCurve } from "./types";

export function EquityChart({ equity }: { equity: EquityCurve }) {
  const ref = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const theme = useTheme();
  const { mode, systemMode } = useColorScheme();
  const resolved = (mode === "system" ? systemMode : mode) ?? theme.palette.mode;
  const dark = resolved === "dark";

  useEffect(() => {
    const el = ref.current;
    if (!el || !equity?.dates?.length) return;
    const c = dark ? CHART_COLORS.dark : CHART_COLORS.light;

    const chart = createChart(el, {
      height: 220,
      layout: {
        background: { type: ColorType.Solid, color: c.background },
        textColor: c.text,
        fontSize: 12,
        panes: { separatorColor: c.border },
      },
      grid: { vertLines: { color: c.grid }, horzLines: { color: c.grid } },
      rightPriceScale: { borderColor: c.border },
      timeScale: { borderColor: c.border },
    });
    chartRef.current = chart;

    const strat = chart.addSeries(LineSeries, { color: "#2f6fed", lineWidth: 2, lastValueVisible: true });
    strat.setData(equity.dates.map((d, i) => ({ time: d as Time, value: equity.strat_equity[i] })));

    const bh = chart.addSeries(LineSeries, {
      color: "#8a8f98",
      lineWidth: 1,
      lastValueVisible: true,
    });
    bh.setData(equity.dates.map((d, i) => ({ time: d as Time, value: equity.bh_equity[i] })));

    const dd = chart.addSeries(
      AreaSeries,
      {
        lineColor: "#d64545",
        topColor: "#d6454533",
        bottomColor: "#d6454505",
        priceScaleId: "dd",
        lastValueVisible: false,
      },
      1,
    );
    dd.setData(equity.dates.map((d, i) => ({ time: d as Time, value: equity.drawdown[i] })));
    chart.panes()[0].setStretchFactor(3);

    chart.timeScale().fitContent();
    const ro = new ResizeObserver((e) => {
      const w = e[0]?.contentRect.width;
      if (w) chart.applyOptions({ width: w });
    });
    ro.observe(el);
    chart.applyOptions({ width: el.clientWidth });
    return () => {
      ro.disconnect();
      chart.remove();
      chartRef.current = null;
    };
  }, [dark, equity]);

  return <div ref={ref} style={{ width: "100%" }} />;
}
