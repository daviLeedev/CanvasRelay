"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { KeyRound, RefreshCw, ShieldCheck, Unplug } from "lucide-react";

import { Button } from "@/components/ui/Button";
import { ErrorState } from "@/components/ui/ErrorState";
import { StatusIndicator } from "@/components/ui/StatusIndicator";
import {
  checkOwnerConnection,
  disconnectOwnerConnection,
  fetchOwnerConnection,
  importOwnerConnection,
  restartOwnerConnection,
  type OwnerConnection,
} from "@/lib/api/imageJobs";

import styles from "./owner-connection.module.css";

export function OwnerConnectionWorkspace() {
  const queryClient = useQueryClient();
  const connection = useQuery({ queryKey: ["owner-codex-connection"], queryFn: fetchOwnerConnection, retry: false });
  const update = useMutation({
    mutationFn: (action: "import" | "check" | "restart" | "disconnect") => ({
      import: importOwnerConnection,
      check: checkOwnerConnection,
      restart: restartOwnerConnection,
      disconnect: disconnectOwnerConnection,
    }[action])(),
    onSuccess: (value: OwnerConnection) => queryClient.setQueryData(["owner-codex-connection"], value),
  });
  const value = connection.data;
  const tone = value?.connected ? "success" : value?.state === "reauth_required" ? "danger" : "warning";

  return (
    <main className={styles.page}>
      <header className={styles.header}><div><span>Local owner configuration</span><h1>Owner GPT connection</h1><p>CanvasRelay uses the Codex login on this computer. No token is displayed, uploaded, or saved by CanvasRelay.</p></div>{value ? <StatusIndicator label={value.state.replaceAll("_", " ")} tone={tone} /> : null}</header>
      {connection.isError ? <ErrorState title="Connection status is unavailable" message="Open Settings from the owner computer and try the connection check again." retryLabel="Retry" onRetry={() => void connection.refetch()} /> : null}
      {value ? <section className={styles.connection}><div className={styles.connectionCopy}><KeyRound aria-hidden="true" size={20} /><div><strong>{value.connected ? "Owner connection is ready" : "Owner connection needs attention"}</strong><p>{value.message}</p></div></div><div className={styles.actions}><Button variant="primary" onClick={() => update.mutate("import")} disabled={update.isPending}><ShieldCheck aria-hidden="true" size={15} /> Detect local login</Button><Button variant="secondary" onClick={() => update.mutate("check")} disabled={update.isPending}>Check</Button><Button variant="quiet" onClick={() => update.mutate("restart")} disabled={update.isPending}><RefreshCw aria-hidden="true" size={15} /> Restart</Button>{value.connected ? <Button variant="quiet" onClick={() => update.mutate("disconnect")} disabled={update.isPending}><Unplug aria-hidden="true" size={15} /> Disconnect</Button> : null}</div></section> : null}
      <section className={styles.guidance}><h2>How this local connection works</h2><ol><li>Sign in to Codex on this owner computer using the supported Codex flow.</li><li>Use <strong>Detect local login</strong> to start the loopback-only connection.</li><li>Use GPT image from this same local CanvasRelay server. It is not a visitor&apos;s own ChatGPT account connection.</li></ol><p>Remote generation and connection management stay disabled unless the local server owner explicitly enables them.</p></section>
    </main>
  );
}
