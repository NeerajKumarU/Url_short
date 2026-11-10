import { useEffect, useRef, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import Icon from "./Icon";
import { useAppearance } from "../hooks/useAppearance";

const titles = { dashboard: "Dashboard", links: "My links", analytics: "Analytics", audience: "Audience", campaigns: "Campaigns", "qr-codes": "QR codes", security: "Security Center", settings: "Settings" };

function ThemeToggle() {
  const { effectiveTheme, setTheme } = useAppearance();
  return <button className="topbar-icon react-topbar-button" type="button" title="Toggle theme" aria-label={`Use ${effectiveTheme === "dark" ? "light" : "dark"} theme`} onClick={() => setTheme(effectiveTheme === "dark" ? "light" : "dark")}>{effectiveTheme === "dark" ? "☀" : "☾"}</button>;
}

export default function Topbar({ shell, toggleSidebar }) {
  const location = useLocation();
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const searchRef = useRef(null);
  const segment = location.pathname.split("/").filter(Boolean)[0] || "dashboard";

  useEffect(() => {
    const handler = (event) => {
      if (event.key === "/" && !/INPUT|TEXTAREA|SELECT/.test(document.activeElement?.tagName)) { event.preventDefault(); searchRef.current?.focus(); }
    };
    document.addEventListener("keydown", handler);
    return () => document.removeEventListener("keydown", handler);
  }, []);

  const submit = (event) => {
    event.preventDefault();
    navigate(`/links?q=${encodeURIComponent(query)}`);
  };
  const initial = shell.user.username.slice(0, 1).toUpperCase();

  return <header className="app-topbar">
    <div className="topbar-title-group"><button className="sidebar-toggle" type="button" aria-controls="app-sidebar" aria-label="Toggle navigation" onClick={toggleSidebar}><Icon name="panel"/></button><div className="topbar-page-copy"><span className="topbar-kicker">{shell.workspace.name}</span><strong>{titles[segment] || "OrbitLink"}</strong></div></div>
    <form className="global-search" role="search" onSubmit={submit}><Icon name="search"/><label className="sr-only" htmlFor="react-global-search">Search links</label><input ref={searchRef} id="react-global-search" type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Search links, destinations, campaigns…" autoComplete="off"/><kbd>/</kbd></form>
    <div className="topbar-actions"><ThemeToggle/><details className="topbar-menu notification-menu"><summary className="topbar-icon" aria-label={`${shell.notification_count} notifications`}><Icon name="bell"/>{shell.notification_count ? <span className="notification-dot">{shell.notification_count}</span> : null}</summary><div className="topbar-popover"><div className="popover-heading"><div><span className="eyebrow">Workspace signals</span><h2>Notifications</h2></div></div><a className="notification-item" href="/react/security"><span className="notification-icon"><Icon name="shield"/></span><span><b>OrbitShield incidents</b><small>{shell.security_count ? `${shell.security_count} high-risk incidents` : "No high-risk incidents"}</small></span></a><a className="notification-item" href="/analytics/anomalies/"><span className="notification-icon"><Icon name="alert"/></span><span><b>Analytics anomalies</b><small>{shell.anomaly_count ? `${shell.anomaly_count} unresolved signals` : "No unresolved signals"}</small></span></a>{shell.permissions.can_admin ? <a className="notification-item" href="/approvals/"><span className="notification-icon"><Icon name="approval"/></span><span><b>Approval queue</b><small>{shell.approval_count ? `${shell.approval_count} requests waiting` : "Nothing waiting for review"}</small></span></a> : null}</div></details>
      <details className="topbar-menu profile-menu"><summary className="topbar-profile" aria-label="Open profile menu"><span className="profile-avatar">{initial}</span><span className="profile-copy"><b>{shell.user.username}</b><small>{shell.membership.role_label}</small></span></summary><div className="topbar-popover profile-popover"><div className="profile-popover-header"><span className="profile-avatar profile-avatar-large">{initial}</span><span><b>{shell.user.username}</b><small>{shell.user.email || "No email provided"}</small></span></div><a href="/settings/"><Icon name="settings"/>Current settings</a><a href="/workspaces/"><Icon name="workspace"/>Switch workspace</a><form method="post" action="/logout/"><input type="hidden" name="csrfmiddlewaretoken" value={shell.csrf_token}/><button type="submit"><Icon name="logout"/>Log out</button></form></div></details>
    </div>
  </header>;
}
