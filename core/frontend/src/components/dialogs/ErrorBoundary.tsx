import React, { Component, ReactNode } from 'react';
import { AlertCircle } from 'lucide-react';
import { Button } from '../ui/button';

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
}

/**
 * Error boundary component to catch and handle errors in dialog components.
 * Prevents the entire application from crashing when a dialog encounters an error.
 */
export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    console.error('Error boundary caught error:', error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback;
      }

      return (
        <div className="flex flex-col items-center justify-center gap-4 p-8">
          <AlertCircle className="h-12 w-12 text-danger" />
          <div className="text-center space-y-2">
            <h3 className="font-semibold text-foreground">Something went wrong</h3>
            <p className="text-sm text-muted-foreground">
              An error occurred while loading this dialog.
            </p>
          </div>
          <Button
            onClick={() => this.setState({ hasError: false })}
            variant="outline"
          >
            Try Again
          </Button>
        </div>
      );
    }

    return this.props.children;
  }
}
