import { Component, type ErrorInfo, type ReactNode } from 'react';

type Props = { children: ReactNode };
type State = { hasError: boolean };

// App-wide safety net: a render-time throw on any surface shows a small recovery
// card instead of white-screening a booth display (the TV, kiosk, or a player's
// phone). Reloading re-mounts the tree from a clean state.
export default class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false };

  static getDerivedStateFromError(): State {
    return { hasError: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    // Surfaces to the browser console / any attached error reporter.
    console.error('Surface crashed:', error, info.componentStack);
  }

  render(): ReactNode {
    if (!this.state.hasError) return this.props.children;
    return (
      <div className="app-crash" role="alert">
        <div className="app-crash-card">
          <div className="app-crash-eyebrow">Quip Network</div>
          <h1>This screen hit an error.</h1>
          <p>Something unexpected happened. Reloading usually clears it.</p>
          <button type="button" onClick={() => window.location.reload()}>Reload</button>
        </div>
      </div>
    );
  }
}
