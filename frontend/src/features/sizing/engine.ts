// Pure position-sizing math for the /sizing sandbox. No React, no I/O — given
// the board rows in scope + the parameter set + the macro context, it returns
// the whole output payload. Every step only ever *shrinks* a name's weight, so
// the per-name table reads as a left-to-right waterfall:
//
//   inverse-vol raw  →  per-name cap  →  per-sector cap / sleeve budget
//                    →  whole-book vol target  →  macro overlay  →  target
//
// None of this is a signal. The Donchian board decides entries/exits; this
// only answers "given those, how big, and what's holding each one back".

import {
  KMAX_GRID,
  SLEEVE_GROUP,
  SLEEVES,
  sleeveFor,
  zeroDeployed,
  type Sleeve,
  type SleeveGroup,
} from "./constants";
import type {
  MacroContext,
  SizingBoard,
  SizingBoardRow,
  SizingParams,
  SizingResult,
  SizingRow,
  Verdict,
} from "./types";

// Flat pairwise correlation for the parametric book-vol estimate. A trend book
// is all long-equity-beta, but inverse-vol weighting + partial diversification
// pull the *realised* pairwise correlation well below the naive 0.5; the M4
// research (realised portfolio vol) lands near ~0.35. Deliberately blunt — the
// "assumed book vol" override on the panel is the escape hatch.
const ASSUMED_PAIR_CORR = 0.35;
// Board rows written before migration 0015 carry no vol_60d. Rather than drop
// them, size them off a placeholder σ and flag it — a fresh Trend backtest
// fills in the real figure.
const FALLBACK_VOL = 0.25;

function daysBetween(a: string | null, b: string | null): number | null {
  if (!a) return null;
  const t0 = new Date(a + "T00:00:00Z").getTime();
  const t1 = b ? new Date(b + "T00:00:00Z").getTime() : Date.now();
  return Math.round((t1 - t0) / 864e5);
}

interface Candidate {
  symbol: string;
  state: "long" | "short";
  sleeve: Sleeve;
  noSectorTag: boolean; // bucketed to a sleeve with no `sector` from the API
  vol60d: number;
  assumedVol: boolean;
  lastClose: number;
  momentum: number | null;
  daysSinceEntry: number | null;
}

function gatherCandidates(board: SizingBoard, p: SizingParams): {
  candidates: Candidate[];
  excluded: { symbol: string; reason: string }[];
} {
  const asOf = board.computed_at ? board.computed_at.slice(0, 10) : null;
  const picked = new Map<string, SizingBoardRow>();

  const take = (rows: SizingBoardRow[], side: "long" | "short") => {
    for (const r of rows) {
      if (r.state !== side) continue;
      if (side === "short" && p.shortResearchOnly) {
        const sl = sleeveFor({ symbol: r.symbol, sector: r.sector });
        if (sl !== "Bonds" && sl !== "Crypto") continue; // research: short only pays for these
      }
      if (!picked.has(r.symbol)) picked.set(r.symbol, r);
    }
  };

  if (p.scopeLong) take(board.long, "long");
  if (p.scopeShort) take(board.short, "short");
  if (p.scopeWatchlist) {
    const wl = board.watchlist.flatMap((s) => s.rows);
    if (p.scopeLong) take(wl, "long");
    if (p.scopeShort) take(wl, "short");
  }

  const candidates: Candidate[] = [];
  const excluded: { symbol: string; reason: string }[] = [];
  for (const r of picked.values()) {
    const days = daysBetween(r.state_since, asOf);
    if (p.mode === "new" && (days == null || days > p.newDays)) continue;
    if (r.last_close == null || r.last_close <= 0) {
      excluded.push({ symbol: r.symbol, reason: "no last price" });
      continue;
    }
    const hasVol = r.vol_60d != null && r.vol_60d > 0;
    const sleeve = sleeveFor({ symbol: r.symbol, sector: r.sector });
    candidates.push({
      symbol: r.symbol,
      state: r.state as "long" | "short",
      sleeve,
      noSectorTag: !r.sector && sleeve === "Other",
      vol60d: hasVol ? (r.vol_60d as number) : FALLBACK_VOL,
      assumedVol: !hasVol,
      lastClose: r.last_close,
      momentum: r.momentum ? r.momentum.score : null,
      daysSinceEntry: days,
    });
  }
  return { candidates, excluded };
}

