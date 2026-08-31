import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";

import { SLEEVE_SHORT, amber, green, grey } from "../constants";
import type { SizingResult } from "../types";

const HATCH = `repeating-linear-gradient(45deg, ${amber}, ${amber} 3px, transparent 3px, transparent 7px)`;

// Segmented gross bar: held ┃ can-add ┃ room-to-k_max ┃ macro-blocked, scaled
// so the full width is max(100, k_max×100)% of NAV. More legible than a gauge —
// you see the head-room and which band is capping you in one glance.
export function GrossBar({ result, kMaxPct }: { result: SizingResult; kMaxPct: number }) {
  const { bar, targetGrossPct } = result;
  const scale = Math.max(100, kMaxPct);
  const seg = (v: number) => `${(v / scale) * 100}%`;
  const segs: { key: string; w: number; bg: string; label: string }[] = [
    { key: "held", w: bar.deployed, bg: grey, label: `Deployed ${bar.deployed.toFixed(0)}%` },
    { key: "add", w: bar.canAdd, bg: green, label: `Can add ${bar.canAdd.toFixed(0)}%` },
    { key: "room", w: bar.roomToKmax, bg: "transparent", label: `Room to k_max ${bar.roomToKmax.toFixed(0)}%` },
    { key: "macro", w: bar.macroBlocked, bg: HATCH, label: `Macro-blocked ${bar.macroBlocked.toFixed(0)}%` },
  ].filter((s) => s.w > 0.05);

  return (
    <Box>
      <Box
        sx={{
          position: "relative",
          display: "flex",
          height: 26,
          borderRadius: 1,
          overflow: "hidden",
          border: "1px solid",
          borderColor: "divider",
          bgcolor: "action.hover",
        }}
      >
        {segs.map((s) => (
          <Tooltip key={s.key} title={s.label} arrow>
            <Box
              sx={{
                width: seg(s.w),
                background: s.bg,
                borderRight: s.key === "room" ? "none" : "1px solid rgba(255,255,255,0.35)",
              }}
            />
          </Tooltip>
        ))}
        {/* target-gross tick */}
        <Box
          sx={{
            position: "absolute",
            left: `calc(${(targetGrossPct / scale) * 100}% - 1px)`,
            top: -3,
            bottom: -3,
            width: 2,
            bgcolor: "text.primary",
          }}
        />
      </Box>
      <Stack direction="row" spacing={2} sx={{ mt: 0.75, flexWrap: "wrap" }}>
        <Legend swatch={grey} label={`Deployed ${bar.deployed.toFixed(0)}%`} />
        <Legend swatch={green} label={`Can add ${bar.canAdd.toFixed(0)}%`} />
        {bar.macroBlocked > 0.05 && <Legend swatch={HATCH} label={`Macro-blocked ${bar.macroBlocked.toFixed(0)}%`} />}
        <Legend swatch="text.primary" label={`Target gross ${targetGrossPct.toFixed(0)}%`} tick />
      </Stack>
    </Box>
  );
}

function Legend({ swatch, label, tick }: { swatch: string; label: string; tick?: boolean }) {
  return (
    <Stack direction="row" spacing={0.5} sx={{ alignItems: "center" }}>
      <Box
        sx={{
          width: tick ? 2 : 12,
          height: 12,
          borderRadius: tick ? 0 : 0.5,
          background: swatch.includes("gradient") ? swatch : undefined,
          bgcolor: swatch.includes("gradient") ? undefined : swatch,
        }}
      />
      <Typography variant="caption" color="text.secondary">
        {label}
      </Typography>
    </Stack>
  );
}

// One row per sleeve that carries weight: deployed + proposed-new stacked on a
// track, with a tick at the per-sector cap. A full / over-cap sleeve turns red.
export function SectorBar({ result }: { result: SizingResult }) {
  const loads = result.sleeveLoads;
  if (!loads.length) return null;
  const scale = Math.max(
    ...loads.map((l) => l.deployedPct + l.newPct),
    ...loads.map((l) => l.capPct),
    1,
  ) * 1.05;
  return (
    <Stack spacing={0.75}>
      {loads.map((l) => {
        const w = (v: number) => `${(v / scale) * 100}%`;
        return (
          <Box key={l.sleeve} sx={{ display: "grid", gridTemplateColumns: "104px 1fr 64px", gap: 1, alignItems: "center" }}>
            <Typography variant="caption" noWrap title={l.sleeve} sx={{ color: l.over ? "error.main" : "text.secondary" }}>
              {SLEEVE_SHORT[l.sleeve]}
            </Typography>
            <Box sx={{ position: "relative", height: 16, bgcolor: "action.hover", borderRadius: 0.5, overflow: "hidden" }}>
              <Box sx={{ position: "absolute", left: 0, top: 0, bottom: 0, width: w(l.deployedPct), bgcolor: grey }} />
              <Box
                sx={{
                  position: "absolute",
                  left: w(l.deployedPct),
                  top: 0,
                  bottom: 0,
                  width: w(l.newPct),
                  bgcolor: l.over ? "error.main" : green,
                }}
              />
              <Box sx={{ position: "absolute", left: w(l.capPct), top: -2, bottom: -2, width: 2, bgcolor: "text.primary", opacity: 0.55 }} />
            </Box>
            <Typography variant="caption" sx={{ textAlign: "right", fontVariantNumeric: "tabular-nums", color: l.over ? "error.main" : "text.secondary" }}>
              {(l.deployedPct + l.newPct).toFixed(0)}%
            </Typography>
          </Box>
        );
      })}
      <Typography variant="caption" color="text.secondary">
        Grey = already deployed · green = proposed add · tick = {result.sleeveLoads[0]?.capPct.toFixed(0)}% sector cap
      </Typography>
    </Stack>
  );
}

export function KmaxSensitivity({ result, current }: { result: SizingResult; current: number }) {
  const max = Math.max(...result.kmaxSensitivity.map((d) => d.grossPct), 1);
  return (
    <Stack spacing={0.5}>
      {result.kmaxSensitivity.map((d) => {
        const on = Math.abs(d.k - current) < 1e-6;
        return (
          <Box key={d.k} sx={{ display: "grid", gridTemplateColumns: "44px 1fr 52px", gap: 1, alignItems: "center" }}>
            <Typography variant="caption" sx={{ fontWeight: on ? 700 : 400 }}>
              {d.k.toFixed(1)}×
            </Typography>
            <Box sx={{ height: 10, bgcolor: "action.hover", borderRadius: 0.5, overflow: "hidden" }}>
              <Box sx={{ height: "100%", width: `${(d.grossPct / max) * 100}%`, bgcolor: on ? green : grey }} />
            </Box>
            <Typography variant="caption" sx={{ textAlign: "right", fontVariantNumeric: "tabular-nums", fontWeight: on ? 700 : 400 }}>
              {d.grossPct.toFixed(0)}%
            </Typography>
          </Box>
        );
      })}
    </Stack>
  );
}
