"use client";

import { Component, type ReactNode } from "react";

import { ErrorState } from "@/components/ui/ErrorState";

import { StudioStage2D } from "./StudioStage2D";
import type { DemoJob } from "./types";
import styles from "./studio.module.css";

type BoundaryProps = {
  children: ReactNode;
  jobs: DemoJob[];
  selectedId: string;
  onSelect: (id: string) => void;
  onFallback: () => void;
};

type BoundaryState = { failed: boolean };

export class ThreeStageBoundary extends Component<BoundaryProps, BoundaryState> {
  state: BoundaryState = { failed: false };

  static getDerivedStateFromError(): BoundaryState {
    return { failed: true };
  }

  componentDidCatch() {
    // The public UI intentionally keeps WebGL implementation details private.
  }

  render() {
    if (this.state.failed) {
      return (
        <div className={styles.webglFallback} data-testid="webgl-fallback">
          <ErrorState
            title="3D view is unavailable"
            message="The studio switched to its complete 2D workspace. Your demo jobs remain available."
            retryLabel="Use 2D view"
            onRetry={this.props.onFallback}
          />
          <StudioStage2D
            jobs={this.props.jobs}
            selectedId={this.props.selectedId}
            onSelect={this.props.onSelect}
          />
        </div>
      );
    }

    return this.props.children;
  }
}