// Book vol from name vols with a flat assumed pairwise correlation.
function estimateBookVol(weightsFrac: number[], vols: number[]): number {
  let v = 0;
  for (let i = 0; i < weightsFrac.length; i++) {
    for (let j = 0; j < weightsFrac.length; j++) {
      const rho = i === j ? 1 : ASSUMED_PAIR_CORR;
      v += weightsFrac[i] * weightsFrac[j] * vols[i] * vols[j] * rho;
    }
  }
  return Math.sqrt(Math.max(v, 0));
}

// Per-name cap WITH spill redistribution — matches the frozen-research sizing
// script (momentum_m4_sizing.py). A name over the cap is clipped; the freed
// weight is handed to the still-under-cap names in proportion to their current
// weight, iterated until it settles. Total gross is preserved (up to n × cap).
function applyPerNameCap(raw: number[], cap: number): number[] {
  const w = raw.slice();
  for (let iter = 0; iter < 6; iter++) {
    let spill = 0;
    const under: number[] = [];
    for (let i = 0; i < w.length; i++) {
      if (w[i] > cap + 1e-9) {
        spill += w[i] - cap;
        w[i] = cap;
      } else if (w[i] < cap - 1e-9) {
        under.push(i);
      }
    }
    if (spill < 1e-6 || under.length === 0) break;
    const usum = under.reduce((a, i) => a + w[i], 0);
    if (usum <= 0) break;
    for (const i of under) w[i] += spill * (w[i] / usum);
  }
  return w;
}

// Steps 1–3 (inverse-vol → per-name cap → per-sector cap / sleeve budget) for a
// given k_max. Returns the post-cap weight (% NAV) per candidate, index-aligned.
function weightsAfterCaps(
  cands: Candidate[],
  p: SizingParams,
  kMax: number,
): { afterName: number[]; afterSector: number[]; raw: number[] } {
  const refGross = kMax * 100; // the gross the caps are a fraction of
  const invVol = cands.map((c) => 1 / c.vol60d);
  const invVolSum = invVol.reduce((a, b) => a + b, 0) || 1;

  const raw = invVol.map((iv) => (iv / invVolSum) * refGross);
  const afterName = applyPerNameCap(raw, p.perNameCapPct);
  const afterSector = afterName.slice();

  // per-sector cap: allowance is a fraction of ref gross, minus what the
  // deployed-by-sleeve table already holds.
  const bySleeve = new Map<Sleeve, number[]>();
  cands.forEach((c, i) => {
    const arr = bySleeve.get(c.sleeve) ?? [];
    arr.push(i);
    bySleeve.set(c.sleeve, arr);
  });
  for (const [sleeve, idxs] of bySleeve) {
    const allowance = (p.perSectorCapPct / 100) * refGross;
    const headroom = Math.max(0, allowance - (p.deployed[sleeve] ?? 0));
    const sum = idxs.reduce((a, i) => a + afterSector[i], 0);
    if (sum > headroom && sum > 0) {
      const k = headroom / sum;
      idxs.forEach((i) => (afterSector[i] *= k));
    }
  }

  // optional sleeve budget: cap each coarse group at budget × ref gross.
  if (p.enforceSleeveBudget) {
    const byGroup = new Map<SleeveGroup, number[]>();
    cands.forEach((c, i) => {
      const g = SLEEVE_GROUP[c.sleeve];
      const arr = byGroup.get(g) ?? [];
      arr.push(i);
      byGroup.set(g, arr);
    });
    for (const [g, idxs] of byGroup) {
      const allowance = (p.sleeveBudget[g] ?? 1) * refGross;
      const sum = idxs.reduce((a, i) => a + afterSector[i], 0);
      if (sum > allowance && sum > 0) {
        const k = allowance / sum;
        idxs.forEach((i) => (afterSector[i] *= k));
      }
    }
  }

  return { afterName, afterSector, raw };
}

