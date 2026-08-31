import Box from "@mui/material/Box";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

import type { MiniEvent, WatchSection } from "../types";
import { SymLink, StateCell } from "../TrendPage";
import { MiniChart, type MiniTf, type MiniWindow } from "./MiniChart";

const md = (d: string) => `${+d.slice(5, 7)}-${d.slice(8, 10)}`;

// compact recent-action line: "S 7-20→8-04 · L 8-14→8-24" / "… · L 8-28 open"
function actionLine(events: MiniEvent[]): string {
  if (!events.length) return "no trades on record";
  return events
    .slice(-3)
    .map((e) => {
      const side = e.dir === "long" ? "L" : "S";
      return e.exit_date ? `${side} ${md(e.entry_date)}→${md(e.exit_date)}` : `${side} ${md(e.entry_date)} open`;
    })
    .join("  ·  ");
}

interface Props {
  sections: WatchSection[];
  tf: MiniTf;
  windowKey: MiniWindow;
  mas: number[];
}

export function WatchlistCharts({ sections, tf, windowKey, mas }: Props) {
  return (
    <Stack spacing={2.5}>
      {sections.map((sec) => (
        <Box key={sec.title}>
          <Typography
            variant="caption"
            sx={{
              display: "block",
              mb: 1,
              fontWeight: 700,
              letterSpacing: 0.6,
              textTransform: "uppercase",
              color: "text.secondary",
            }}
          >
            {sec.title}
          </Typography>
          <Box
            sx={{
              display: "grid",
              gap: 1.5,
              gridTemplateColumns: {
                xs: "1fr",
                sm: "repeat(2, 1fr)",
                md: "repeat(3, 1fr)",
              },
            }}
          >
            {sec.rows.map((r) => {
              const c = r.chart;
              return (
                <Paper key={r.symbol} variant="outlined" sx={{ p: 1, minWidth: 0 }}>
                  <Stack
                    direction="row"
                    spacing={1}
                    sx={{ alignItems: "center", mb: 0.25, minWidth: 0 }}
                  >
                    <SymLink symbol={r.symbol} />
                    <StateCell row={r} />
                    <Box sx={{ flex: 1 }} />
                    {r.vol_60d != null && (
                      <Typography
                        variant="caption"
                        color="text.secondary"
                        sx={{ fontVariantNumeric: "tabular-nums" }}
                      >
                        vol {Math.round(r.vol_60d * 100)}%
                      </Typography>
                    )}
                    {r.momentum != null && (
                      <Typography
                        variant="caption"
                        color="text.secondary"
                        sx={{ fontVariantNumeric: "tabular-nums" }}
                      >
                        m{Math.round(r.momentum.score)}
                      </Typography>
                    )}
                  </Stack>
                  <Typography
                    variant="caption"
                    color="text.secondary"
                    sx={{ display: "block", mb: 0.25, fontSize: 10, lineHeight: 1.3 }}
                    noWrap
                  >
                    {c ? actionLine(c.events) : ""}
                  </Typography>
                  {c ? (
                    <MiniChart bars={c.bars} events={c.events} tf={tf} windowKey={windowKey} mas={mas} />
                  ) : (
                    <Box
                      sx={{
                        height: 150,
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "center",
                        color: "text.disabled",
                        fontSize: 12,
                      }}
                    >
                      no price history
                    </Box>
                  )}
                </Paper>
              );
            })}
          </Box>
        </Box>
      ))}
    </Stack>
  );
}
