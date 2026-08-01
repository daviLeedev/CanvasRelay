import { Suspense } from "react";

import { AppShell, WorkspaceLoading } from "@/components/app-shell/AppShell";
import { ImageEditWorkspace } from "@/features/edit/ImageEditWorkspace";

export default function ImageEditPage() {
  return (
    <AppShell>
      <Suspense fallback={<WorkspaceLoading label="Loading image edit..." />}>
        <ImageEditWorkspace />
      </Suspense>
    </AppShell>
  );
}
