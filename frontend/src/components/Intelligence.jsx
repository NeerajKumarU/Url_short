import Icon from "./Icon";
import { number } from "../utils/format";

export function StatCard({ icon, label, value, detail }) {
  return <article className="glass-card cyber-stat"><span><Icon name={icon}/></span><small>{label}</small><strong>{number(value)}</strong><em>{detail}</em></article>;
}

export function Breakdown({ title, subtitle, items = [] }) {
  return <article className="glass-card cyber-breakdown"><header><h2>{title}</h2><span>{subtitle}</span></header>{items.length ? items.map((item, index) => <div key={`${item.label}-${index}`}><span>{item.label}</span><i><em style={{ width: `${item.percent}%` }}/></i><b>{number(item.value)}</b></div>) : <p className="panel-empty">No recorded data yet.</p>}</article>;
}
