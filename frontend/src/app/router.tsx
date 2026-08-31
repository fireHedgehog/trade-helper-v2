import { createBrowserRouter, Navigate } from "react-router-dom";

import { AppShell } from "@/app/AppShell";
import { CredentialsPage } from "@/features/credentials/CredentialsPage";
import { DataManagementPage } from "@/features/data-management/DataManagementPage";
import { MacroPage } from "@/features/macro/MacroPage";
import { MultisectionalPage } from "@/features/multisectional/MultisectionalPage";
import { StrategiesPage } from "@/features/strategies/StrategiesPage";
import { TimingPage } from "@/features/timing/TimingPage";
import { TrendPage } from "@/features/trend/TrendPage";

// Menu order follows docs/08-navigation-and-app-shell.md.
export const NAV_ITEMS = [
  { path: "/macro", label: "Macro" },
  { path: "/multisectional", label: "Multisectional" },
  { path: "/trend", label: "Trend" },
  { path: "/timing", label: "Timing" },
  { path: "/strategies", label: "Strategies" },
  { path: "/data-management", label: "Data management" },
  { path: "/credentials", label: "Credentials" },
] as const;

export const router = createBrowserRouter([
  {
    path: "/",
    element: <AppShell />,
    children: [
      { index: true, element: <Navigate to="/macro" replace /> },
      { path: "macro", element: <MacroPage /> },
      { path: "multisectional", element: <MultisectionalPage /> },
      { path: "trend", element: <TrendPage /> },
      { path: "timing", element: <TimingPage /> },
      { path: "timing/:symbol", element: <TimingPage /> },
      { path: "strategies", element: <StrategiesPage /> },
      { path: "data-management", element: <DataManagementPage /> },
      { path: "credentials", element: <CredentialsPage /> },
    ],
  },
]);
