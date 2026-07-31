"use client";

import { ErrorState } from "@/components/ui/ErrorState";

export default function RouteError({ reset }: Readonly<{ error: Error & { digest?: string }; reset: () => void }>) {
  return (
    <ErrorState
      title="The studio could not open"
      message="Your work is still available. Retry the workspace, or return after checking the local service."
      onRetry={reset}
    />
  );
}
