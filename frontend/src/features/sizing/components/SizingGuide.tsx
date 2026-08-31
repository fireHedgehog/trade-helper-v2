import type { ReactNode } from "react";
import Accordion from "@mui/material/Accordion";
import AccordionDetails from "@mui/material/AccordionDetails";
import AccordionSummary from "@mui/material/AccordionSummary";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Divider from "@mui/material/Divider";
import Stack from "@mui/material/Stack";
import Table from "@mui/material/Table";
import TableBody from "@mui/material/TableBody";
import TableCell from "@mui/material/TableCell";
import TableRow from "@mui/material/TableRow";
import Typography from "@mui/material/Typography";
import type { SxProps, Theme } from "@mui/material/styles";
import ExpandMoreRounded from "@mui/icons-material/ExpandMoreRounded";
import MenuBookRounded from "@mui/icons-material/MenuBookRounded";

type Row = { group: string } | { name: string; def: string; what: string };

const PARAMS: Row[] = [
  { group: "Account" },
  {
    name: "Simulated NAV",
    def: "$1.0M",
    what: "Pretend account size — every $ figure scales off it. Set it to your real account, or leave it round to read the % columns.",
  },
  {
    name: "Deployed by sleeve",
    def: "all 0%",
    what: "What you already hold, as % of NAV, per sleeve. Drives 'remaining head-room', and — as the per-sector cap's already-held term — the crowding model. Presets: Flat / Balanced / Tech-heavy / All-in energy.",
  },
  { group: "Risk ladder" },
  {
    name: "Whole-book vol target",
    def: "12%",
    what: "How bumpy you want the WHOLE book per year. The main 'how aggressive' dial — lower shrinks every position. The book is only ever scaled down to hit it, never up.",
  },
  {
    name: "k_max — gross cap",
    def: "1.00×",
    what: "Ceiling on total exposure, as a multiple of NAV. 1.0 = never more than fully invested, no leverage. The frozen-research headline.",
  },
  {
    name: "Per-name cap",
    def: "10%",
    what: "No single position bigger than this % of NAV, however low-vol it looks. Weight it frees up is redistributed to the other names.",
  },
  {
    name: "Per-sector cap",
    def: "30%",
    what: "No single sleeve bigger than this share of the gross book. The anti-crowding cap — it nets off what your Deployed table already holds in that sleeve.",
  },
  {
    name: "Assumed book vol",
    def: "estimate",
    what: "'Estimate' derives book vol from the names (blunt: flat 0.35 pairwise correlation). Switch to 'override' and type a number if the estimate looks too pessimistic.",
  },
  {
    name: "Sleeve budget",
    def: "off",
    what: "Optional coarser cap — Equities 50 / Bonds 20 / Crypto 5 / Other 25 of gross.",
  },
  { group: "Scope" },
  {
    name: "Long / Short / Watchlist",
    def: "Long only",
    what: "Which board buckets to size. Short adds an option to restrict to the bond ETFs + BTC the research blessed.",
  },
  {
    name: "Whole book / New entries only",
    def: "Whole book",
    what: "'New entries only' sizes just the names that entered in the last N days — the 'signals piled up, I now have cash' workflow.",
  },
  { group: "Macro overlay" },
  {
    name: "Apply macro regime",
    def: "off",
    what: "Layers the regime throttle over the ladder. On + neutral regime → whole book ×0.65; risk-off → ×0.35 and drop known-weak names. Off = pure rules.",
  },
  {
    name: "Neutral / Risk-off scale",
    def: "0.65 / 0.35",
    what: "The multipliers above — tune your conservatism. Neutral shrinks both directions: too full fears a crash, too short fears a squeeze.",
  },
];

const VERDICTS: { v: string; color: "success" | "warning" | "default" | "error"; filled?: boolean; text: string }[] = [
  { v: "ADD", color: "success", filled: true, text: "Clean — there is head-room and only the uniform whole-book scaling applied." },
  { v: "LIGHT", color: "warning", text: "A cap (per-name or per-sector) trimmed this below its inverse-vol weight, but it still has a real target." },
  { v: "BLOCKED", color: "default", text: "The per-sector cap squeezed this to ~nothing — its sleeve is full from your Deployed table. No room here." },
  { v: "TRIM", color: "error", filled: true, text: "Your Deployed table has this name's sleeve OVER its cap. It's a cut candidate, not an add — trim the weakest peer-ranked names in that sleeve. (Per-sleeve, since the tool has no per-name holdings.)" },
  { v: "WAIT", color: "error", text: "Risk-off dropped this name outright (known-weak peer rank), or its target is too small to ticket." },
];

const OUTPUTS: [string, string][] = [
  ["Hero", "Green = head-room $ to add. Red 'Over budget' = deployed is above the target book, $ to trim. Amber = the whole book is throttled (vol-target / macro). Grey = deployed ≈ target."],
  ["Gross bar", "Deployed ┃ red over-target trim band ┃ can-add ┃ room-to-k_max ┃ macro-blocked, with a target tick and the one binding constraint spelled out."],
  ["Sleeve load", "Deployed + proposed vs the sector cap, per sleeve. An over-cap sleeve turns red and shows '▼ trim N%'."],
  ["k_max sensitivity", "The resulting target gross at k_max ∈ {0.5, 1, 1.5, 2}, so you see the slope before you drag."],
];

const CAVEATS = [
  "Deployed-by-sleeve is coarse — it assumes your existing book was itself sized by these rules. If you are lopsided, 'room to add' reads optimistic. Paste-your-holdings precision is a later add-on.",
  "Est. book vol is a blunt parametric guess (flat 0.35 correlation). If it looks too conservative, use the override.",
  "The macro zone comes from the AI regime gauge, or the naive composite if there is no run. Only the zone drives the maths; the score is context.",
  "Roughly a third of names have no GICS sector tag yet and fall into 'Other', so the per-sector cap is weaker for them.",
];

