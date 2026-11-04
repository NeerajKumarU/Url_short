import { useEffect, useMemo, useState } from "react";
import Icon from "../components/Icon";
import PageState from "../components/PageState";
import { scanSecurityNow, securityAction, updateSecuritySettings } from "../api/client";
import { usePageData } from "../hooks/usePageData";
import { number, relative } from "../utils/format";

const actionLabels = {
  investigate: "Start investigation",
  resolve: "Resolve incident",
  dismiss: "Mark as safe",
  suspend_1h: "Suspend for 1 hour",
  suspend_24h: "Suspend for 24 hours",
  disable: "Disable indefinitely",
  resume: "Reactivate link",
};

const auditLabels = {
  SECURITY_INCIDENT_CREATED: "Incident detected",
  SECURITY_INCIDENT_ESCALATED: "Incident severity increased",
  SECURITY_INCIDENT_INVESTIGATED: "Investigation started",
  SECURITY_INCIDENT_RESOLVED: "Incident resolved",
  SECURITY_INCIDENT_DISMISSED: "Activity marked safe",
  LINK_TEMPORARILY_SUSPENDED: "Link temporarily suspended",
  LINK_SECURITY_DISABLED: "Link disabled by security review",
  LINK_SECURITY_REACTIVATED: "Link reactivated",
  LINK_SECURITY_SUSPENSION_EXPIRED: "Temporary suspension expired",
  LINK_AUTOMATICALLY_THROTTLED: "Critical traffic automatically throttled",
};

function RiskGauge({ score, compact = false }) {
  const tone = score >= 80 ? "critical" : score >= 60 ? "high" : score >= 30 ? "medium" : "low";
  return <div className={`security-risk-gauge risk-${tone}${compact ? " is-compact" : ""}`} style={{ "--risk": `${score * 3.6}deg` }}><div><strong>{score}</strong><small>/100</small></div></div>;
}

function SummaryCard({ icon, label, value, detail, tone = "" }) {
  return <article className={`glass-card security-summary-card ${tone}`}><span><Icon name={icon}/></span><small>{label}</small><strong>{value}</strong><em>{detail}</em></article>;
}

function ThreatTimeline({ items }) {
  const maximum = Math.max(...items.map((item) => item.total), 1);
  return <article className="glass-card security-panel security-timeline-panel"><header><div><span className="security-panel-icon"><Icon name="pulse"/></span><div><span className="eyebrow">Last 24 hours</span><h2>Suspicious traffic timeline</h2></div></div><div className="security-legend"><span><i className="total"/>Total</span><span><i className="automated"/>Automated</span><span><i className="risk"/>Risk</span></div></header><div className="security-timeline" role="img" aria-label="Total and automated clicks with incident risk over the last 24 hours">{items.map((item, index) => <div className="security-timeline-column" key={item.time}><i className="security-total-bar" style={{ height: `${Math.max(3, item.total / maximum * 100)}%` }}/><i className="security-bot-bar" style={{ height: `${Math.max(0, item.automated / maximum * 100)}%` }}/>{item.risk ? <b style={{ bottom: `${Math.min(92, item.risk)}%` }} title={`Risk ${item.risk}`}/> : null}{index % 4 === 0 ? <small>{item.label}</small> : null}</div>)}</div></article>;
}

function SignalBreakdown({ signals }) {
  return <div className="security-signals">{signals.length ? signals.map((signal) => <div className="security-signal" key={signal.name}><header><span>{signal.label}</span><b>+{signal.score}</b></header><i><em style={{ width: `${signal.score / signal.maximum * 100}%` }}/></i><p>{signal.detail}</p><small>Observed {signal.observed} · trigger {signal.baseline}</small></div>) : <p className="panel-empty">No signal evidence was recorded.</p>}</div>;
}

