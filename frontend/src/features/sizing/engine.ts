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

const ASSUMED_PAIR_CORR = 0.5; // for the book-vol estimate — deliberately blunt
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
    candidates.push({
      symbol: r.symbol,
      state: r.state as "long" | "short",
      sleeve: sleeveFor({ symbol: r.symbol, sector: r.sector }),
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
  const afterName = raw.map((w) => Math.min(w, p.perNameCapPct));
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
    if (dropWeak && (c.momentum == null || c.momentum < 50)) return;
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

  const emptyBar = { deployed: deployedGrossPct, canAdd: 0, roomToKmax: 0, macroBlocked: 0 };
  const assumedVolCount = candidates.filter((c) => c.assumedVol).length;

  if (!candidates.length) {
    return {
      rows: [], excluded, assumedVolCount,
      targetGrossPct: 0, deployedGrossPct, headroomPct: 0, headroomUsd: 0, addCount: 0,
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
    const rawPct = raw[i];
    const namePct = afterName[i];
    const sectorPct = afterSector[i];
    if (namePct < rawPct - 1e-6) notes.push(`per-name cap ${p.perNameCapPct}% (P3)`);
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
    if (dropWeak && (c.momentum == null || c.momentum < 50)) {
      targetPct = 0;
      dropped = true;
      notes.push("macro risk-off — held back (weak / no peer rank)");
    } else if (p.macroEnabled && macroScale < 1) {
      notes.push(`macro ${macro.zone} ×${macroScale.toFixed(2)}`);
    }
    const sleeveCapBit = sectorPct < namePct - 1e-6; // the per-sector cap trimmed this name
    if (namePct >= rawPct - 1e-6 && sectorPct >= namePct - 1e-6 && targetPct >= 0.05) {
      notes.push(`${rawPct.toFixed(1)}% → ${targetPct.toFixed(1)}% — room to add`);
    }

    const targetUsd = (targetPct / 100) * p.nav;
    const shares = Math.max(0, Math.floor(targetUsd / c.lastClose));

    // Verdicts are per-name and narrow. Whole-book scaling (vol-target, a
    // neutral / risk-off macro overlay) shrinks every target uniformly — that
    // is normal operation, surfaced in the hero, NOT a per-row WAIT.
    let verdict: Verdict;
    if (dropped) verdict = "WAIT"; // risk-off dropped this name outright
    else if (sleeveCapBit && sectorPct < namePct * 0.5)
      verdict = "HOLD"; // the sector cap squeezed this name to ~nothing — no room in the sleeve
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
  const addCount = rows.filter((r) => r.verdict === "ADD").length;
  const maxNamePct = rows.reduce((a, r) => Math.max(a, r.targetPct), 0);
  const loads = sleeveLoads(p, rows);

  // segmented gross bar (all % of NAV, clamped so the bar never exceeds 100)
  const kmaxCeil = p.kMax * 100;
  const grossNoMacro = rows.reduce((a, r) => a + r.afterVolTargetPct, 0);
  const macroBlocked = Math.max(0, grossNoMacro - targetGrossPct);
  const canAdd = headroomPct;
  const held = Math.min(deployedGrossPct, 100);
  const roomToKmax = Math.max(0, Math.min(kmaxCeil, 100) - held - canAdd - macroBlocked);
  const bar = { deployed: held, canAdd, roomToKmax, macroBlocked };

  return {
    rows,
    excluded,
    assumedVolCount,
    targetGrossPct,
    deployedGrossPct,
    headroomPct,
    headroomUsd: (headroomPct / 100) * p.nav,
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
    return { sleeve: s, deployedPct, newPct, capPct, over: deployedPct + newPct > capPct + 1e-6 };
  }).filter((l) => l.deployedPct > 0 || l.newPct > 0);
}

function bindingConstraint(
  p: SizingParams,
  macro: MacroContext,
  x: {
    volScale: number;
    macroScale: number;
    grossCappedPct: number;
    nNameCapped: number;
    anySectorTrim: boolean;
    worstSleeve?: Sleeve;
  },
): string {
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
