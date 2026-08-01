"use client";

import { Columns2, Download, ImagePlus, Maximize2, Minus, Plus, ScanFace } from "lucide-react";
import Image from "next/image";
import { useSearchParams } from "next/navigation";
import { useQuery } from "@tanstack/react-query";
import { type CSSProperties, useEffect, useMemo, useRef, useState } from "react";

import { HealthPanel } from "@/components/health/HealthPanel";
import { StatusIndicator } from "@/components/ui/StatusIndicator";
import { RecentImageJobs } from "@/features/studio/RecentImageJobs";
import {
  fetchImageJob,
  getImageInputUrl,
  getImageResultUrl,
  type ImageJobResponse,
} from "@/lib/api/imageJobs";
import { useHealthQuery } from "@/lib/api/useHealthQuery";
import {
  useImageEditOptionsQuery,
  useImageEditProviderQuery,
} from "@/lib/api/useImageProviderQuery";

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
  const options = useImageEditOptionsQuery();
  const searchParams = useSearchParams();
  const [sourceFile, setSourceFile] = useState<File | null>(null);
  const [sourceJobOverride, setSourceJobOverride] = useState<ImageJobResponse | null | undefined>();
  const requestedSourceId = searchParams?.get("sourceJobId") ?? null;
  const requestedRestoreId = searchParams?.get("restoreJobId") ?? null;
  const [compare, setCompare] = useState(50);
  const [compareJobId, setCompareJobId] = useState<string | null>(null);
  const [zoom, setZoom] = useState(1);
  const [toast, setToast] = useState<string | null>(null);
  const previousStatus = useRef<ImageJobResponse["status"] | null>(null);
  const handoff = useQuery({
    queryKey: ["image-job", "edit-source", requestedSourceId],
    queryFn: ({ signal }) => fetchImageJob(requestedSourceId ?? "", signal),
    enabled: Boolean(requestedSourceId),
  });
  const restore = useQuery({
    queryKey: ["image-job", "edit-restore", requestedRestoreId],
    queryFn: ({ signal }) => fetchImageJob(requestedRestoreId ?? "", signal),
    enabled: Boolean(requestedRestoreId),
  });
  const sourceFileUrl = useMemo(() => sourceFile ? URL.createObjectURL(sourceFile) : null, [sourceFile]);

  useEffect(() => () => { if (sourceFileUrl) URL.revokeObjectURL(sourceFileUrl); }, [sourceFileUrl]);
  useEffect(() => {
    const status = edit.job?.status ?? null;
    if (status && status !== previousStatus.current && (status === "completed" || status === "failed")) {
      setToast(status === "completed" ? "Image edit completed." : "Image edit failed. Review the job details.");
      const timer = window.setTimeout(() => setToast(null), 4500);
      previousStatus.current = status;
      return () => window.clearTimeout(timer);
    }
    previousStatus.current = status;
  }, [edit.job?.status]);

  const resultUrl = edit.job ? getImageResultUrl(edit.job) : null;
  const handoffSourceJob = handoff.data?.status === "completed" ? handoff.data : null;
  const templateJob = restore.data?.settings.operation === "edit" ? restore.data : null;
  const sourceJob = sourceJobOverride === undefined ? handoffSourceJob : sourceJobOverride;
  const linkedSourceUrl = sourceJob ? getImageResultUrl(sourceJob) : null;
  const storedInputUrl = edit.job?.settings.operation === "edit"
    ? getImageInputUrl(edit.job.id, "source")
    : null;
  const sourceUrl = sourceFileUrl ?? linkedSourceUrl ?? storedInputUrl;
  const active = edit.job?.status === "queued" || edit.job?.status === "running";
  const completed = Boolean(resultUrl && edit.job?.status === "completed");
  const comparing = Boolean(completed && sourceUrl && compareJobId === edit.job?.id);

  return (
    <div className={styles.workspace}>
      <header className={styles.toolbar}>
        <div className={styles.title}><span>Source-guided workflow</span><h1>Image edit</h1></div>
        <div className={styles.toolbarStatus}>
          <ApiStatus />
          <span className={styles.workflowMode}>
            {edit.job?.settings.hasFaceReference ? <ScanFace aria-hidden="true" size={14} /> : <ImagePlus aria-hidden="true" size={14} />}
            {edit.job?.settings.hasFaceReference ? "Two-reference edit" : "Image-to-image"}
          </span>
        </div>
      </header>

      <div className={styles.contentGrid}>
        <main className={styles.stage} aria-label="Image edit result stage">
          <div className={styles.stageTools}>
            <span>{completed ? (comparing ? "Source / result comparison" : "Completed result") : active ? edit.job?.phase : "Result preview"}</span>
            <div>
              {completed && sourceUrl ? (
                <button
                  type="button"
                  aria-label="Compare source and result"
                  aria-pressed={comparing}
                  onClick={() => setCompareJobId((value) => value === edit.job?.id ? null : (edit.job?.id ?? null))}
                >
                  <Columns2 size={15} />
                </button>
              ) : null}
              <button type="button" aria-label="Zoom out" onClick={() => setZoom((value) => Math.max(0.5, value - 0.25))}><Minus size={15} /></button>
              <button type="button" aria-label="Fit image" onClick={() => setZoom(1)}><Maximize2 size={15} /></button>
              <button type="button" aria-label="Zoom in" onClick={() => setZoom((value) => Math.min(3, value + 0.25))}><Plus size={15} /></button>
              {completed && resultUrl ? <a href={resultUrl} download={`canvasrelay-${edit.job?.id}.png`} aria-label="Download result"><Download size={15} /></a> : null}
            </div>
          </div>

          <div className={styles.compareFrame} style={{ "--media-zoom": zoom } as CSSProperties}>
            {completed && resultUrl ? (
              <>
                {comparing && sourceUrl ? <Image src={sourceUrl} alt="Edit source comparison" fill sizes="(max-width: 1000px) 100vw, 70vw" unoptimized /> : null}
                <div
                  className={styles.resultLayer}
                  style={comparing ? { clipPath: `inset(0 ${100 - compare}% 0 0)` } : undefined}
                >
                <Image src={resultUrl} alt={`Edited result for ${edit.job?.prompt}`} fill sizes="(max-width: 1000px) 100vw, 70vw" unoptimized priority />
                </div>
              </>
            ) : active ? (
              <div className={styles.activeStage}>
                <span>{edit.job?.phase === "queued" ? "Queued" : "Processing"}</span>
                <strong>{edit.job?.phase === "queued" ? "Waiting for the provider" : "Editing image"}</strong>
                <p>{edit.job?.currentStep !== null && edit.job?.totalSteps !== null ? `Step ${edit.job?.currentStep} of ${edit.job?.totalSteps}` : "Waiting for provider progress"}</p>
              </div>
            ) : edit.job?.status === "failed" ? (
              <div className={styles.emptyStage}><ImagePlus aria-hidden="true" size={28} /><strong>Edit did not complete</strong><span>Review the error in the Inspector and retry when ready.</span></div>
            ) : (
              <div className={styles.emptyStage}><ImagePlus aria-hidden="true" size={28} /><strong>No completed edit selected</strong><span>Choose a source in the Inspector, then run an edit.</span></div>
            )}
            {comparing ? <div className={styles.compareDivider} style={{ left: `${compare}%` }} aria-hidden="true" /> : null}
          </div>
          {comparing ? <label className={styles.compareControl}>Source / Result<input aria-label="Comparison position" type="range" min="0" max="100" value={compare} onChange={(event) => setCompare(Number(event.target.value))} /></label> : null}
        </main>

        <aside className={styles.inspector} aria-label="Image edit controls">
          <ImageEditPanel
            key={`${edit.job?.settings.operation === "edit" ? edit.job.id : "new-edit"}:${templateJob?.id ?? "no-template"}`}
            job={edit.job}
            templateJob={templateJob}
            sourceJob={sourceJob}
            sourceJobPreview={linkedSourceUrl}
            options={options.data ?? null}
            isBusy={edit.isBusy}
            isSubmitting={edit.isSubmitting}
            isCanceling={edit.isCanceling}
            hasError={edit.hasError}
            canRetry={edit.canRetry}
            provider={provider.data ?? null}
            providerStatusUnavailable={provider.isError}
            onSourceJobChange={(nextJob) => setSourceJobOverride(nextJob)}
            onSourcePreview={setSourceFile}
            onSubmit={async (input) => { await edit.submit(input); }}
            onCancel={edit.cancel}
            onRetry={edit.retry}
          />
          <RecentImageJobs jobs={edit.recentJobs} selectedId={edit.job?.id} loading={edit.isLoadingRecent} onSelect={edit.selectJob} />
          <HealthPanel />
        </aside>
      </div>
      {toast ? <div className={styles.toast} role="status" aria-live="polite">{toast}</div> : null}
    </div>
  );
}
