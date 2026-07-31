import type { DemoJob, JobStatus } from "./types";

const QUEUE_DURATION_MS = 3_000;
const RUN_DURATION_MS = 9_000;

const jobDefinitions = [
  { id: "frame-compose", name: "Frame compose", phase: "Output ready", initialAgeMs: 13_000 },
  { id: "detail-pass", name: "Detail pass", phase: "Refining image", initialAgeMs: 6_000 },
  { id: "preview-export", name: "Preview export", phase: "Waiting for a slot", initialAgeMs: 0 },
] as const;

function getStatus(ageMs: number): JobStatus {
  if (ageMs < QUEUE_DURATION_MS) return "queued";
  if (ageMs < QUEUE_DURATION_MS + RUN_DURATION_MS) return "running";
  return "completed";
}

function getProgress(ageMs: number, status: JobStatus): number {
  if (status === "queued") return 0;
  if (status === "completed") return 100;

  const runAge = ageMs - QUEUE_DURATION_MS;
  return Math.min(96, Math.max(8, Math.round(8 + (runAge / RUN_DURATION_MS) * 88)));
}

export function createDemoJobs(elapsedMs: number, epochMs: number): DemoJob[] {
  return jobDefinitions.map((definition) => {
    const ageMs = Math.max(0, definition.initialAgeMs + elapsedMs);
    const status = getStatus(ageMs);
    const startedOffset = Math.max(0, ageMs - QUEUE_DURATION_MS);

    return {
      id: definition.id,
      name: definition.name,
      phase:
        status === "queued"
          ? "Waiting for a slot"
          : status === "running"
            ? definition.phase === "Output ready"
              ? "Compositing frame"
              : definition.phase
            : "Output ready",
      status,
      progress: getProgress(ageMs, status),
      startedAt: status === "queued" ? null : new Date(epochMs - startedOffset),
    };
  });
}
