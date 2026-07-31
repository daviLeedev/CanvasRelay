"use client";

import { Box, Layers3, RotateCcw } from "lucide-react";
import { lazy, Suspense, useMemo, useState } from "react";

import { HealthPanel } from "@/components/health/HealthPanel";
import { Button } from "@/components/ui/Button";
import { Field } from "@/components/ui/Field";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { Select } from "@/components/ui/Select";
import { StatusIndicator } from "@/components/ui/StatusIndicator";
import { useHealthQuery } from "@/lib/api/useHealthQuery";
import { useImageProviderQuery } from "@/lib/api/useImageProviderQuery";

import { StudioStage2D } from "./StudioStage2D";
import { RecentImageJobs } from "./RecentImageJobs";
import { ThreeStageBoundary } from "./ThreeStageBoundary";
import type { DisplayMode, JobStatus } from "./types";
import { ImageGenerationPanel } from "./ImageGenerationPanel";
import { projectImageJob } from "./demoJobs";
import { useDemoJobs } from "./useDemoJobs";
import { useDisplayPreference } from "./useDisplayPreference";
import { useImageGenerationJob } from "./useImageGenerationJob";
import { usePageVisibility } from "./usePageVisibility";
import { useReducedMotion } from "./useReducedMotion";
import styles from "./studio.module.css";

const LazyStudioStage3D = lazy(() =>
  import("./StudioStage3D").then((module) => ({ default: module.StudioStage3D })),
);

const modeOptions = [
  { value: "2d", label: "2D", icon: <Layers3 aria-hidden="true" size={14} /> },
  { value: "3d", label: "3D", icon: <Box aria-hidden="true" size={14} /> },
] as const;

const statusTone: Record<JobStatus, "success" | "warning" | "neutral" | "danger"> = {
  queued: "warning",
  running: "neutral",
  completed: "success",
  failed: "danger",
  canceled: "neutral",
};

function formatStartedAt(startedAt: Date | null) {
  if (!startedAt) return "Not started";
  return new Intl.DateTimeFormat("en", { hour: "2-digit", minute: "2-digit", second: "2-digit" }).format(
    startedAt,
  );
}

function ApiToolbarStatus() {
  const healthQuery = useHealthQuery();
  const isChecking = healthQuery.isPending || healthQuery.isFetching;

  if (isChecking) return <StatusIndicator label="API checking" tone="warning" />;
  if (healthQuery.isSuccess) return <StatusIndicator label="API connected" tone="success" />;
  return <StatusIndicator label="API unavailable" tone="danger" />;
}

