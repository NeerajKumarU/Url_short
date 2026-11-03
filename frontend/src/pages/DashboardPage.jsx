import { useEffect } from "react";
import Icon from "../components/Icon";
import PageState from "../components/PageState";
import { usePageData } from "../hooks/usePageData";
import { number, relative } from "../utils/format";

function Growth({ value }) {
  const negative = Number(value) < 0;
  return <em className={negative ? "negative" : ""}>{negative ? "↘ " : "↗ +"}{value}%</em>;
}

function LineChart({ items }) {
  const values = items.map((item) => Number(item.value) || 0);
  const max = Math.max(...values, 1);
  const left = 22, right = 738, bottom = 214, top = 18;
  const step = (right - left) / Math.max(values.length - 1, 1);
  const points = values.map((value, index) => [left + step * index, bottom - (value / max) * (bottom - top)]);
  const polyline = points.map((point) => point.join(",")).join(" ");
  const area = `M ${left} ${bottom} L ${points.map((point) => point.join(" ")).join(" L ")} L ${right} ${bottom} Z`;
  return <div className="traffic-chart-shell"><svg className="react-chart-svg" viewBox="0 0 760 245" preserveAspectRatio="none" aria-label="Click activity for the last seven days"><defs><linearGradient id="react-chart-line" x1="0" x2="1"><stop stopColor="#8b5cf6"/><stop offset=".5" stopColor="#6198ff"/><stop offset="1" stopColor="#22d3ee"/></linearGradient><linearGradient id="react-chart-area" x1="0" x2="0" y1="0" y2="1"><stop stopColor="#3b82f6" stopOpacity=".55"/><stop offset="1" stopColor="#8b5cf6" stopOpacity=".05"/></linearGradient></defs><path className="command-grid-lines" d="M15 20H745M15 78H745M15 136H745M15 194H745M120 10V218M225 10V218M330 10V218M435 10V218M540 10V218M645 10V218"/><path className="chart-area" d={area}/><polyline className="chart-line" points={polyline}/>{points.map(([cx, cy], index) => <circle key={index} cx={cx} cy={cy} r="5"/>)}</svg><div className="command-chart-labels">{items.map((item) => <span key={item.date}><b>{number(item.value)}</b><small>{item.label}</small></span>)}</div></div>;
}

function Dashboard({ data }) {
  useEffect(() => {
    const timer = window.setInterval(() => fetch("/analytics/realtime/", { headers: { Accept: "application/json" }, credentials: "same-origin" }), 30000);
    return () => window.clearInterval(timer);
  }, []);
  const metrics = [
    ["orb-total-links", "link", "Total Links", data.total_links, data.growth.links],
    ["orb-total-clicks", "chart", "Total Clicks", data.total_clicks, data.growth.clicks],
    ["orb-visitors", "users", "Unique Visitors", data.unique_visitors, data.growth.visitors],
    ["orb-conversions", "approval", "Conversions", data.total_conversions, data.growth.conversions],
  ];
  return <div className="signal-command shell"><header className="command-heading"><div><h1>Signal Command <span>Center</span></h1><p>Real-time link performance and traffic intelligence for your {data.workspace_name} workspace.</p></div><a className="button command-create" href="/links/new/"><Icon name="link"/>Create link</a></header><section className="orb-command-stage" aria-label="Workspace performance overview"><div className="command-stars"/>{metrics.map(([klass, icon, label, value, growth]) => <article className={`orb-metric-card ${klass}`} key={label}><span className="orb-metric-icon"><Icon name={icon}/></span><div><small>{label}</small><strong>{number(value)}</strong><Growth value={growth}/></div><i className="metric-connector"/></article>)}<div className="signal-globe" data-hologram-anchor aria-hidden="true"><div className="globe-pedestal"><i/><i/><i/></div></div></section>
    <section className="command-analytics-grid"><article className="command-panel traffic-intelligence"><header><div><span className="panel-title-icon"><Icon name="chart"/></span><h2>Traffic Intelligence</h2></div><nav aria-label="Analytics period"><span>24H</span><span className="is-active">7D</span><span>30D</span><span>90D</span></nav></header><LineChart items={data.timeline}/></article><div className="command-side-panels"><article className="command-panel top-links-panel"><header><div><span className="panel-title-icon"><Icon name="link"/></span><h2>Top Links</h2></div><a href="/react/links">View all</a></header><div className="command-top-links"><div className="top-links-labels"><span>Link</span><span>Clicks</span><span>Conversions</span><span/></div>{data.top_links.length ? data.top_links.map((link) => <a href={`/links/${link.id}/edit/`} key={link.id}><span>/{link.alias}</span><b>{number(link.clicks)}</b><b>{number(link.conversions)}</b><i><em style={{ width: `${link.share}%` }}/></i></a>) : <div className="panel-empty">No link activity yet.</div>}</div></article><article className="command-panel live-activity-panel"><header><div><span className="panel-title-icon"><Icon name="chart"/></span><h2>Live Activity</h2><i className="activity-live-dot"><span className="sr-only">Live</span></i></div></header><div className="command-live-list">{data.recent_clicks.length ? data.recent_clicks.map((click) => <a href={`/links/${click.link_id}/edit/`} key={click.id}><i/><span>Click on <b>/{click.alias}</b><small>{click.browser} · {click.device}</small></span><time>{relative(click.clicked_at)}</time><em>{click.country || "—"}</em></a>) : <div className="panel-empty">Waiting for the first click event.</div>}</div></article></div></section>
  </div>;
}

export default function DashboardPage() {
  const state = usePageData("dashboard");
  return <PageState state={state}>{(data) => <Dashboard data={data}/>}</PageState>;
}
