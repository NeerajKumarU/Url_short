import { NavLink } from "react-router-dom";
import Icon from "./Icon";

const groups = [
  ["Overview", [{ to: "/dashboard", label: "Dashboard", icon: "dashboard" }]],
  ["Links", [
    { to: "/links", label: "Links", icon: "link" },
    { href: "/links/new/", label: "Create link", icon: "plus", permission: "can_edit" },
    { to: "/qr-codes", label: "QR codes", icon: "qr" },
  ]],
  ["Marketing", [
    { to: "/analytics", label: "Analytics", icon: "chart" },
    { to: "/campaigns", label: "Campaigns", icon: "campaign" },
    { to: "/audience", label: "Audience", icon: "users" },
    { href: "/tools/utm-builder/", label: "UTM builder", icon: "tool" },
  ]],
  ["Workspace", [
    { href: "/workspaces/", label: "Workspaces", icon: "workspace" },
    { href: "/domains/", label: "Domains", icon: "globe" },
    { href: "/analytics/anomalies/", label: "Anomalies", icon: "alert", count: "anomaly_count" },
    { href: "/approvals/", label: "Approvals", icon: "approval", permission: "can_admin", count: "approval_count" },
    { href: "/audit/", label: "Audit log", icon: "audit", permission: "can_admin" },
  ]],
  ["Integrations", [
    { href: "/integrations/api-keys/", label: "API credentials", icon: "key", permission: "can_admin" },
    { href: "/integrations/webhooks/", label: "Webhooks", icon: "webhook", permission: "can_admin" },
  ]],
];

function SidebarItem({ item, shell, close }) {
  if (item.permission && !shell.permissions[item.permission]) return null;
  const content = <><Icon name={item.icon} className="nav-icon"/><span className="nav-label">{item.label}</span>{item.count && shell[item.count] > 0 ? <span className="nav-count">{shell[item.count]}</span> : null}</>;
  return item.to
    ? <NavLink to={item.to} onClick={close} className={({ isActive }) => `sidebar-link dashboard-core-link${isActive ? " is-active" : ""}`}>{content}</NavLink>
    : <a className="sidebar-link" href={item.href}>{content}</a>;
}

export default function Sidebar({ shell, open, close }) {
  const initial = shell.user.username.slice(0, 1).toUpperCase();
  return <>
    <aside className={`app-sidebar${open ? " is-open" : ""}`} id="app-sidebar" aria-label="Application navigation">
      <div className="sidebar-brand-row">
        <NavLink className="brand" to="/dashboard" aria-label="OrbitLink dashboard"><span className="brand-mark"><Icon name="link"/></span><span className="brand-copy"><b>OrbitLink</b><small>Link intelligence</small></span></NavLink>
        <button className="sidebar-close" type="button" aria-label="Close navigation" onClick={close}><Icon name="close"/></button>
      </div>
      <nav className="sidebar-nav">
        {groups.map(([label, items]) => <div className="nav-section" key={label}><span className="nav-section-label">{label}</span>{items.map((item) => <SidebarItem key={item.label} item={item} shell={shell} close={close}/>)}</div>)}
        {shell.permissions.is_platform_admin ? <><div className="nav-divider"/><div className="nav-section admin-navigation"><span className="nav-section-label">Administration</span><a className="sidebar-link" href="/admin-dashboard/"><Icon name="workspace" className="nav-icon"/><span className="nav-label">Platform overview</span><span className="admin-chip">Admin</span></a><a className="sidebar-link" href="/admin-dashboard/reports/"><Icon name="alert" className="nav-icon"/><span className="nav-label">Abuse reports</span></a><a className="sidebar-link" href="/admin-dashboard/system-health/"><Icon name="chart" className="nav-icon"/><span className="nav-label">System health</span></a></div></> : null}
        <div className="nav-section account-navigation"><span className="nav-section-label">Account</span><NavLink to="/settings" className={({ isActive }) => `sidebar-link dashboard-core-link${isActive ? " is-active" : ""}`}><Icon name="settings" className="nav-icon"/><span className="nav-label">Settings</span></NavLink><form method="post" action="/logout/"><input type="hidden" name="csrfmiddlewaretoken" value={shell.csrf_token}/><button className="sidebar-link sidebar-logout" type="submit"><Icon name="logout" className="nav-icon"/><span className="nav-label">Log out</span></button></form></div>
      </nav>
      <div className="sidebar-workspace"><span className="workspace-avatar">{initial}</span><span className="workspace-copy"><b>{shell.workspace.name}</b><small>{shell.membership.role_label}</small></span><span className="online-dot"><span className="sr-only">Online</span></span></div>
    </aside>
    <button className={`sidebar-backdrop react-mobile-backdrop${open ? " is-open" : ""}`} type="button" aria-label="Close navigation" onClick={close}/>
  </>;
}
