import { Ban, Check, Clock3, LoaderCircle } from "lucide-react";

import { DemoResultPreview } from "./DemoResultPreview";
import type { DemoJob } from "./types";
import styles from "./studio.module.css";

const statusIcon = {
  queued: Clock3,
  running: LoaderCircle,
  completed: Check,
  canceled: Ban,
} as const;

export function StudioStage2D({
  jobs,
  selectedId,
  onSelect,
}: Readonly<{ jobs: DemoJob[]; selectedId: string; onSelect: (id: string) => void }>) {
  const selectedJob = jobs.find((job) => job.id === selectedId);

  return (
    <div className={styles.stage2d} data-testid="stage-2d">
      <div className={styles.relayHeader}>
        <span>Input queue</span>
        <span>Studio relay</span>
        <span>Output</span>
      </div>

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
                <StatusIcon aria-hidden="true" size={16} />
                <span>{job.status}</span>
                <strong>{job.progress}%</strong>
              </span>
              <span className={styles.jobName}>{job.name}</span>
              <span className={styles.jobPhase}>{job.phase}</span>
              <span className={styles.progressTrack} aria-hidden="true">
                <span style={{ width: `${job.progress}%` }} />
              </span>
            </button>
          );
        })}
      </div>

      <div className={styles.relaySurface}>
        <div className={styles.mediaPlane}>
          {selectedJob?.imageJob?.status === "completed" ? (
            <DemoResultPreview job={selectedJob.imageJob} />
          ) : (
            <div className={styles.processingLabel} aria-hidden="true">
              <span>MEDIA</span>
              <span>PROCESSING PLANE</span>
            </div>
          )}
        </div>
        <span className={styles.relayLine} />
        <div className={styles.outputSlot} aria-hidden="true">
          OUTPUT 01
        </div>
      </div>
    </div>
  );
}
