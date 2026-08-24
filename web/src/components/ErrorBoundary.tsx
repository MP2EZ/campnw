import { Component, type ReactNode, type ErrorInfo } from "react";
import { getPosthog } from "../api";

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
}

export class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false };

  static getDerivedStateFromError(): State {
    return { hasError: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("ErrorBoundary caught:", error, info.componentStack);
    // The snippet's capture_exceptions only sees *uncaught* errors — a React
    // boundary swallows the error before it reaches window.onerror, so the
    // crashes that actually blank the UI are exactly the ones that need an
    // explicit report.
    const ph = getPosthog();
    ph?.captureException(error, { componentStack: info.componentStack });
    ph?.capture("app_crashed", {
      error_name: error.name,
      error_message: error.message,
      route: window.location.pathname,
    });
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="error-boundary">
          <h2>Something went wrong</h2>
          <p>An unexpected error occurred. Try reloading the page.</p>
          <button onClick={() => window.location.reload()}>Reload</button>
        </div>
      );
    }
    return this.props.children;
  }
}