function IncidentDrawer({ incident, canAdmin, close, requestAction, note, setNote }) {
  if (!incident) return null;
  const linkRestricted = incident.link?.security_disabled || incident.link?.status === "Suspended";
  return <div className="security-drawer-backdrop" role="presentation" onMouseDown={(event) => event.target === event.currentTarget && close()}><aside className="security-drawer" aria-label={`Security incident ${incident.id}`}><header className="security-drawer-header"><div><span className={`security-severity severity-${incident.severity.toLowerCase()}`}>{incident.severity_label}</span><span className="eyebrow">Incident #{incident.id}</span><h2>{incident.threat_label}</h2><p>{incident.link ? `/${incident.link.alias}` : "Deleted link"} · detected {relative(incident.first_detected_at)}</p></div><button className="icon-button" type="button" onClick={close} aria-label="Close incident"><Icon name="close"/></button></header><div className="security-drawer-risk"><RiskGauge score={incident.risk_score}/><div><small>Current risk score</small><strong>{incident.status_label}</strong><p>{incident.explanation}</p></div></div><section><div className="security-section-heading"><h3>Risk score breakdown</h3><span>{incident.signals.length} triggered signals</span></div><SignalBreakdown signals={incident.signals}/></section><section className="security-evidence-grid"><div><span>Observed clicks</span><strong>{number(incident.observed_clicks)}</strong></div><div><span>Normal baseline</span><strong>{incident.baseline_clicks}</strong></div><div><span>Last detected</span><strong>{relative(incident.last_detected_at)}</strong></div><div><span>Investigator</span><strong>{incident.investigated_by || "Unassigned"}</strong></div></section>{canAdmin ? <section className="security-response"><div className="security-section-heading"><h3>Investigation response</h3><span>All actions are audited</span></div><label><span>Administrator note</span><textarea value={note} onChange={(event) => setNote(event.target.value)} placeholder="Add evidence, decision context, or resolution details…" maxLength="2000"/></label><div className="security-action-grid"><button type="button" onClick={() => requestAction("investigate")}><Icon name="search"/>Investigate</button><button type="button" onClick={() => requestAction("dismiss")}><Icon name="approval"/>Mark safe</button><button type="button" onClick={() => requestAction("resolve")}><Icon name="shield"/>Resolve</button>{linkRestricted ? <button type="button" className="action-success" onClick={() => requestAction("resume")}><Icon name="unlock"/>Reactivate</button> : <><button type="button" className="action-warning" onClick={() => requestAction("suspend_1h")}><Icon name="lock"/>Suspend 1h</button><button type="button" className="action-warning" onClick={() => requestAction("suspend_24h")}><Icon name="lock"/>Suspend 24h</button><button type="button" className="action-danger" onClick={() => requestAction("disable")}><Icon name="alert"/>Disable</button></>}</div></section> : <p className="security-readonly-note"><Icon name="lock"/>Administrator access is required to change incident or link status.</p>}</aside></div>;
}

function ConfirmAction({ action, incident, cancel, confirm, busy }) {
  if (!action || !incident) return null;
  const dangerous = ["suspend_1h", "suspend_24h", "disable", "resume"].includes(action);
  return <div className="security-confirm-backdrop"><div className="glass-card security-confirm" role="alertdialog" aria-modal="true"><span className={`security-confirm-icon${dangerous ? " is-warning" : ""}`}><Icon name={dangerous ? "alert" : "shield"}/></span><span className="eyebrow">Confirm security action</span><h2>{actionLabels[action]}</h2><p>This will update incident #{incident.id}{incident.link ? ` for /${incident.link.alias}` : ""}. The action and administrator identity will be recorded in the audit log.</p><div className="button-row"><button className="button button-secondary" type="button" onClick={cancel} disabled={busy}>Cancel</button><button className={`button ${dangerous ? "button-danger" : "button-primary"}`} type="button" onClick={confirm} disabled={busy}>{busy ? "Applying…" : "Confirm action"}</button></div></div></div>;
}