function H({ children }: { children: ReactNode }) {
  return (
    <Typography variant="overline" sx={{ display: "block", color: "text.secondary", letterSpacing: 0.8 }}>
      {children}
    </Typography>
  );
}

export function SizingGuide({ sx }: { sx?: SxProps<Theme> }) {
  return (
    <Accordion disableGutters sx={{ borderRadius: 1, "&:before": { display: "none" }, ...sx }}>
      <AccordionSummary expandIcon={<ExpandMoreRounded />}>
        <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
          <MenuBookRounded fontSize="small" color="action" />
          <Typography variant="subtitle2">How to read this page — parameters, verdicts, caveats</Typography>
        </Stack>
      </AccordionSummary>
      <AccordionDetails sx={{ pt: 0 }}>
        <Stack spacing={2.5} sx={{ maxWidth: 860, lineHeight: 1.6 }}>
          <Typography variant="body2" color="text.secondary">
            The Donchian board says <i>what</i> to hold. This page says <i>how big</i>, under a
            risk-ladder you drag, and <i>what is holding each name back</i>. It places no order and
            persists nothing.
          </Typography>

          <Box>
            <H>Use it in three steps</H>
            <Box component="ol" sx={{ m: 0, mt: 0.5, pl: 2.5, "& li": { mb: 0.75 } }}>
              <li>
                <Typography variant="body2">
                  Set <b>NAV</b> to your real account and fill <b>Deployed by sleeve</b> with what you
                  already hold (or pick a preset) — that is the &quot;how much dry powder / am I
                  already crowded&quot; input.
                </Typography>
              </li>
              <li>
                <Typography variant="body2">
                  Leave the <b>risk ladder</b> on its defaults. Read the hero and the <b>ADD</b> rows —
                  that is the clean book the rules want, and the gap versus what you hold.
                </Typography>
              </li>
              <li>
                <Typography variant="body2">
                  Now experiment: push a sleeve&apos;s Deployed to its cap and watch new breakouts
                  there turn <b>LIGHT</b> / <b>BLOCKED</b>; drop the vol target; turn the macro
                  overlay on for the institutional throttle.
                </Typography>
              </li>
            </Box>
          </Box>

          <Box>
            <H>Parameters</H>
            <Table
              size="small"
              sx={{
                mt: 0.5,
                "& td": { borderColor: "divider", verticalAlign: "top", py: 0.75 },
                "& tr:last-of-type td": { border: 0 },
              }}
            >
              <TableBody>
                {PARAMS.map((row, i) =>
                  "group" in row ? (
                    <TableRow key={`g${i}`}>
                      <TableCell
                        colSpan={3}
                        sx={{
                          bgcolor: "action.hover",
                          fontSize: 11,
                          fontWeight: 700,
                          letterSpacing: 0.6,
                          textTransform: "uppercase",
                          color: "text.secondary",
                          py: 0.5,
                        }}
                      >
                        {row.group}
                      </TableCell>
                    </TableRow>
                  ) : (
                    <TableRow key={row.name}>
                      <TableCell sx={{ fontWeight: 600, width: 190, whiteSpace: "nowrap" }}>
                        {row.name}
                      </TableCell>
                      <TableCell sx={{ width: 90 }}>
                        <Chip size="small" variant="outlined" label={row.def} sx={{ fontVariantNumeric: "tabular-nums" }} />
                      </TableCell>
                      <TableCell>
                        <Typography variant="body2" color="text.secondary">
                          {row.what}
                        </Typography>
                      </TableCell>
                    </TableRow>
                  ),
                )}
              </TableBody>
            </Table>
          </Box>

          <Box>
            <H>The four verdicts</H>
            <Stack spacing={1} sx={{ mt: 0.5 }}>
              {VERDICTS.map((x) => (
                <Stack key={x.v} direction="row" spacing={1.5} sx={{ alignItems: "flex-start" }}>
                  <Chip
                    size="small"
                    label={x.v}
                    color={x.color}
                    variant={x.filled ? "filled" : "outlined"}
                    sx={{ minWidth: 74, flexShrink: 0 }}
                  />
                  <Typography variant="body2" color="text.secondary">
                    {x.text}
                  </Typography>
                </Stack>
              ))}
            </Stack>
            <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 1 }}>
              Verdicts are per name. A whole-book throttle (vol-target, a neutral / risk-off macro
              overlay) shrinks every target evenly — that is normal, shown in the hero, and does not
              turn rows into WAIT.
            </Typography>
          </Box>

          <Box>
            <H>Reading the outputs</H>
            <Stack spacing={0.75} sx={{ mt: 0.5 }}>
              {OUTPUTS.map(([k, v]) => (
                <Typography key={k} variant="body2" color="text.secondary">
                  <b style={{ color: "inherit" }}>{k}</b> — {v}
                </Typography>
              ))}
            </Stack>
          </Box>

          <Box>
            <Divider sx={{ mb: 1.5 }} />
            <H>Known blunt edges</H>
            <Box component="ul" sx={{ m: 0, mt: 0.5, pl: 2.5, "& li": { mb: 0.5 } }}>
              {CAVEATS.map((c, i) => (
                <li key={i}>
                  <Typography variant="body2" color="text.secondary">
                    {c}
                  </Typography>
                </li>
              ))}
            </Box>
          </Box>
        </Stack>
      </AccordionDetails>
    </Accordion>
  );
}