function grossForKmax(cands: Candidate[], p: SizingParams, macro: MacroContext, kMax: number): number {
  if (!cands.length) return 0;
  const { afterSector } = weightsAfterCaps(cands, p, kMax);
  const weightsFrac = afterSector.map((w) => w / 100);
  const vols = cands.map((c) => c.vol60d);
  const bookVol = p.bookVolOverridePct != null
    ? p.bookVolOverridePct / 100
    : estimateBookVol(weightsFrac, vols);
  const volScale = bookVol > 0 ? Math.min(1, p.volTargetPct / (bookVol * 100)) : 1;
  const macroScale = macroGrossScale(p, macro);
  const dropWeak = p.macroEnabled && macro.zone === "risk-off";
  let gross = 0;
  cands.forEach((c, i) => {
    if (dropWeak && c.momentum != null && c.momentum < 50) return; // known-weak only
    gross += afterSector[i] * volScale * macroScale;
  });
  return gross;
}

export function macroGrossScale(p: SizingParams, macro: MacroContext): number {
  if (!p.macroEnabled) return 1;
  if (macro.zone === "risk-on") return 1;
  if (macro.zone === "neutral") return p.neutralScale;
  return p.riskOffScale;
}

export function computeSizing(
  board: SizingBoard,
  p: SizingParams,
  macro: MacroContext,
): SizingResult {
  const { candidates, excluded } = gatherCandidates(board, p);
  const deployedGrossPct = SLEEVES.reduce((a, s) => a + (p.deployed[s] ?? 0), 0);

  const emptyBar = { held: deployedGrossPct, over: 0, canAdd: 0, roomToKmax: 0, macroBlocked: 0 };
  const assumedVolCount = candidates.filter((c) => c.assumedVol).length;
  const otherNoSectorCount = candidates.filter((c) => c.noSectorTag).length;

  if (!candidates.length) {
    return {
      rows: [], excluded, assumedVolCount, otherNoSectorCount,
      targetGrossPct: 0, deployedGrossPct, headroomPct: 0, headroomUsd: 0,
      overshootPct: 0, overshootUsd: 0, // no signals in scope → nothing to say about the book
      addCount: 0,
      cashAfterPct: Math.max(0, 100 - deployedGrossPct), maxNamePct: 0,
      sleeveLoads: sleeveLoads(p, []), estBookVolPct: 0, volScale: 1,
      macroScale: macroGrossScale(p, macro),
      bindingConstraint: "No on-signal names in scope — widen the scope or run the Trend backtest.",
      kmaxSensitivity: KMAX_GRID.map((k) => ({ k, grossPct: 0 })),
      bar: emptyBar,
    };
  }

  const { raw, afterName, afterSector } = weightsAfterCaps(candidates, p, p.kMax);
  const weightsFrac = afterSector.map((w) => w / 100);
  const vols = candidates.map((c) => c.vol60d);
  const estBookVol = p.bookVolOverridePct != null
    ? p.bookVolOverridePct / 100
    : estimateBookVol(weightsFrac, vols);
  const volScale = estBookVol > 0 ? Math.min(1, p.volTargetPct / (estBookVol * 100)) : 1;
  const macroScale = macroGrossScale(p, macro);
  const dropWeak = p.macroEnabled && macro.zone === "risk-off";

  const rows: SizingRow[] = candidates.map((c, i) => {
    const notes: string[] = [];
    if (c.assumedVol) notes.push("assumed 25% vol — re-run Trend for the real σ");
    if (c.noSectorTag) notes.push("no sector tag — bucketed to Other");
    const rawPct = raw[i];
    const namePct = afterName[i];
    const sectorPct = afterSector[i];
    if (namePct < rawPct - 1e-6) notes.push(`per-name cap ${p.perNameCapPct}% (P3)`);
    else if (namePct > rawPct + 1e-6) notes.push("picked up spill from capped names");
    if (sectorPct < namePct - 1e-6) {
      const allowance = (p.perSectorCapPct / 100) * p.kMax * 100;
      const headroom = Math.max(0, allowance - (p.deployed[c.sleeve] ?? 0));
      notes.push(
        headroom <= 0.05
          ? `${c.sleeve} sleeve already full (S4)`
          : `${c.sleeve} near ${p.perSectorCapPct}% sector cap — trimmed (S4)`,
      );
    }
    const volPct = sectorPct * volScale;
    if (volScale < 0.995) {
      notes.push(
        `vol-target ×${volScale.toFixed(2)} (book ${(estBookVol * 100).toFixed(0)}% > ${p.volTargetPct}%)`,
      );
    }
    let targetPct = volPct * macroScale;
    let dropped = false;
    if (dropWeak && c.momentum != null && c.momentum < 50) {
      targetPct = 0;
      dropped = true;
      notes.push(`macro risk-off — held back (peer rank ${Math.round(c.momentum)} < 50)`);
    } else if (p.macroEnabled && macroScale < 1) {
      notes.push(`macro ${macro.zone} ×${macroScale.toFixed(2)}`);
    }
    const sleeveCapBit = sectorPct < namePct - 1e-6; // the per-sector cap trimmed this name
    // Your deployed-by-sleeve table has this name's sleeve above its own cap —
    // it is a candidate to cut, not to add. (Per-sleeve, since the tool has no
    // per-name holdings — trim the weakest peer-ranked names in the sleeve.)
    const sleeveCapPct = (p.perSectorCapPct / 100) * p.kMax * 100;
    const sleeveTrimPct = Math.max(0, (p.deployed[c.sleeve] ?? 0) - sleeveCapPct);
    if (sleeveTrimPct > 0.5) {
      notes.push(`${c.sleeve} is ${sleeveTrimPct.toFixed(0)}% over its ${p.perSectorCapPct}% cap — trim this sleeve`);
    }
    if (namePct >= rawPct - 1e-6 && sectorPct >= namePct - 1e-6 && targetPct >= 0.05 && sleeveTrimPct <= 0.5) {
      notes.push(`${rawPct.toFixed(1)}% → ${targetPct.toFixed(1)}% — room to add`);
    }

    const targetUsd = (targetPct / 100) * p.nav;
    const shares = Math.max(0, Math.floor(targetUsd / c.lastClose));

    // Verdicts are per-name and narrow. Whole-book scaling (vol-target, a
    // neutral / risk-off macro overlay) shrinks every target uniformly — that
    // is normal operation, surfaced in the hero, NOT a per-row WAIT.
    let verdict: Verdict;
    if (sleeveTrimPct > 0.5)
      verdict = "TRIM"; // your book is over-allocated to this sleeve — cut here
    else if (dropped) verdict = "WAIT"; // risk-off dropped this name outright
    else if (sleeveCapBit && sectorPct < namePct * 0.5)
      verdict = "BLOCKED"; // the sector cap squeezed this name to ~nothing — no room in the sleeve
    else if (sectorPct < rawPct - 1e-6) verdict = "LIGHT"; // a cap trimmed this name, still sized
    else if (targetPct < 0.05) verdict = "WAIT"; // otherwise too small to ticket
    else verdict = "ADD";

    return {
      symbol: c.symbol,
      state: c.state,
      sleeve: c.sleeve,
      vol60d: c.vol60d,
      lastClose: c.lastClose,
      momentum: c.momentum,
      daysSinceEntry: c.daysSinceEntry,
      invVolRawPct: rawPct,
      afterNameCapPct: namePct,
      afterSectorCapPct: sectorPct,
      afterVolTargetPct: volPct,
      targetPct,
      targetUsd,
      shares,
      verdict,
      notes,
    };
  });

  rows.sort((a, b) => b.targetPct - a.targetPct || a.symbol.localeCompare(b.symbol));

  const targetGrossPct = rows.reduce((a, r) => a + r.targetPct, 0);
  const headroomPct = Math.max(0, targetGrossPct - deployedGrossPct);
  const overshootPct = Math.max(0, deployedGrossPct - targetGrossPct);
  const addCount = rows.filter((r) => r.verdict === "ADD").length;
  const maxNamePct = rows.reduce((a, r) => Math.max(a, r.targetPct), 0);
  const loads = sleeveLoads(p, rows);

  // segmented gross bar (all % of NAV, clamped so the bar never exceeds 100).
  // held ┃ over (red, = deployed above target) ┃ can-add ┃ room-to-k_max ┃ macro-blocked
  const kmaxCeil = p.kMax * 100;
  const barMax = Math.min(Math.max(kmaxCeil, deployedGrossPct), 100);
  const grossNoMacro = rows.reduce((a, r) => a + r.afterVolTargetPct, 0);
  const macroBlocked = Math.max(0, grossNoMacro - targetGrossPct);
  const held = Math.min(deployedGrossPct, targetGrossPct);
  const over = Math.min(overshootPct, Math.max(0, 100 - held));
  const canAdd = headroomPct;
  const roomToKmax = Math.max(0, barMax - held - over - canAdd - macroBlocked);
  const bar = { held, over, canAdd, roomToKmax, macroBlocked };

  return {
    rows,
    excluded,
    assumedVolCount,
    otherNoSectorCount,
    targetGrossPct,
    deployedGrossPct,
    headroomPct,
    headroomUsd: (headroomPct / 100) * p.nav,
    overshootPct,
    overshootUsd: (overshootPct / 100) * p.nav,
    addCount,
    cashAfterPct: Math.max(0, 100 - Math.max(deployedGrossPct, targetGrossPct)),
    maxNamePct,
    sleeveLoads: loads,
    estBookVolPct: estBookVol * 100,
    volScale,
    macroScale,
    bindingConstraint: bindingConstraint(p, macro, {
      volScale,
      macroScale,
      overshootPct,
      grossCappedPct: rows.reduce((a, r) => a + r.afterSectorCapPct, 0),
      nNameCapped: rows.filter((r) => r.afterNameCapPct < r.invVolRawPct - 1e-6).length,
      anySectorTrim: rows.some((r) => r.afterSectorCapPct < r.afterNameCapPct - 1e-6),
      worstSleeve: loads.slice().sort((a, b) => b.newPct + b.deployedPct - (a.newPct + a.deployedPct))[0]?.sleeve,
    }),
    kmaxSensitivity: KMAX_GRID.map((k) => ({
      k,
      grossPct: grossForKmax(candidates, p, macro, k),
    })),
    bar,
  };
}

