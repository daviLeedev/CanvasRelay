"use client";

import { ImagePlus, ScanFace } from "lucide-react";
import Image from "next/image";
import { useEffect, useMemo, useState } from "react";

import { HealthPanel } from "@/components/health/HealthPanel";
import { StatusIndicator } from "@/components/ui/StatusIndicator";
import { RecentImageJobs } from "@/features/studio/RecentImageJobs";
import { getImageResultUrl } from "@/lib/api/imageJobs";
import { useHealthQuery } from "@/lib/api/useHealthQuery";
import { useImageEditProviderQuery } from "@/lib/api/useImageProviderQuery";

import { ImageEditPanel } from "./ImageEditPanel";
import { useImageEditJob } from "./useImageEditJob";
import styles from "./edit.module.css";

function ApiStatus() {
  const health = useHealthQuery();
  if (health.isPending || health.isFetching) return <StatusIndicator label="API checking" tone="warning" />;
  if (health.isSuccess) return <StatusIndicator label="API connected" tone="success" />;
  return <StatusIndicator label="API unavailable" tone="danger" />;
}

export function ImageEditWorkspace() {
  const edit = useImageEditJob();
  const provider = useImageEditProviderQuery();
  const [sourceFile, setSourceFile] = useState<File | null>(null);
  const sourceUrl = useMemo(
    () => (sourceFile ? URL.createObjectURL(sourceFile) : null),
    [sourceFile],
  );

  useEffect(() => {
    return () => {
      if (sourceUrl) URL.revokeObjectURL(sourceUrl);
    };
  }, [sourceUrl]);

  const resultUrl = edit.job ? getImageResultUrl(edit.job) : null;
  const active = edit.job?.status === "queued" || edit.job?.status === "running";

  async function submit(input: Parameters<typeof edit.submit>[0]) {
    await edit.submit(input);
  }

  return (
    <div className={styles.workspace}>
      <header className={styles.toolbar}>
        <div className={styles.title}>
          <span>Source-guided workflow</span>
          <h1>Image edit</h1>
        </div>
        <div className={styles.toolbarStatus}>
          <ApiStatus />
          <span className={styles.workflowMode}>
            {edit.job?.settings.hasFaceReference ? <ScanFace aria-hidden="true" size={14} /> : <ImagePlus aria-hidden="true" size={14} />}
            {edit.job?.settings.hasFaceReference ? "Two-reference edit" : "Image-to-image"}
          </span>
        </div>
      </header>

      <div className={styles.contentGrid}>
        <main className={styles.stage} aria-label="Image edit comparison stage">
          <section className={styles.comparisonPane} aria-label="Source image preview">
            <header><span>Source</span><strong>{sourceFile?.name ?? "No image"}</strong></header>
            <div className={styles.mediaFrame}>
              {sourceUrl ? (
                <Image src={sourceUrl} alt="Selected source" fill sizes="(max-width: 900px) 100vw, 50vw" unoptimized />
              ) : (
                <div className={styles.emptyStage}><ImagePlus aria-hidden="true" size={28} /><span>Select a source image</span></div>
              )}
            </div>
          </section>

          <section className={styles.comparisonPane} aria-label="Edited image preview">
            <header>
              <span>Result</span>
              <strong>{edit.job?.status ?? "Waiting"}</strong>
            </header>
            <div className={styles.mediaFrame}>
              {resultUrl && edit.job?.status === "completed" ? (
                <Image src={resultUrl} alt={`Edited result for ${edit.job.prompt}`} fill sizes="(max-width: 900px) 100vw, 50vw" unoptimized priority />
              ) : (
                <div className={styles.emptyStage} data-active={active ? "true" : "false"}>
                  <span>{active ? "Local edit in progress" : "The edited result appears here"}</span>
                  {active && edit.job?.progress !== null ? <strong>{edit.job?.progress ?? 0}%</strong> : null}
                </div>
              )}
            </div>
          </section>
        </main>

        <aside className={styles.inspector} aria-label="Image edit controls">
          <ImageEditPanel
            job={edit.job}
            isBusy={edit.isBusy}
            isSubmitting={edit.isSubmitting}
            isCanceling={edit.isCanceling}
            hasError={edit.hasError}
            canRetry={edit.canRetry}
            provider={provider.data ?? null}
            providerStatusUnavailable={provider.isError}
            onSourcePreview={setSourceFile}
            onSubmit={submit}
            onCancel={edit.cancel}
            onRetry={edit.retry}
          />
          <RecentImageJobs
            jobs={edit.recentJobs}
            selectedId={edit.job?.id}
            loading={edit.isLoadingRecent}
            onSelect={edit.selectJob}
          />
          <HealthPanel />
        </aside>
      </div>
    </div>
  );
}
