import { describe, expect, it } from "vitest";

import { createDemoJobs } from "./demoJobs";

describe("createDemoJobs", () => {
  const epoch = Date.parse("2026-08-01T00:00:00Z");

  it("starts with one completed, one running, and one queued job", () => {
    const jobs = createDemoJobs(0, epoch);

    expect(jobs.map((job) => job.status)).toEqual(["completed", "running", "queued"]);
    expect(jobs.map((job) => job.progress)).toEqual([100, 37, 0]);
  });

  it("moves each job through the same queued, running, and completed rules", () => {
    const afterFourSeconds = createDemoJobs(4_000, epoch);
    const afterThirteenSeconds = createDemoJobs(13_000, epoch);

    expect(afterFourSeconds[2]?.status).toBe("running");
    expect(afterFourSeconds[2]?.progress).toBeGreaterThan(0);
    expect(afterThirteenSeconds.every((job) => job.status === "completed")).toBe(true);
    expect(afterThirteenSeconds.every((job) => job.progress === 100)).toBe(true);
  });

  it("only assigns a start time after a queued job begins running", () => {
    expect(createDemoJobs(0, epoch)[2]?.startedAt).toBeNull();
    expect(createDemoJobs(4_000, epoch)[2]?.startedAt).toBeInstanceOf(Date);
  });
});
