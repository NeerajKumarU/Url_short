export function Loading() {
  return <div className="react-loading-screen"><div><span className="react-loader"/><p>Synchronizing workspace intelligence…</p></div></div>;
}

export function ErrorState({ error, retry }) {
  return <div className="react-loading-screen"><article className="glass-card react-error"><span className="eyebrow">Connection interrupted</span><h1>Unable to load OrbitLink</h1><p>{error?.message || "The workspace response could not be loaded."}</p><div className="button-row"><button className="button button-primary" type="button" onClick={retry}>Try again</button><a className="button button-secondary" href="/dashboard/">Use current interface</a></div></article></div>;
}
