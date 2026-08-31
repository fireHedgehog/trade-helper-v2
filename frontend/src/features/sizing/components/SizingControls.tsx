import { type ReactNode } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Checkbox from "@mui/material/Checkbox";
import Collapse from "@mui/material/Collapse";
import Divider from "@mui/material/Divider";
import FormControlLabel from "@mui/material/FormControlLabel";
import Slider from "@mui/material/Slider";
import Stack from "@mui/material/Stack";
import Switch from "@mui/material/Switch";
import TextField from "@mui/material/TextField";
import ToggleButton from "@mui/material/ToggleButton";
import ToggleButtonGroup from "@mui/material/ToggleButtonGroup";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";

import {
  DEPLOYED_PRESETS,
  SLEEVES,
  presetDeployed,
  type Sleeve,
  type SleeveGroup,
} from "../constants";
import type { MacroContext, SizingParams } from "../types";

const money = (v: number) =>
  v >= 1e6 ? `$${(v / 1e6).toFixed(2)}M` : `$${Math.round(v / 1e3)}k`;

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <Box sx={{ mb: 2 }}>
      <Typography
        variant="caption"
        sx={{ fontWeight: 700, letterSpacing: 0.6, textTransform: "uppercase", color: "text.secondary" }}
      >
        {title}
      </Typography>
      <Box sx={{ mt: 1 }}>{children}</Box>
    </Box>
  );
}

function LabeledSlider({
  label,
  help,
  value,
  onChange,
  min,
  max,
  step,
  format,
}: {
  label: string;
  help?: string;
  value: number;
  onChange: (v: number) => void;
  min: number;
  max: number;
  step: number;
  format: (v: number) => string;
}) {
  return (
    <Box sx={{ mb: 1.5 }}>
      <Stack direction="row" sx={{ justifyContent: "space-between", alignItems: "baseline" }}>
        <Typography variant="body2">{label}</Typography>
        <Typography variant="body2" sx={{ fontWeight: 700, fontVariantNumeric: "tabular-nums" }}>
          {format(value)}
        </Typography>
      </Stack>
      <Slider
        size="small"
        value={value}
        min={min}
        max={max}
        step={step}
        onChange={(_, v) => onChange(v as number)}
        valueLabelDisplay="auto"
        valueLabelFormat={format}
      />
      {help && (
        <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: -0.5 }}>
          {help}
        </Typography>
      )}
    </Box>
  );
}

