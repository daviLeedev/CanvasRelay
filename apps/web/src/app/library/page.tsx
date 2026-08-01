import { Suspense } from "react";

import { AppShell, WorkspaceLoading } from "@/components/app-shell/AppShell";
import { LibraryWorkspace } from "@/features/library/LibraryWorkspace";

export default function LibraryPage() {
  return (
    <AppShell>
      <Suspense fallback={<WorkspaceLoading label="Loading image library..." />}>
        <LibraryWorkspace />
      </Suspense>
    </AppShell>
  );
}
