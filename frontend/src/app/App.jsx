import { useCallback, useEffect, useState } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { getBootstrap } from "../api/client";
import AppShell from "../components/AppShell";
import { ErrorState, Loading } from "../components/Loading";
import { AppearanceProvider } from "../hooks/useAppearance";
import AnalyticsPage from "../pages/AnalyticsPage";
import AudiencePage from "../pages/AudiencePage";
import CampaignsPage from "../pages/CampaignsPage";
import DashboardPage from "../pages/DashboardPage";
import LegacyPage from "../pages/LegacyPage";
import LinksPage from "../pages/LinksPage";
import QrCodesPage from "../pages/QrCodesPage";
import SettingsPage from "../pages/SettingsPage";
import SecurityPage from "../pages/SecurityPage";

export default function App() {
  const [state, setState] = useState({ loading: true, shell: null, error: null });
  const load = useCallback(() => {
    setState({ loading: true, shell: null, error: null });
    getBootstrap("shell").then((data) => setState({ loading: false, shell: data.shell, error: null })).catch((error) => setState({ loading: false, shell: null, error }));
  }, []);
  useEffect(load, [load]);
  if (state.loading) return <Loading/>;
  if (state.error) return <ErrorState error={state.error} retry={load}/>;
  return <AppearanceProvider><Routes><Route element={<AppShell shell={state.shell}/>}><Route index element={<Navigate to="dashboard" replace/>}/><Route path="dashboard" element={<DashboardPage/>}/><Route path="links" element={<LinksPage/>}/><Route path="analytics" element={<AnalyticsPage/>}/><Route path="audience" element={<AudiencePage/>}/><Route path="campaigns" element={<CampaignsPage/>}/><Route path="qr-codes" element={<QrCodesPage/>}/><Route path="security" element={<SecurityPage/>}/><Route path="settings" element={<SettingsPage/>}/><Route path="*" element={<LegacyPage/>}/></Route></Routes></AppearanceProvider>;
}
