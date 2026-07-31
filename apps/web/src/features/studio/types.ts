export type DisplayMode = "2d" | "3d";

export type JobStatus = "queued" | "running" | "completed";

export type DemoJob = {
  id: string;
  name: string;
  phase: string;
  status: JobStatus;
  progress: number;
  startedAt: Date | null;
};
