// Sleeve taxonomy + defaults for the /sizing sandbox. All advisory — none of
// this touches the signal engine. Sleeves are 11 GICS sectors + Bonds + Crypto
// + Other (commodity ETFs, unclassified names). `assets.sector` (surfaced on
// the board response) drives the GICS bucket; the symbol lists below override
// it for cross-asset names that have no sector.

export const GICS_SLEEVES = [
  "Information Technology",
  "Communication Services",
  "Consumer Discretionary",
  "Consumer Staples",
  "Health Care",
  "Financials",
  "Industrials",
  "Energy",
  "Utilities",
  "Real Estate",
  "Materials",
] as const;

export const SLEEVES = [...GICS_SLEEVES, "Bonds", "Crypto", "Other"] as const;
export type Sleeve = (typeof SLEEVES)[number];

// Compact labels for tight table cells.
export const SLEEVE_SHORT: Record<Sleeve, string> = {
  "Information Technology": "Tech",
  "Communication Services": "Comm Svcs",
  "Consumer Discretionary": "Cons Disc",
  "Consumer Staples": "Staples",
  "Health Care": "Health",
  Financials: "Financials",
  Industrials: "Industrials",
  Energy: "Energy",
  Utilities: "Utilities",
  "Real Estate": "Real Estate",
  Materials: "Materials",
  Bonds: "Bonds",
  Crypto: "Crypto",
  Other: "Other",
};

// Coarse budget groups the optional sleeve-budget constraint works on.
export type SleeveGroup = "Equities" | "Bonds" | "Crypto" | "Other";
export const SLEEVE_GROUP: Record<Sleeve, SleeveGroup> = {
  "Information Technology": "Equities",
  "Communication Services": "Equities",
  "Consumer Discretionary": "Equities",
  "Consumer Staples": "Equities",
  "Health Care": "Equities",
  Financials: "Equities",
  Industrials: "Equities",
  Energy: "Equities",
  Utilities: "Equities",
  "Real Estate": "Equities",
  Materials: "Equities",
  Bonds: "Bonds",
  Crypto: "Crypto",
  Other: "Other",
};

// Bond / rates ETFs — no GICS sector, so route them to the Bonds sleeve.
export const BOND_ETFS = new Set([
  "AGG", "BND", "BNDX", "BIV", "BSV", "GOVT", "TLT", "TLH", "IEF", "IEI", "SHY",
  "SHV", "BIL", "EDV", "VGIT", "VGLT", "VGSH", "VCIT", "VCSH", "SPTL", "SPTS",
  "SCHP", "TIP", "VTIP", "LQD", "IGSB", "IGIB", "HYG", "JNK", "USHY", "SJNK",
  "EMB", "PCY", "MBB", "MUB", "TFI", "SUB",
]);

export const CRYPTO_SYMBOLS = new Set(["BTC/USD", "ETH/USD", "BTCUSD", "ETHUSD"]);

export function sleeveFor(row: { symbol: string; sector: string | null | undefined }): Sleeve {
  const sym = row.symbol.toUpperCase();
  if (CRYPTO_SYMBOLS.has(sym) || sym.endsWith("/USD")) return "Crypto";
  if (BOND_ETFS.has(sym)) return "Bonds";
  const s = row.sector as Sleeve | null | undefined;
  if (s && (GICS_SLEEVES as readonly string[]).includes(s)) return s;
  return "Other";
}

export const zeroDeployed = (): Record<Sleeve, number> =>
  Object.fromEntries(SLEEVES.map((s) => [s, 0])) as Record<Sleeve, number>;

// Preset "how is my book already deployed" scenarios (% of NAV per sleeve).
// Merged over a zeroed base, so a preset only lists its non-zero sleeves.
export const DEPLOYED_PRESETS: { key: string; label: string; map: Partial<Record<Sleeve, number>> }[] = [
  { key: "flat", label: "Flat", map: {} },
  {
    key: "balanced",
    label: "Balanced",
    map: {
      "Information Technology": 7, "Communication Services": 4, "Consumer Discretionary": 4,
      "Consumer Staples": 3, "Health Care": 5, Financials: 5, Industrials: 4, Energy: 3,
      Utilities: 2, "Real Estate": 2, Materials: 2, Bonds: 12, Crypto: 1, Other: 3,
    },
  },
  {
    key: "tech-heavy",
    label: "Tech-heavy (crowded)",
    map: {
      "Information Technology": 24, "Communication Services": 9, "Consumer Discretionary": 8,
      "Health Care": 3, Financials: 3, Industrials: 2, Bonds: 4, Crypto: 3, Other: 2,
    },
  },
  {
    key: "energy",
    label: "All-in energy",
    map: { Energy: 30, Materials: 8, Industrials: 6, Financials: 3, Utilities: 3, Bonds: 3, Other: 2 },
  },
];

export function presetDeployed(map: Partial<Record<Sleeve, number>>): Record<Sleeve, number> {
  return { ...zeroDeployed(), ...map };
}

export const DEFAULT_SLEEVE_BUDGET: Record<SleeveGroup, number> = {
  Equities: 0.5,
  Bonds: 0.2,
  Crypto: 0.05,
  Other: 0.25,
};

export const KMAX_GRID = [0.5, 1.0, 1.5, 2.0] as const;

export const green = "#1f9d55";
export const red = "#d64545";
export const amber = "#c98a12";
export const grey = "#8a8f98";
