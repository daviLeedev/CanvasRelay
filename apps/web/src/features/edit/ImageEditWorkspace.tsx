"use client";

import { Download, ImagePlus, Maximize2, Minus, Plus, ScanFace } from "lucide-react";
import Image from "next/image";
import { useQuery } from "@tanstack/react-query";
import { type CSSProperties, useEffect, useMemo, useRef, useState } from "react";

import { HealthPanel } from "@/components/health/HealthPanel";
import { Button } from "@/components/ui/Button";
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
  const [sourceFile, setSourceFile] = useState<File | null>(null);
  const [sourceJob, setSourceJob] = useState<ImageJobResponse | null>(null);
  const [requestedSourceId, setRequestedSourceId] = useState<string | null>(null);
  const [compare, setCompare] = useState(50);
  const [zoom, setZoom] = useState(1);
  const [toast, setToast] = useState<string | null>(null);
  const previousStatus = useRef<ImageJobResponse["status"] | null>(null);
  const handoff = useQuery({
    queryKey: ["image-job", "edit-source", requestedSourceId],
    queryFn: ({ signal }) => fetchImageJob(requestedSourceId ?? "", signal),
    enabled: Boolean(requestedSourceId),
  });
  const sourceFileUrl = useMemo(() => sourceFile ? URL.createObjectURL(sourceFile) : null, [sourceFile]);

  useEffect(() => {
    setRequestedSourceId(new URLSearchParams(window.location.search).get("sourceJobId"));
  }, []);
  useEffect(() => () => { if (sourceFileUrl) URL.revokeObjectURL(sourceFileUrl); }, [sourceFileUrl]);
  useEffect(() => {
    if (handoff.data?.status === "completed") setSourceJob(handoff.data);
  }, [handoff.data]);
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
  const linkedSourceUrl = sourceJob ? getImageResultUrl(sourceJob) : null;
  const storedInputUrl = edit.job?.settings.operation === "edit"
    ? getImageInputUrl(edit.job.id, "source")
    : null;
  const sourceUrl = sourceFileUrl ?? linkedSourceUrl ?? storedInputUrl;
  const active = edit.job?.status === "queued" || edit.job?.status === "running";
  const completed = Boolean(resultUrl && edit.job?.status === "completed");

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
        <main className={styles.stage} aria-label="Image edit comparison stage">
          <div className={styles.stageTools}>
            <span>{completed ? "Compare source and result" : active ? edit.job?.phase : "Preview"}</span>
            <div>
              <button type="button" aria-label="Zoom out" onClick={() => setZoom((value) => Math.max(0.5, value - 0.25))}><Minus size={15} /></button>
              <button type="button" aria-label="Fit image" onClick={() => setZoom(1)}><Maximize2 size={15} /></button>
              <button type="button" aria-label="Zoom in" onClick={() => setZoom((value) => Math.min(3, value + 0.25))}><Plus size={15} /></button>
              {completed && resultUrl ? <a href={resultUrl} download={`canvasrelay-${edit.job?.id}.png`} aria-label="Download result"><Download size={15} /></a> : null}
            </div>
          </div>

          <div className={styles.compareFrame} style={{ "--media-zoom": zoom } as CSSProperties}>
            {sourceUrl ? <Image src={sourceUrl} alt="Edit source" fill sizes="(max-width: 1000px) 100vw, 70vw" unoptimized /> : <div className={styles.emptyStage}><ImagePlus aria-hidden="true" size={28} /><span>Select a source image</span></div>}
            {completed && resultUrl ? (
              <div className={styles.resultLayer} style={{ clipPath: `inset(0 ${100 - compare}% 0 0)` }}>
                <Image src={resultUrl} alt={`Edited result for ${edit.job?.prompt}`} fill sizes="(max-width: 1000px) 100vw, 70vw" unoptimized priority />
              </div>
            ) : active ? (
              <div className={styles.progressOverlay}>
                <strong>{edit.job?.phase === "queued" ? "Waiting in queue" : "Local edit in progress"}</strong>
                <span>{edit.job?.currentStep !== null && edit.job?.totalSteps !== null ? `Step ${edit.job?.currentStep} / ${edit.job?.totalSteps}` : "Waiting for provider progress"}</span>
              </div>
            ) : null}
            {completed ? <div className={styles.compareDivider} style={{ left: `${compare}%` }} aria-hidden="true" /> : null}
          </div>
          {completed ? <label className={styles.compareControl}>Source / Result<input aria-label="Compare source and result" type="range" min="0" max="100" value={compare} onChange={(event) => setCompare(Number(event.target.value))} /></label> : null}
        </main>

        <aside className={styles.inspector} aria-label="Image edit controls">
          <ImageEditPanel
            job={edit.job}
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
            onSourceJobChange={setSourceJob}
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
