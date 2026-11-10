import { ErrorState, Loading } from "./Loading";

export default function PageState({ state, children }) {
  if (state.loading) return <Loading/>;
  if (state.error) return <ErrorState error={state.error} retry={state.reload}/>;
  return children(state.data);
}