function SecuritySettings({ value, canAdmin, save, busy }) {
  const [settings, setSettings] = useState(value);
  useEffect(() => setSettings(value), [value]);
  const toggle = (key) => setSettings((current) => ({ ...current, [key]: !current[key] }));
  return <article className="glass-card security-panel security-settings"><header><div><span className="security-panel-icon"><Icon name="settings"/></span><div><span className="eyebrow">Workspace policy</span><h2>Security settings</h2></div></div><span className={`live-signal ${settings.monitoring_enabled ? "" : "is-paused"}`}><i/>{settings.monitoring_enabled ? "Monitoring active" : "Monitoring paused"}</span></header><div className="security-settings-grid"><label><span>Monitoring sensitivity</span><select value={settings.sensitivity} onChange={(event) => setSettings({ ...settings, sensitivity: event.target.value })} disabled={!canAdmin}><option value="RELAXED">Relaxed</option><option value="BALANCED">Balanced</option><option value="HIGH">High sensitivity</option></select><small>Controls the minimum score required to create an incident.</small></label><label><span>Alert threshold: {settings.alert_threshold}</span><input type="range" min="20" max="100" step="5" value={settings.alert_threshold} onChange={(event) => setSettings({ ...settings, alert_threshold: Number(event.target.value) })} disabled={!canAdmin}/><small>Email and webhooks trigger at this score.</small></label><div className="security-toggle-list">{[["monitoring_enabled", "Continuous monitoring", "Analyze new click traffic"], ["email_alerts", "Email alerts", "Notify the workspace owner"], ["webhook_alerts", "Webhook alerts", "Send signed SECURITY_INCIDENT events"], ["automatic_throttling", "Critical-risk throttling", "Pause risk 90+ links for 15 minutes"]].map(([key, label, detail]) => <button type="button" className={`security-toggle ${settings[key] ? "is-on" : ""}`} onClick={() => canAdmin && toggle(key)} disabled={!canAdmin} key={key}><i><em/></i><span><b>{label}</b><small>{detail}</small></span></button>)}</div></div>{canAdmin ? <div className="security-settings-actions"><button className="button button-primary" type="button" onClick={() => save(settings)} disabled={busy}>{busy ? "Saving…" : "Save security settings"}</button></div> : null}</article>;
}