export function SizingControls({
  params: p,
  onChange,
  macro,
}: {
  params: SizingParams;
  onChange: (patch: Partial<SizingParams>) => void;
  macro: MacroContext;
}) {
  const deployedTotal = SLEEVES.reduce((a, s) => a + (p.deployed[s] ?? 0), 0);
  const setDeployed = (s: Sleeve, v: number) =>
    onChange({ deployed: { ...p.deployed, [s]: Number.isFinite(v) ? Math.max(0, v) : 0 } });
  const setBudget = (g: SleeveGroup, v: number) =>
    onChange({ sleeveBudget: { ...p.sleeveBudget, [g]: Math.max(0, v) / 100 } });

  return (
    <Box>
      <Section title="Account">
        <LabeledSlider
          label="Simulated NAV"
          value={p.nav}
          onChange={(v) => onChange({ nav: v })}
          min={100_000}
          max={5_000_000}
          step={50_000}
          format={money}
        />
      </Section>

      <Divider sx={{ mb: 2 }} />

      <Section title="Deployed by sleeve — simulate crowding">
        <Stack direction="row" spacing={0.5} sx={{ flexWrap: "wrap", mb: 1, gap: 0.5 }}>
          {DEPLOYED_PRESETS.map((preset) => (
            <Button
              key={preset.key}
              size="small"
              variant="outlined"
              onClick={() => onChange({ deployed: presetDeployed(preset.map) })}
            >
              {preset.label}
            </Button>
          ))}
        </Stack>
        <Box
          sx={{
            display: "grid",
            gridTemplateColumns: "1fr auto",
            columnGap: 1,
            rowGap: 0.5,
            alignItems: "center",
          }}
        >
          {SLEEVES.map((s) => (
            <Box key={s} sx={{ display: "contents" }}>
              <Typography variant="caption" sx={{ color: "text.secondary" }}>
                {s}
              </Typography>
              <TextField
                size="small"
                type="number"
                value={p.deployed[s] ?? 0}
                onChange={(e) => setDeployed(s, parseFloat(e.target.value))}
                slotProps={{ htmlInput: { min: 0, step: 1, style: { textAlign: "right", padding: "4px 6px", width: 52 } } }}
              />
            </Box>
          ))}
        </Box>
        <Typography
          variant="caption"
          sx={{ display: "block", mt: 1, fontWeight: 700 }}
          color={deployedTotal > 100 ? "error" : "text.secondary"}
        >
          Deployed total: {deployedTotal.toFixed(0)}% of NAV
        </Typography>
        <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>
          Assumes your current book was itself sized by these rules. Paste-your-holdings precision is a
          later add-on.
        </Typography>
      </Section>

      <Divider sx={{ mb: 2 }} />

      <Section title="Risk ladder">
        <LabeledSlider
          label="Whole-book vol target"
          help="P2 — annualised; sizes the whole book, not one name"
          value={p.volTargetPct}
          onChange={(v) => onChange({ volTargetPct: v })}
          min={8}
          max={20}
          step={0.5}
          format={(v) => `${v}%`}
        />
        <LabeledSlider
          label="k_max — gross cap"
          help="P2/P3 — total exposure ceiling, × NAV"
          value={p.kMax}
          onChange={(v) => onChange({ kMax: v })}
          min={0.5}
          max={2}
          step={0.05}
          format={(v) => `${v.toFixed(2)}×`}
        />
        <LabeledSlider
          label="Per-name cap"
          help="P3 — max any single position, % of NAV"
          value={p.perNameCapPct}
          onChange={(v) => onChange({ perNameCapPct: v })}
          min={5}
          max={15}
          step={0.5}
          format={(v) => `${v}%`}
        />
        <LabeledSlider
          label="Per-sector cap"
          help="S4 — max any one sleeve, % of target gross"
          value={p.perSectorCapPct}
          onChange={(v) => onChange({ perSectorCapPct: v })}
          min={20}
          max={40}
          step={1}
          format={(v) => `${v}%`}
        />
        <Stack direction="row" sx={{ mt: 0.5, alignItems: "center", justifyContent: "space-between" }}>
          <Typography variant="body2">Assumed book vol</Typography>
          <FormControlLabel
            control={
              <Switch
                size="small"
                checked={p.bookVolOverridePct != null}
                onChange={(e) => onChange({ bookVolOverridePct: e.target.checked ? 15 : null })}
              />
            }
            label={
              <Typography variant="caption" color="text.secondary">
                {p.bookVolOverridePct != null ? "override" : "estimate from names"}
              </Typography>
            }
          />
        </Stack>
        <Collapse in={p.bookVolOverridePct != null}>
          <LabeledSlider
            label="Book vol override"
            value={p.bookVolOverridePct ?? 15}
            onChange={(v) => onChange({ bookVolOverridePct: v })}
            min={5}
            max={40}
            step={1}
            format={(v) => `${v}%`}
          />
        </Collapse>
      </Section>

      <Divider sx={{ mb: 2 }} />

      <Section title="Sleeve budget — advanced">
        <FormControlLabel
          control={
            <Switch
              size="small"
              checked={p.enforceSleeveBudget}
              onChange={(e) => onChange({ enforceSleeveBudget: e.target.checked })}
            />
          }
          label={
            <Typography variant="body2">
              {p.enforceSleeveBudget ? "Enforcing" : "Ignoring"} sleeve budget
            </Typography>
          }
        />
        <Collapse in={p.enforceSleeveBudget}>
          <Box sx={{ mt: 1, display: "grid", gridTemplateColumns: "1fr auto", columnGap: 1, rowGap: 0.5, alignItems: "center" }}>
            {(Object.keys(p.sleeveBudget) as SleeveGroup[]).map((g) => (
              <Box key={g} sx={{ display: "contents" }}>
                <Typography variant="caption" color="text.secondary">
                  {g}
                </Typography>
                <TextField
                  size="small"
                  type="number"
                  value={Math.round((p.sleeveBudget[g] ?? 0) * 100)}
                  onChange={(e) => setBudget(g, parseFloat(e.target.value))}
                  slotProps={{ htmlInput: { min: 0, step: 5, style: { textAlign: "right", padding: "4px 6px", width: 52 } } }}
                />
              </Box>
            ))}
          </Box>
          <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.5 }}>
            % of target gross per coarse group. Equities = the 11 GICS sleeves; Other folds in
            commodity ETFs.
          </Typography>
        </Collapse>
      </Section>

      <Divider sx={{ mb: 2 }} />

      <Section title="Scope">
        <FormControlLabel
          control={<Checkbox size="small" checked={p.scopeLong} onChange={(e) => onChange({ scopeLong: e.target.checked })} />}
          label={<Typography variant="body2">Long board</Typography>}
        />
        <FormControlLabel
          control={<Checkbox size="small" checked={p.scopeShort} onChange={(e) => onChange({ scopeShort: e.target.checked })} />}
          label={<Typography variant="body2">Short board</Typography>}
        />
        <Collapse in={p.scopeShort}>
          <Box sx={{ pl: 3.5 }}>
            <Tooltip
              title="The frozen research says the short side only pays for bond ETFs and BTC/USD. Off (default) = size every short setup on the board."
              arrow
            >
              <FormControlLabel
                control={
                  <Checkbox
                    size="small"
                    checked={p.shortResearchOnly}
                    onChange={(e) => onChange({ shortResearchOnly: e.target.checked })}
                  />
                }
                label={
                  <Typography variant="caption" color="text.secondary">
                    only bond ETFs &amp; BTC (research)
                  </Typography>
                }
              />
            </Tooltip>
          </Box>
        </Collapse>
        <FormControlLabel
          control={<Checkbox size="small" checked={p.scopeWatchlist} onChange={(e) => onChange({ scopeWatchlist: e.target.checked })} />}
          label={<Typography variant="body2">Include watchlist rows</Typography>}
        />
        <Box sx={{ mt: 1 }}>
          <ToggleButtonGroup
            size="small"
            exclusive
            value={p.mode}
            onChange={(_, v) => v && onChange({ mode: v })}
          >
            <ToggleButton value="full">Whole book</ToggleButton>
            <ToggleButton value="new">New entries only</ToggleButton>
          </ToggleButtonGroup>
        </Box>
        <Collapse in={p.mode === "new"}>
          <Box sx={{ mt: 1.5 }}>
            <LabeledSlider
              label="Entered within"
              help="fits the 'signals piled up, I now have cash' workflow"
              value={p.newDays}
              onChange={(v) => onChange({ newDays: v })}
              min={1}
              max={30}
              step={1}
              format={(v) => `${v} d`}
            />
          </Box>
        </Collapse>
      </Section>

      <Divider sx={{ mb: 2 }} />

      <Section title="Macro overlay">
        <FormControlLabel
          control={
            <Switch
              size="small"
              checked={p.macroEnabled}
              onChange={(e) => onChange({ macroEnabled: e.target.checked })}
            />
          }
          label={<Typography variant="body2">Apply macro regime</Typography>}
        />
        <Typography
          variant="caption"
          sx={{ display: "block", mb: 1 }}
          color={p.macroEnabled ? "text.primary" : "text.disabled"}
        >
          {macro.label} → <b>{macro.zone}</b>
          {p.macroEnabled
            ? ` → gross ×${
                macro.zone === "risk-on"
                  ? "1.00"
                  : macro.zone === "neutral"
                    ? p.neutralScale.toFixed(2)
                    : p.riskOffScale.toFixed(2)
              }`
            : " (off — pure rule sizing)"}
        </Typography>
        <Collapse in={p.macroEnabled}>
          <LabeledSlider
            label="Neutral gross scale"
            help="both sides shrink: too full fears a crash, too short fears a squeeze"
            value={p.neutralScale}
            onChange={(v) => onChange({ neutralScale: v })}
            min={0.3}
            max={1}
            step={0.05}
            format={(v) => `×${v.toFixed(2)}`}
          />
          <LabeledSlider
            label="Risk-off gross scale"
            help="also drops names with weak / missing peer rank"
            value={p.riskOffScale}
            onChange={(v) => onChange({ riskOffScale: v })}
            min={0.1}
            max={0.8}
            step={0.05}
            format={(v) => `×${v.toFixed(2)}`}
          />
        </Collapse>
      </Section>
    </Box>
  );
}
