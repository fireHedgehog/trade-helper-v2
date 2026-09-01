import { createTheme } from "@mui/material/styles";

// Light + dark, driven by CSS variables. The active scheme follows the OS by
// default and can be overridden by the toggle in the app bar (see AppShell).
export const theme = createTheme({
  cssVariables: { colorSchemeSelector: "class" },
  colorSchemes: {
    light: {
      palette: {
        primary: { main: "#2f6fed" },
        background: { default: "#f7f7f8", paper: "#ffffff" },
      },
    },
    dark: {
      palette: {
        primary: { main: "#5b8def" },
        background: { default: "#0f1115", paper: "#161a20" },
      },
    },
  },
  shape: { borderRadius: 8 },
  typography: {
    fontSize: 13,
    fontFamily:
      '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif',
  },
  components: {
    MuiButton: { defaultProps: { disableElevation: true } },
    MuiPaper: { defaultProps: { variant: "outlined" } },

    // Every genuinely interactive element gets the pointer cursor — MUI covers
    // most, this catches the rest (clickable chips, the label+control combo,
    // hover table rows, the Select trigger, custom role="button" boxes).
    MuiCssBaseline: {
      styleOverrides: {
        [[
          "a[href]",
          "summary",
          "[role='button']",
          "[role='tab']",
          "[role='option']",
          ".MuiButtonBase-root",
          ".MuiChip-clickable",
          ".MuiFormControlLabel-root",
          ".MuiTableRow-hover",
          ".MuiSelect-select",
          ".MuiAccordionSummary-root",
        ].join(",")]: { cursor: "pointer" },
        [[
          ".MuiButtonBase-root.Mui-disabled",
          ".MuiFormControlLabel-root.Mui-disabled",
          ".MuiAccordionSummary-root.Mui-disabled",
        ].join(",")]: { cursor: "default" },
      },
    },

    // --- density pass ------------------------------------------------------
    // Excel-tight tables / chips / notices. Spacing + type only — no colour,
    // palette, or brand change. Page-level padding (Paper `p`, section gaps,
    // h5 titles) is still per-page.
    MuiTable: { defaultProps: { size: "small" } },
    MuiTableCell: {
      styleOverrides: {
        root: { padding: "3px 10px", fontSize: 13, lineHeight: 1.42 },
        sizeSmall: { padding: "2px 8px" },
        head: { fontWeight: 700, lineHeight: 1.3, whiteSpace: "nowrap" },
      },
    },
    MuiChip: {
      styleOverrides: {
        sizeSmall: {
          height: 19,
          fontSize: 11,
          "& .MuiChip-label": { paddingLeft: 6, paddingRight: 6 },
        },
      },
    },
    MuiAlert: {
      styleOverrides: {
        root: { paddingTop: 4, paddingBottom: 4, fontSize: 13 },
        icon: { paddingTop: 6, paddingBottom: 6 },
        message: { paddingTop: 4, paddingBottom: 4 },
      },
    },
    MuiToggleButton: {
      styleOverrides: { sizeSmall: { padding: "3px 10px", fontSize: 12, lineHeight: 1.3 } },
    },
    MuiListItemButton: { defaultProps: { dense: true } },
  },
});

export const DRAWER_WIDTH = 232;

// Canvas-safe color pairs for the TradingView chart (it cannot read CSS vars).
export const CHART_COLORS = {
  light: {
    background: "#ffffff",
    text: "#1c1c1e",
    grid: "#f0f0f2",
    border: "#e2e2e5",
  },
  dark: {
    background: "#161a20",
    text: "#c7ccd4",
    grid: "#232833",
    border: "#2f3742",
  },
} as const;
