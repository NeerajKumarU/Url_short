import { useEffect } from "react";

export default function CyberUniverse({ route }) {
  useEffect(() => {
    const existing = document.querySelector('script[data-react-cyber-scene]');
    if (existing) return undefined;
    const script = document.createElement("script");
    script.src = "/static/js/cyber-scene.js?v=20261103-1";
    script.defer = true;
    script.dataset.reactCyberScene = "true";
    document.body.appendChild(script);
    return undefined;
  }, []);

  return <div className="cyber-universe" aria-hidden="true"><canvas id="cyber-scene" data-route={route}/><div className="cyber-aurora"/><div className="cyber-grid"/><div className="cyber-vignette"/></div>;
}
