import { Component, ErrorInfo, ReactNode } from "react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";

type AppErrorBoundaryProps = {
  children: ReactNode;
};

type AppErrorBoundaryState = {
  hasError: boolean;
};

export class AppErrorBoundary extends Component<AppErrorBoundaryProps, AppErrorBoundaryState> {
  state: AppErrorBoundaryState = {
    hasError: false
  };

  static getDerivedStateFromError(): AppErrorBoundaryState {
    return {
      hasError: true
    };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    // Keep an explicit console hook for local debugging and Sentry-style future wiring.
    console.error("Unhandled frontend error", error, info);
  }

  resetBoundary = (): void => {
    this.setState({ hasError: false });
  };

  render(): ReactNode {
    if (!this.state.hasError) {
      return this.props.children;
    }

    return (
      <main className="mx-auto flex min-h-screen w-full max-w-2xl items-center px-4 py-8">
        <Alert variant="destructive">
          <AlertTitle>Unexpected frontend error</AlertTitle>
          <AlertDescription className="space-y-3">
            <p>The page crashed. Retry the route and reload if the problem persists.</p>
            <div className="flex gap-2">
              <Button type="button" variant="outline" onClick={this.resetBoundary}>
                Retry render
              </Button>
              <Button type="button" onClick={() => window.location.reload()}>
                Reload app
              </Button>
            </div>
          </AlertDescription>
        </Alert>
      </main>
    );
  }
}
