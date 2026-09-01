import { useEffect, useState, type ReactNode } from "react";
import { NavLink, Outlet } from "react-router-dom";
import Box from "@mui/material/Box";
import Divider from "@mui/material/Divider";
import IconButton from "@mui/material/IconButton";
import List from "@mui/material/List";
import ListItemButton from "@mui/material/ListItemButton";
import ListItemIcon from "@mui/material/ListItemIcon";
import ListItemText from "@mui/material/ListItemText";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import AccountBalanceRounded from "@mui/icons-material/AccountBalanceRounded";
import ChevronLeftRounded from "@mui/icons-material/ChevronLeftRounded";
import KeyRounded from "@mui/icons-material/KeyRounded";
import LeaderboardRounded from "@mui/icons-material/LeaderboardRounded";
import MenuRounded from "@mui/icons-material/MenuRounded";
import ScaleRounded from "@mui/icons-material/ScaleRounded";
import ShowChartRounded from "@mui/icons-material/ShowChartRounded";
import StorageRounded from "@mui/icons-material/StorageRounded";
import TrendingUpRounded from "@mui/icons-material/TrendingUpRounded";
import TuneRounded from "@mui/icons-material/TuneRounded";

import { NAV_ITEMS } from "@/app/router";
import { DRAWER_WIDTH } from "@/app/theme";
import { ColorModeToggle } from "@/shared/components/ColorModeToggle";

const SIDEBAR_KEY = "trade-helper.sidebar";
const RAIL_WIDTH = 56;

const NAV_ICON: Record<string, ReactNode> = {
  "/macro": <AccountBalanceRounded fontSize="small" />,
  "/multisectional": <LeaderboardRounded fontSize="small" />,
  "/trend": <TrendingUpRounded fontSize="small" />,
  "/timing": <ShowChartRounded fontSize="small" />,
  "/strategies": <TuneRounded fontSize="small" />,
  "/sizing": <ScaleRounded fontSize="small" />,
  "/data-management": <StorageRounded fontSize="small" />,
  "/credentials": <KeyRounded fontSize="small" />,
};

export function AppShell() {
  const [open, setOpen] = useState(() => {
    try {
      return localStorage.getItem(SIDEBAR_KEY) !== "closed";
    } catch {
      return true;
    }
  });

  useEffect(() => {
    try {
      localStorage.setItem(SIDEBAR_KEY, open ? "open" : "closed");
    } catch {
      /* private mode — ignore */
    }
  }, [open]);

  // Ctrl/⌘ + \  toggles the sidebar (same as the Claude web app).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "\\") {
        e.preventDefault();
        setOpen((o) => !o);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const width = open ? DRAWER_WIDTH : RAIL_WIDTH;

  return (
    <Box sx={{ display: "flex", minHeight: "100vh" }}>
      <Box
        component="nav"
        sx={{
          width,
          flexShrink: 0,
          position: "sticky",
          top: 0,
          alignSelf: "flex-start",
          height: "100vh",
          display: "flex",
          flexDirection: "column",
          overflow: "hidden",
          transition: "width 0.2s ease",
          borderRight: "1px solid",
          borderColor: "divider",
          bgcolor: "background.paper",
        }}
      >
        {/* header */}
        <Box
          sx={{
            px: open ? 2 : 0,
            py: 1.5,
            minHeight: 56,
            display: "flex",
            flexDirection: "column",
            alignItems: open ? "stretch" : "center",
          }}
        >
          <Stack
            direction="row"
            sx={{
              alignItems: "center",
              justifyContent: open ? "space-between" : "center",
              width: "100%",
            }}
          >
            {open && (
              <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
                Trade Helper
              </Typography>
            )}
            <Tooltip title={open ? "Hide sidebar (Ctrl/⌘ + \\)" : "Show sidebar (Ctrl/⌘ + \\)"} arrow>
              <IconButton size="small" onClick={() => setOpen((o) => !o)}>
                {open ? <ChevronLeftRounded fontSize="small" /> : <MenuRounded fontSize="small" />}
              </IconButton>
            </Tooltip>
          </Stack>
          {open && (
            <Typography variant="caption" color="text.secondary" sx={{ mt: 0.25 }}>
              Naive-v1 research. Nothing here is validated.
            </Typography>
          )}
        </Box>

        <Divider />

        {/* nav */}
        <List sx={{ px: open ? 0.75 : 0.5, py: 0.5, flexGrow: 1, overflowY: "auto" }}>
          {NAV_ITEMS.map((item) => (
            <Tooltip key={item.path} title={open ? "" : item.label} placement="right" arrow>
              <ListItemButton
                component={NavLink}
                to={item.path}
                sx={{
                  borderRadius: 1,
                  mb: 0.25,
                  minHeight: 32,
                  px: open ? 1.25 : 0,
                  justifyContent: open ? "flex-start" : "center",
                  "&.active": {
                    bgcolor: "primary.main",
                    color: "primary.contrastText",
                    "& .MuiListItemIcon-root": { color: "inherit" },
                  },
                }}
              >
                <ListItemIcon
                  sx={{ minWidth: 0, mr: open ? 1.25 : 0, justifyContent: "center", color: "inherit" }}
                >
                  {NAV_ICON[item.path]}
                </ListItemIcon>
                {open && (
                  <ListItemText
                    slotProps={{ primary: { sx: { fontSize: 13 } } }}
                    primary={item.label}
                  />
                )}
              </ListItemButton>
            </Tooltip>
          ))}
        </List>

        {/* footer — theme toggle, pinned, both states */}
        <Divider />
        <Box
          sx={{
            px: open ? 2 : 0,
            py: 1,
            display: "flex",
            alignItems: "center",
            justifyContent: open ? "space-between" : "center",
          }}
        >
          {open && (
            <Typography variant="caption" color="text.secondary">
              Theme
            </Typography>
          )}
          <ColorModeToggle />
        </Box>
      </Box>

      <Box component="main" sx={{ flexGrow: 1, minWidth: 0, pl: 1.5, pr: 2, py: 1.5 }}>
        <Outlet />
      </Box>
    </Box>
  );
}
