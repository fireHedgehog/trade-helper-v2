import { NavLink, Outlet } from "react-router-dom";
import Box from "@mui/material/Box";
import Drawer from "@mui/material/Drawer";
import List from "@mui/material/List";
import ListItemButton from "@mui/material/ListItemButton";
import ListItemText from "@mui/material/ListItemText";
import Stack from "@mui/material/Stack";
import Toolbar from "@mui/material/Toolbar";
import Typography from "@mui/material/Typography";

import { NAV_ITEMS } from "@/app/router";
import { DRAWER_WIDTH } from "@/app/theme";
import { ColorModeToggle } from "@/shared/components/ColorModeToggle";

export function AppShell() {
  return (
    <Box sx={{ display: "flex", minHeight: "100vh" }}>
      <Drawer
        variant="permanent"
        sx={{
          width: DRAWER_WIDTH,
          flexShrink: 0,
          [`& .MuiDrawer-paper`]: { width: DRAWER_WIDTH, boxSizing: "border-box" },
        }}
      >
        <Toolbar sx={{ flexDirection: "column", alignItems: "flex-start", py: 2 }}>
          <Stack
            direction="row"
            spacing={1}
            sx={{ alignItems: "center", justifyContent: "space-between", width: "100%" }}
          >
            <Typography variant="subtitle1" sx={{ fontWeight: 700 }}>
              Trade Helper
            </Typography>
            <ColorModeToggle />
          </Stack>
          <Typography variant="caption" color="text.secondary">
            Naive-v1 research. Nothing here is validated.
          </Typography>
        </Toolbar>
        <List sx={{ px: 1 }}>
          {NAV_ITEMS.map((item) => (
            <ListItemButton
              key={item.path}
              component={NavLink}
              to={item.path}
              sx={{
                borderRadius: 1,
                mb: 0.5,
                "&.active": {
                  bgcolor: "primary.main",
                  color: "primary.contrastText",
                },
              }}
            >
              <ListItemText
                slotProps={{ primary: { sx: { fontSize: 14 } } }}
                primary={item.label}
              />
            </ListItemButton>
          ))}
        </List>
      </Drawer>

      <Box component="main" sx={{ flexGrow: 1, minWidth: 0, p: 4 }}>
        <Outlet />
      </Box>
    </Box>
  );
}