export function StudioWorkspace() {
  const { jobs: sampleJobs, restart } = useDemoJobs();
  const imageGeneration = useImageGenerationJob();
  const imageProvider = useImageProviderQuery();
  const { mode, setMode } = useDisplayPreference();
  const reducedMotion = useReducedMotion();
  const pageVisible = usePageVisibility();
  const jobs = useMemo(() => {
    const recent = imageGeneration.recentJobs.slice(0, 3).map(projectImageJob);
    if (imageGeneration.job && !recent.some((item) => item.id === imageGeneration.job?.id)) {
      recent.unshift(projectImageJob(imageGeneration.job));
    }
    return recent.length > 0 ? recent.slice(0, 3) : sampleJobs;
  }, [imageGeneration.job, imageGeneration.recentJobs, sampleJobs]);
  const [selectedId, setSelectedId] = useState(sampleJobs[1]?.id ?? sampleJobs[0]?.id ?? "");
  async function submitImageJob(input: Parameters<typeof imageGeneration.submit>[0]) {
    const job = await imageGeneration.submit(input);
    if (job) setSelectedId(job.id);
  }

  async function retryImageJob() {
    const job = await imageGeneration.retry();
    if (job) setSelectedId(job.id);
  }

  const selectedJob = useMemo(
    () => jobs.find((job) => job.id === selectedId) ?? jobs[0],
    [jobs, selectedId],
  );
  const effectiveSelectedId = selectedJob?.id ?? "";
  const summary = useMemo(
    () => ({
      queued: jobs.filter((job) => job.status === "queued").length,
      running: jobs.filter((job) => job.status === "running").length,
      completed: jobs.filter((job) => job.status === "completed").length,
    }),
    [jobs],
  );

  return (
    <div className={styles.workspace}>
      <header className={styles.localToolbar}>
        <div className={styles.workspaceTitle}>
          <span>Image workspace</span>
          <h1>Studio relay</h1>
        </div>

        <div className={styles.toolbarStatus}>
          <ApiToolbarStatus />
          <span className={styles.summary} aria-label="Mock job summary">
            <span>{summary.queued} queued</span>
            <span>{summary.running} running</span>
            <span>{summary.completed} complete</span>
          </span>
        </div>

        <div className={styles.toolbarActions}>
          <Button variant="quiet" onClick={restart}>
            <RotateCcw aria-hidden="true" size={15} />
            Demo restart
          </Button>
          <SegmentedControl<DisplayMode>
            label="Stage view"
            options={modeOptions}
            value={mode}
            onChange={setMode}
          />
        </div>
      </header>

      <div className={styles.contentGrid}>
        <section className={styles.stage} aria-label={`${mode.toUpperCase()} job stage`}>
          {mode === "2d" ? (
            <StudioStage2D jobs={jobs} selectedId={effectiveSelectedId} onSelect={setSelectedId} />
          ) : (
            <ThreeStageBoundary
              jobs={jobs}
              selectedId={effectiveSelectedId}
              onSelect={setSelectedId}
              onFallback={() => setMode("2d")}
            >
              <Suspense fallback={<div className={styles.stageLoading}>Preparing 3D workspace...</div>}>
                <LazyStudioStage3D
                  jobs={jobs}
                  selectedId={effectiveSelectedId}
                  onSelect={setSelectedId}
                  reducedMotion={reducedMotion}
                  pageVisible={pageVisible}
                />
              </Suspense>
            </ThreeStageBoundary>
          )}
        </section>

        <aside className={styles.inspector} aria-label="Job and API inspector">
          <div className={styles.inspectorStack}>
            <ImageGenerationPanel
              job={imageGeneration.job}
              isBusy={imageGeneration.isBusy}
              isSubmitting={imageGeneration.isSubmitting}
              isCanceling={imageGeneration.isCanceling}
              hasError={imageGeneration.hasError}
              canRetry={imageGeneration.canRetry}
              provider={imageProvider.data ?? null}
              providerStatusUnavailable={imageProvider.isError}
              onSubmit={submitImageJob}
              onCancel={imageGeneration.cancel}
              onRetry={retryImageJob}
            />

            <RecentImageJobs
              jobs={imageGeneration.recentJobs}
              selectedId={imageGeneration.job?.id}
              loading={imageGeneration.isLoadingRecent}
              onSelect={(jobId) => {
                imageGeneration.selectJob(jobId);
                setSelectedId(jobId);
              }}
            />

            <section className={styles.jobInspector} aria-labelledby="job-inspector-title">
              <header className={styles.inspectorHeader}>
                <div>
                  <span>Selected job</span>
                  <h2 id="job-inspector-title">{selectedJob?.name ?? "No job"}</h2>
                </div>
                {selectedJob ? (
                  <StatusIndicator label={selectedJob.status} tone={statusTone[selectedJob.status]} />
                ) : null}
              </header>

              <div className={styles.inspectorBody}>
                <Field label="Focus job" htmlFor="focus-job" hint="Selection is shared by the 2D and 3D stage.">
                  <Select
                    id="focus-job"
                    value={effectiveSelectedId}
                    onChange={(event) => setSelectedId(event.target.value)}
                  >
                    {jobs.map((job) => (
                      <option value={job.id} key={job.id}>
                        {job.name}
                      </option>
                    ))}
                  </Select>
                </Field>

                {selectedJob ? (
                  <>
                    <div className={styles.progressBlock}>
                      <div>
                        <span>Progress</span>
                        <strong>
                          {selectedJob.progress === null ? "Unavailable" : `${selectedJob.progress}%`}
                        </strong>
                      </div>
                      {selectedJob.progress !== null ? (
                        <span className={styles.inspectorProgress} aria-hidden="true">
                          <span style={{ width: `${selectedJob.progress}%` }} />
                        </span>
                      ) : null}
                    </div>

                    <dl className={styles.jobDetails}>
                      <div>
                        <dt>Phase</dt>
                        <dd>{selectedJob.phase}</dd>
                      </div>
                      <div>
                        <dt>Started</dt>
                        <dd>{formatStartedAt(selectedJob.startedAt)}</dd>
                      </div>
                      <div>
                        <dt>Mode</dt>
                        <dd>{mode.toUpperCase()} projection</dd>
                      </div>
                      {selectedJob.imageJob ? (
                        <>
                          <div>
                            <dt>Ratio</dt>
                            <dd>{selectedJob.imageJob.settings.aspectRatio}</dd>
                          </div>
                          <div>
                            <dt>Style</dt>
                            <dd>{selectedJob.imageJob.settings.style}</dd>
                          </div>
                          <div>
                            <dt>Seed</dt>
                            <dd>{selectedJob.imageJob.settings.seed}</dd>
                          </div>
                          <div>
                            <dt>Provider</dt>
                            <dd>{selectedJob.imageJob.settings.provider}</dd>
                          </div>
                          <div>
                            <dt>Created</dt>
                            <dd>{formatStartedAt(new Date(selectedJob.imageJob.createdAt))}</dd>
                          </div>
                        </>
                      ) : null}
                    </dl>
                    {selectedJob.imageJob ? (
                      <p className={styles.jobPrompt}>{selectedJob.imageJob.prompt}</p>
                    ) : null}
                  </>
                ) : null}
              </div>
            </section>
          </div>

          <HealthPanel />
        </aside>
      </div>
    </div>
  );
}
