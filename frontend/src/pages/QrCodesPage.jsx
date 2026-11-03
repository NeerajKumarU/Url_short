import { useState } from "react";
import Icon from "../components/Icon";
import PageHeader from "../components/PageHeader";
import PageState from "../components/PageState";
import { usePageData } from "../hooks/usePageData";
import { date } from "../utils/format";

function QrCodes({ data }) {
  const [copied, setCopied] = useState("");
  const copy = async (value) => { await navigator.clipboard.writeText(value); setCopied("Link copied"); window.setTimeout(() => setCopied(""), 1800); };
  return <section className="ops-shell"><PageHeader eyebrow={data.workspace_name} title="QR code library" description="Every short link includes a downloadable QR code tied to the same secure redirect and analytics flow." action={{ href: "/links/new/", label: "Create link" }}/><div className="qr-grid premium-qr-grid">{data.links.length ? data.links.map((link) => <article className="glass-card qr-card premium-qr-card" key={link.id}><div className="qr-image-shell"><img src={`/links/${link.id}/qr/`} alt={`QR code for ${link.alias}`}/></div><div className="qr-card-content"><div className="qr-card-meta"><span className={`status-pill ${link.status === "Active" ? "status-approved" : ""}`}>{link.status}</span><span>{date(link.created_at)}</span></div><h2>/{link.alias}</h2><p title={link.destination}>{link.destination}</p>{link.campaign ? <small className="campaign-label"><Icon name="campaign"/>{link.campaign}</small> : null}<div className="button-row"><button className="button button-secondary" type="button" onClick={() => copy(link.public_url)}><Icon name="copy"/>Copy</button><a className="button button-secondary" href={`/links/${link.id}/qr/?download=1`}><Icon name="download"/>Download</a><a className="icon-only-link" href={`/links/${link.id}/edit/`} aria-label={`Edit ${link.alias}`}><Icon name="settings"/></a></div></div></article>) : <div className="glass-card empty-state full-grid"><h3>No QR codes yet</h3><p>Create your first link and its QR code will appear here automatically.</p><a className="button button-primary" href="/links/new/">Create a link</a></div>}</div>{copied ? <div className="notice notice-success react-copy-feedback">{copied}</div> : null}</section>;
}
export default function QrCodesPage() { const state = usePageData("qr-codes"); return <PageState state={state}>{(data) => <QrCodes data={data}/>}</PageState>; }
