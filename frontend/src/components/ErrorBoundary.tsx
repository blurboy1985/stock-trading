import { Component, type ErrorInfo, type ReactNode } from "react";

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("Render error", error, info.componentStack);
  }

  render() {
    if (!this.state.error) return this.props.children;

    return (
      <div className="bg-sell/10 border border-sell/40 text-sell rounded-lg px-4 py-3 text-sm space-y-3">
        <div>Dashboard rendering failed: {this.state.error.message || "unknown error"}</div>
        <button
          type="button"
          onClick={() => this.setState({ error: null })}
          className="px-3 py-1.5 rounded-lg border border-sell/40 bg-panel2 text-sell hover:bg-edge"
        >
          Retry
        </button>
      </div>
    );
  }
}
