import Icon from "./Icon";

export default function PageHeader({ eyebrow, title, accent, description, action }) {
  return <header className="ops-heading premium-page-heading cyber-page-heading"><div><span className="eyebrow">{eyebrow}</span><h1>{title} {accent ? <span>{accent}</span> : null}</h1><p>{description}</p></div>{action ? <a className="button button-primary" href={action.href}><Icon name={action.icon || "plus"}/>{action.label}</a> : null}</header>;
}