function SecurityCenter({ data, reload }) {
  const [selected, setSelected] = useState(null);
  const [note, setNote] = useState("");
  const [confirmAction, setConfirmAction] = useState(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [error, setError] = useState("");
  const [filters, setFilters] = useState({ q: "", severity: "all", status: "all", threat: "all" });

  const incidents = useMemo(() => data.incidents.filter((incident) => {
    const search = filters.q.toLowerCase();
    return (!search || incident.link?.alias.toLowerCase().includes(search) || incident.explanation.toLowerCase().includes(search))
      && (filters.severity === "all" || incident.severity === filters.severity)
      && (filters.status === "all" || incident.status === filters.status)
      && (filters.threat === "all" || incident.threat_type === filters.threat);
  }), [data.incidents, filters]);
  const activeThreats = data.incidents.filter((item) => ["OPEN", "INVESTIGATING"].includes(item.status)).slice(0, 5);
  const totalBots = data.bot_breakdown.reduce((sum, item) => sum + item.value, 0);
  const botColors = ["#35f2d0", "#9b6cff", "#ff9c4a", "#5d8cff"];
  let stop = 0;
  const botGradient = data.bot_breakdown.map((item, index) => { const start = stop; stop += totalBots ? item.value / totalBots * 100 : 0; return `${botColors[index]} ${start}% ${stop}%`; }).join(", ");

  const toast = (message) => { setNotice(message); window.setTimeout(() => setNotice(""), 2600); };
  const applyAction = async () => {
    if (!selected || !confirmAction) return;
    setBusy(true); setError("");
    try {
      const response = await securityAction(selected.id, confirmAction, note);
      setSelected(response.incident);
      toast(`${actionLabels[confirmAction]} completed.`);
      setConfirmAction(null);
      reload();
    } catch (requestError) { setError(requestError.message); }
    finally { setBusy(false); }
  };
  const scan = async () => {
    setBusy(true); setError("");
    try { const response = await scanSecurityNow(); toast(`Scan complete: ${response.created} created, ${response.updated} updated.`); reload(); }
    catch (requestError) { setError(requestError.message); }
    finally { setBusy(false); }
  };
  const saveSettings = async (settings) => {
    setBusy(true); setError("");
    try { await updateSecuritySettings(settings); toast("Security settings saved."); reload(); }
    catch (requestError) { setError(requestError.message); }
    finally { setBusy(false); }
  };

  return <section className="ops-shell shell security-center"><header className="security-page-heading"><div><span className="eyebrow"><Icon name="shield"/>OrbitShield · {data.workspace_name}</span><h1>Intelligent Click <span>Monitoring</span></h1><p>Explainable, privacy-aware detection for traffic spikes, automation, repeated visitors, abnormal velocity, geographic shifts, and unusual browser signatures.</p></div>{data.can_admin ? <button className="button button-primary" type="button" onClick={scan} disabled={busy}><Icon name="play"/>{busy ? "Scanning…" : "Run security scan"}</button> : null}</header>{error ? <div className="notice notice-error security-notice"><span>{error}</span><button type="button" onClick={() => setError("")}>×</button></div> : null}<div className="security-overview-grid"><article className="glass-card security-primary-risk"><RiskGauge score={data.summary.risk_score}/><div><span className="eyebrow">Workspace risk</span><h2>{data.summary.risk_score >= 80 ? "Critical attention required" : data.summary.risk_score >= 60 ? "High-risk activity detected" : data.summary.risk_score >= 30 ? "Elevated monitoring" : "Security posture normal"}</h2><p>Highest unresolved incident score across {number(data.summary.monitored_links)} monitored links.</p></div></article><SummaryCard icon="alert" label="Open incidents" value={number(data.summary.open_incidents)} detail="Awaiting review"/><SummaryCard icon="shield" label="Critical alerts" value={number(data.summary.critical_incidents)} detail="Risk score 80+" tone="critical"/><SummaryCard icon="bot" label="Suspicious clicks" value={number(data.summary.suspicious_clicks)} detail={`${data.summary.bot_percentage}% automated`} tone="warning"/></div><div className="security-main-grid"><ThreatTimeline items={data.timeline}/><article className="glass-card security-panel live-threat-panel"><header><div><span className="security-panel-icon"><Icon name="pulse"/></span><div><span className="eyebrow">Live monitor</span><h2>Active threats</h2></div></div><span className="live-signal"><i/>Continuous</span></header><div className="live-threat-list">{activeThreats.length ? activeThreats.map((incident) => <button type="button" onClick={() => { setSelected(incident); setNote(incident.resolution_note || ""); }} key={incident.id}><span className={`threat-dot severity-${incident.severity.toLowerCase()}`}/><span><b>{incident.threat_label}</b><small>{incident.link ? `/${incident.link.alias}` : "Deleted link"} · {relative(incident.last_detected_at)}</small></span><strong>{incident.risk_score}</strong></button>) : <p className="panel-empty">No active security incidents.</p>}</div></article></div><div className="security-intelligence-grid"><article className="glass-card security-panel"><header><div><span className="security-panel-icon"><Icon name="link"/></span><div><span className="eyebrow">Exposure ranking</span><h2>Most targeted links</h2></div></div></header><div className="targeted-link-list">{data.targeted_links.length ? data.targeted_links.map((link) => <div key={link.id}><span><b>/{link.alias}</b><small>{link.incidents} incident{link.incidents === 1 ? "" : "s"} · {link.status}</small></span><RiskGauge score={link.risk_score} compact/></div>) : <p className="panel-empty">No targeted links recorded.</p>}</div></article><article className="glass-card security-panel"><header><div><span className="security-panel-icon"><Icon name="bot"/></span><div><span className="eyebrow">Classification</span><h2>Bot traffic analysis</h2></div></div></header><div className="bot-analysis"><div className="bot-donut" style={{ background: totalBots ? `conic-gradient(${botGradient})` : "var(--surface-strong)" }}><span><b>{number(totalBots)}</b><small>clicks</small></span></div><div>{data.bot_breakdown.map((item, index) => <p key={item.key}><i style={{ background: botColors[index] }}/><span>{item.label}</span><b>{number(item.value)}</b></p>)}</div></div></article><article className="glass-card security-panel"><header><div><span className="security-panel-icon"><Icon name="location"/></span><div><span className="eyebrow">Geographic signals</span><h2>Traffic locations</h2></div></div></header><div className="security-country-list">{data.countries.length ? data.countries.map((item) => <div key={item.country}><span>{item.country}</span><i><em style={{ width: `${item.value / Math.max(data.countries[0].value, 1) * 100}%` }}/></i><b>{number(item.value)}</b></div>) : <p className="panel-empty">Geographic data appears when trusted edge headers are enabled.</p>}</div></article></div><article className="glass-card security-panel incident-register"><header><div><span className="security-panel-icon"><Icon name="shield"/></span><div><span className="eyebrow">Investigation queue</span><h2>Security incidents</h2></div></div><span className="count-chip">{incidents.length} shown</span></header><div className="security-filter-bar"><label><Icon name="search"/><input type="search" placeholder="Search alias or evidence" value={filters.q} onChange={(event) => setFilters({ ...filters, q: event.target.value })}/></label><select value={filters.severity} onChange={(event) => setFilters({ ...filters, severity: event.target.value })}><option value="all">All severities</option><option value="CRITICAL">Critical</option><option value="HIGH">High</option><option value="MEDIUM">Medium</option><option value="LOW">Low</option></select><select value={filters.status} onChange={(event) => setFilters({ ...filters, status: event.target.value })}><option value="all">All statuses</option><option value="OPEN">Open</option><option value="INVESTIGATING">Investigating</option><option value="RESOLVED">Resolved</option><option value="DISMISSED">False positive</option></select><select value={filters.threat} onChange={(event) => setFilters({ ...filters, threat: event.target.value })}><option value="all">All threats</option><option value="TRAFFIC_SPIKE">Traffic spike</option><option value="REPEATED_IP">Repeated visitor</option><option value="BOT_ACTIVITY">Bot activity</option><option value="GEO_ANOMALY">Geographic anomaly</option><option value="USER_AGENT_ANOMALY">User-agent anomaly</option><option value="CLICK_VELOCITY">Click velocity</option><option value="COMPOSITE">Multiple signals</option></select></div><div className="table-wrap"><table className="ops-table security-table"><thead><tr><th>Risk</th><th>Incident</th><th>Affected link</th><th>Signals</th><th>Status</th><th>Detected</th><th></th></tr></thead><tbody>{incidents.length ? incidents.map((incident) => <tr key={incident.id}><td><RiskGauge score={incident.risk_score} compact/></td><td><strong>{incident.threat_label}</strong><small>#{incident.id} · {incident.severity_label}</small></td><td>{incident.link ? <><b>/{incident.link.alias}</b><small>{incident.link.status}</small></> : "Deleted link"}</td><td><div className="incident-signal-chips">{incident.signals.slice(0, 3).map((signal) => <span key={signal.name}>{signal.label}</span>)}{incident.signals.length > 3 ? <span>+{incident.signals.length - 3}</span> : null}</div></td><td><span className={`status-pill incident-status-${incident.status.toLowerCase()}`}>{incident.status_label}</span></td><td>{relative(incident.last_detected_at)}</td><td><button className="text-action" type="button" onClick={() => { setSelected(incident); setNote(incident.resolution_note || ""); }}>Investigate →</button></td></tr>) : <tr><td colSpan="7"><div className="empty-state"><Icon name="shield"/><h3>No incidents match these filters</h3><p>Adjust the filters or run a new security scan.</p></div></td></tr>}</tbody></table></div></article><div className="security-bottom-grid"><SecuritySettings value={data.settings} canAdmin={data.can_admin} save={saveSettings} busy={busy}/><article className="glass-card security-panel security-activity"><header><div><span className="security-panel-icon"><Icon name="audit"/></span><div><span className="eyebrow">Audited evidence</span><h2>Security activity</h2></div></div></header><div>{data.activity.length ? data.activity.map((item) => <p key={item.id}><i/><span><b>{auditLabels[item.action] || item.action}</b><small>{item.actor} · {relative(item.created_at)}</small></span></p>) : <p className="panel-empty">Security actions will appear here.</p>}</div></article></div><IncidentDrawer incident={selected} canAdmin={data.can_admin} close={() => { setSelected(null); setConfirmAction(null); }} requestAction={setConfirmAction} note={note} setNote={setNote}/><ConfirmAction action={confirmAction} incident={selected} cancel={() => setConfirmAction(null)} confirm={applyAction} busy={busy}/>{notice ? <div className="notice notice-success react-copy-feedback"><Icon name="approval"/>{notice}</div> : null}</section>;
}

export default function SecurityPage() {
  const state = usePageData("security");
  return <PageState state={state}>{(data) => <SecurityCenter data={data} reload={state.reload}/>}</PageState>;
}
