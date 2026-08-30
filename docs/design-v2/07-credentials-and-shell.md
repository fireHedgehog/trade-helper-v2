# Credentials page & app shell

## Credentials — `/credentials`, `features/credentials/`

Configure and verify provider API keys. The page is **data-driven** from a
provider registry, so a new provider appears automatically.

### Provider registry (`app/providers/`)

`base.py` defines `ProviderSpec(key, label, credential_name, fields=[FieldSpec…],
verify_fn)`; each provider module calls `register(...)`; `loader.py` imports
them all so registration runs.

| `key` | `credential_name` (keychain service) | fields | verify |
| --- | --- | --- | --- |
| `alpaca` | `trade-helper/alpaca` | `api_key_id` (`ALPACA_API_KEY_ID`), `api_secret_key` (`ALPACA_API_SECRET_KEY`) | read the paper account |
| `fred` | `trade-helper/fred` | `api_key` (`FRED_API_KEY`) | a metadata call |
| `openai` | `trade-helper/openai` | `api_key` (`OPENAI_API_KEY`) | `GET /v1/models` |

### Secret handling — the hard rule

A raw secret value is **never** written to the DB, returned by an API, logged,
or bundled into the frontend. Flow:

1. `PUT /api/credentials/{key}` with the field value(s) → `secrets/store.py`
   writes them to the **OS keychain** via `keyring`, and `credentials` stores
   only config + verification metadata (`configured`, `last_verified_at`,
   `verification_status`).
2. At fetch time, `providers/secret_resolver.resolve_provider_secrets(key)`
   returns `{field: value}` from the keychain, falling back to the field's
   env var. Raises `MissingCredential` if a required field is absent.
3. `POST /api/credentials/{key}/verify` resolves the secret and calls the
   provider's `verify_fn` against the real API; the result updates
   `verification_status` only.

### API

`GET /api/credentials` (list of statuses) · `GET /api/credentials/{key}` ·
`PUT /api/credentials/{key}` · `DELETE /api/credentials/{key}` ·
`POST /api/credentials/{key}/verify`.

## App shell — `app/{AppShell,router,theme}.tsx`

- **Layout:** a permanent left `Drawer` (`DRAWER_WIDTH = 232`) listing
  `NAV_ITEMS` (Macro · Multisectional · Trend · Timing · Data management ·
  Credentials), a top bar with a `ColorModeToggle`, and the routed page. No
  page-width cap.
- **Routing** (`react-router` `createBrowserRouter`): `/` → redirect
  `/macro`; the six page routes; `timing/:symbol` in addition to `timing`.
- **Theme** (`theme.ts`): MUI v9, `cssVariables` with a `class` color-scheme
  selector, light + dark palettes, `MuiPaper` defaults to `variant="outlined"`,
  13px base font. `CHART_COLORS` (a light/dark pair) is passed to
  `lightweight-charts`, which can't read CSS variables.
- **MUI v9 note:** system props were removed from `Box`/`Stack`/`Typography`
  — use `sx={{ … }}`, not `alignItems=`/`fontWeight=` props; `slotProps` not
  `componentsProps`.
