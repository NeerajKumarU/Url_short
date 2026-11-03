import { useCallback, useEffect, useState } from "react";
import { useLocation } from "react-router-dom";
import { getBootstrap } from "../api/client";

export function usePageData(page) {
  const location = useLocation();
  const [state, setState] = useState({ loading: true, data: null, error: null });
  const load = useCallback(() => {
    let alive = true;
    setState((current) => ({ ...current, loading: true, error: null }));
    getBootstrap(page, location.search).then((data) => alive && setState({ loading: false, data: data.page, error: null })).catch((error) => alive && setState({ loading: false, data: null, error }));
    return () => { alive = false; };
  }, [page, location.search]);
  useEffect(load, [load]);
  return { ...state, reload: load };
}