function sleeveLoads(p: SizingParams, rows: SizingRow[]) {
  const capPct = (p.perSectorCapPct / 100) * p.kMax * 100;
  const newBySleeve = new Map<Sleeve, number>();
  for (const r of rows) newBySleeve.set(r.sleeve, (newBySleeve.get(r.sleeve) ?? 0) + r.targetPct);
  const base = zeroDeployed();
  return SLEEVES.map((s) => {
    const deployedPct = p.deployed[s] ?? base[s];
    const newPct = newBySleeve.get(s) ?? 0;
    const trimPct = Math.max(0, deployedPct - capPct);
    return {
      sleeve: s,
      deployedPct,
      newPct,
      capPct,
      trimPct,
      over: deployedPct + newPct > capPct + 1e-6,
    };
  }).filter((l) => l.deployedPct > 0 || l.newPct > 0);
}

function bindingConstraint(
  p: SizingParams,
  macro: MacroContext,
  x: {
    volScale: number;
    macroScale: number;
    overshootPct: number;
    grossCappedPct: number;
    nNameCapped: number;
    anySectorTrim: boolean;
    worstSleeve?: Sleeve;
  },
): string {
  if (x.overshootPct >= 1) {
    return `Deployed is ${x.overshootPct.toFixed(0)}% of NAV above the target book — trim, don't add.`;
  }
  if (p.macroEnabled && x.macroScale < 1 && x.macroScale <= x.volScale) {
    return `Macro overlay (${macro.zone}${macro.score != null ? ` · ${macro.label}` : ""}) is binding — whole-book gross ×${x.macroScale.toFixed(2)}.`;
  }
  if (x.volScale < 0.995) {
    return `Vol-target is binding — estimated book vol above the ${p.volTargetPct}% target → ×${x.volScale.toFixed(2)}.`;
  }
  if (x.anySectorTrim && x.worstSleeve) {
    return `Per-sector cap is binding — the ${x.worstSleeve} sleeve is at its ${p.perSectorCapPct}%-of-gross limit.`;
  }
  if (x.grossCappedPct < p.kMax * 100 - 0.5) {
    return `Per-name cap is binding — ${x.nNameCapped} name${x.nNameCapped === 1 ? "" : "s"} clipped to ${p.perNameCapPct}% of NAV.`;
  }
  return `Gross is at k_max (${p.kMax.toFixed(2)}×) — more only if you raise k_max.`;
}
