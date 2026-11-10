import { useEffect, useState } from "react";
import { Outlet, useLocation } from "react-router-dom";
import Sidebar from "./Sidebar";
import Topbar from "./Topbar";
import CyberUniverse from "./CyberUniverse";

export default function AppShell({ shell }) {
  const [collapsed, setCollapsed] = useState(() => { try { return localStorage.getItem("sidebar-collapsed") === "true"; } catch (_) { return false; } });
  const [mobileOpen, setMobileOpen] = useState(false);
  const location = useLocation();
  useEffect(() => setMobileOpen(false), [location.pathname]);
  useEffect(() => { try { localStorage.setItem("sidebar-collapsed", String(collapsed)); } catch (_) { /* no-op */ } }, [collapsed]);

  const toggle = () => window.matchMedia("(max-width: 900px)").matches ? setMobileOpen((value) => !value) : setCollapsed((value) => !value);
  return <>
    <a className="skip-link" href="#main-content">Skip to content</a>
    <CyberUniverse route={location.pathname}/>
    <div className={`app-layout${collapsed ? " sidebar-collapsed" : ""}${mobileOpen ? " sidebar-open" : ""}`}>
      <Sidebar shell={shell} open={mobileOpen} close={() => setMobileOpen(false)}/>
      <div className="app-column"><Topbar shell={shell} toggleSidebar={toggle}/><main id="main-content" className="app-main"><Outlet/></main></div>
    </div>
  </>;
}
