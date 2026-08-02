import { Ban, Check, CircleX, Clock3, ImageIcon, LoaderCircle } from "lucide-react";

import { DemoResultPreview } from "./DemoResultPreview";
import type { DemoJob } from "./types";
import styles from "./studio.module.css";

const statusIcon = {
  queued: Clock3,
  running: LoaderCircle,
  completed: Check,
  failed: CircleX,
  canceled: Ban,
} as const;

export function StudioStage2D({
  jobs,
  selectedId,
  onSelect,
}: Readonly<{ jobs: DemoJob[]; selectedId: string; onSelect: (id: string) => void }>) {
  const selectedJob = jobs.find((job) => job.id === selectedId) ?? jobs[0];

  return (
    <div className={styles.stage2d} data-testid="stage-2d">
      <header className={styles.stageHeader}>
        <div>
          <span>Selected output</span>
          <strong>{selectedJob?.name ?? "No active job"}</strong>
        </div>
        {selectedJob ? (
          <span className={styles.stageStatus} data-status={selectedJob.status}>
            {selectedJob.status} · {selectedJob.progress === null ? "--" : `${selectedJob.progress}%`}
          </span>
        ) : null}
      </header>

      <div className={styles.previewDeck}>
        <div className={styles.mediaPlane}>
          {selectedJob?.imageJob?.status === "completed" ? (
            <DemoResultPreview job={selectedJob.imageJob} />
          ) : (
            <div className={styles.processingLabel}>
              <ImageIcon aria-hidden="true" size={28} />
              <strong>
                {selectedJob?.source === "sample"
                  ? "Demo workflow projection"
                  : selectedJob
                    ? "Output is not ready yet"
                    : "Create an image to begin"}
              </strong>
              <span>
                {selectedJob?.source === "sample"
                  ? "Sample jobs demonstrate shared 2D and 3D state without a rendered result."
                  : selectedJob?.imageJob?.prompt ?? "Your selected result will appear here."}
              </span>
            </div>
          )}
        </div>
      </div>

      <section className={styles.queueDock} aria-label="Generation activity">
        <header>
          <span>Activity</span>
          <small>{jobs.length} visible jobs</small>
        </header>
        <div className={styles.jobLane}>
          {jobs.map((job) => {
            const StatusIcon = statusIcon[job.status];
            return (
              <button
                className={styles.jobCard}
                data-status={job.status}
                data-selected={selectedId === job.id}
                key={job.id}
                type="button"
                onClick={() => onSelect(job.id)}
                aria-pressed={selectedId === job.id}
              >
                <span className={styles.jobCardTopline}>
                  <StatusIcon aria-hidden="true" size={15} />
                  <span>{job.status}</span>
                  <strong>{job.progress === null ? "--" : `${job.progress}%`}</strong>
                </span>
                <span className={styles.jobName}>{job.name}</span>
                <span className={styles.jobPhase}>{job.phase}</span>
                {job.progress !== null ? (
                  <span className={styles.progressTrack} aria-hidden="true">
                    <span style={{ width: `${job.progress}%` }} />
                  </span>
                ) : null}
              </button>
            );
          })}
        </div>
      </section>
    </div>
  );
}
