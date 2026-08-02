import { Suspense } from "react";

import { AppShell, WorkspaceLoading } from "@/components/app-shell/AppShell";
import { JobCenterWorkspace } from "@/features/jobs/JobCenterWorkspace";

export default function JobsPage() {
  return (
    <AppShell>
      <Suspense fallback={<WorkspaceLoading label="Loading job center..." />}>
        <JobCenterWorkspace />
      </Suspense>
    </AppShell>
  );
}
