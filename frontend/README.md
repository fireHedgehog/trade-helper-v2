# Frontend

React + TypeScript + Vite. Local-first admin/research UI. All UI copy is
English.

## UI stack

- **MUI (Material UI) v9** — `@mui/material` + `@emotion/*`, `@mui/icons-material`,
  `@mui/x-data-grid` (MIT tier, for the dense tables on Multisectional / Trend /
  Data management later). Theme in `src/app/theme.ts` uses CSS-variable
  `colorSchemes` (light + dark). The active scheme follows the OS; the toggle in
  the drawer header (`ColorModeToggle`, cycles system → light → dark) overrides
  it and MUI persists the choice in `localStorage`. No separate CSS file —
  Emotion injects styles at runtime. `PriceChart` reads the resolved scheme and
  recolors the TradingView canvas (which cannot use CSS variables) from
  `CHART_COLORS` in `theme.ts`.
- **TradingView Lightweight Charts** (`lightweight-charts`, Apache-2.0, on npm) —
  fed with our own OHLC bars + our own Donchian entry/exit markers. Wrapped once
  in `src/shared/components/PriceChart.tsx` and reused wherever a price chart is
  needed (Timing first). This is the free, self-hosted, npm-installable
  TradingView product. The gated **Advanced Charts / Charting Library** (full
  indicator + drawing UI, apply for access, self-host, implement a Datafeed) is
  the upgrade path if we ever need it; the embeddable widget is not usable here
  because it renders TradingView's data, not ours.

## Layout

```
src/
  main.tsx                 ThemeProvider + CssBaseline + router
  app/
    router.tsx             route table + NAV_ITEMS (menu order)
    AppShell.tsx           MUI permanent Drawer nav + <Outlet/>
    theme.ts               MUI theme + DRAWER_WIDTH
  shared/
    api/client.ts          fetch wrapper + ApiError
    components/            StatusPill (Chip), Placeholder, PriceChart (TradingView)
  features/
    credentials/           one feature = page + api + types + components/
      CredentialsPage.tsx
      api.ts
      types.ts
      components/ProviderCard.tsx
    timing/                TimingPage.tsx + sampleData.ts (demo chart, sample data)
    data-management/       DataManagementPage + FetchPanel (button→poll→progress)
                           + ServerTable / SimpleTable / DetailDialog
    macro/                 MacroPage — full-width AI regime panel (RegimeGauge +
                           RegimeControls model/budget picker + per-analyst
                           breakdown) + naive CompositeReadout (plain-language
                           reading + factor table) + category grids of MacroCard
                           sparklines. Uses @mui/x-charts (Gauge + SparkLineChart).
    multisectional/ trend/ (placeholders for now — each grows its own folder)
```

Every page is its own `features/<name>/` folder — page component, its API
module, its types, its sub-components. Nothing shared lives under a feature;
it goes in `shared/`.

## Run

```bash
cd frontend
npm install
npm run dev            # http://localhost:5173
```

The dev server proxies `/api` to `http://localhost:8000` (the backend) — see
`vite.config.ts`. Start the backend first (see `../backend/README.md`).

```bash
npm run typecheck     # tsc, no emit
npm run build         # tsc -b && vite build
```

## Credentials page

- One card per provider (FRED, Alpaca), served from `GET /api/credentials`.
- FRED shows one field (API Key); Alpaca shows two (API Key ID + API Secret
  Key) because Alpaca credentials are an identify-plus-authenticate pair. The
  card text explains this.
- Inputs are `type="password"`, `autoComplete="off"`, and never pre-filled —
  the API never returns a secret. Blank field = keep current value.
- **Save** → `PUT /api/credentials/{provider}` (write-only), clears inputs.
- **Test** → `POST /api/credentials/{provider}/verify`, makes one real
  minimal call to the provider and shows `healthy` / `invalid`.
- **Clear** → `DELETE /api/credentials/{provider}`.
