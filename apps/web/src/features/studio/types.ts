export type DisplayMode = "2d" | "3d";

import type { ImageJobResponse } from "@/lib/api/imageJobs";

export type JobStatus = "queued" | "running" | "completed" | "failed" | "canceled";

export type DemoJob = {
  id: string;
  name: string;
  phase: string;
  status: JobStatus;
  progress: number | null;
  startedAt: Date | null;
  source: "sample" | "image";
  imageJob?: ImageJobResponse;
};
