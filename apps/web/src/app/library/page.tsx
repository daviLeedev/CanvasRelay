import { AppShell } from "@/components/app-shell/AppShell";
import { LibraryWorkspace } from "@/features/library/LibraryWorkspace";

export default function LibraryPage() {
  return (
    <AppShell>
      <LibraryWorkspace />
    </AppShell>
  );
}
