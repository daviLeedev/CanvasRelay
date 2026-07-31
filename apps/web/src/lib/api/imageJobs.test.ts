import { describe, expect, it, vi } from "vitest";

import { createImageJob, fetchImageJob } from "./imageJobs";

const queuedJob = {
  id: "img_demo",
  status: "queued",
  progress: 0,
  prompt: "A structured studio still",
  settings: { aspectRatio: "4:3", style: "editorial", seed: 42 },
  createdAt: "2026-08-01T00:00:00Z",
  startedAt: null,
  completedAt: null,
  result: null,
  error: null,
} as const;

describe("image job API client", () => {
  it("submits the generated contract payload", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(queuedJob), { status: 201, headers: { "Content-Type": "application/json" } }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const job = await createImageJob({
      prompt: "A structured studio still",
      aspectRatio: "4:3",
      style: "editorial",
      seed: 42,
    });

    expect(job).toEqual(queuedJob);
    expect(fetchMock).toHaveBeenCalledOnce();
    expect(fetchMock.mock.calls[0]?.[1]).toMatchObject({ method: "POST" });
  });

  it("rejects null and malformed job states", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ ...queuedJob, status: "mystery" }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );

    await expect(fetchImageJob("img_demo")).rejects.toThrow("invalid response");
  });

  it("does not surface raw server errors", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ detail: "private stack and internal endpoint" }), {
          status: 500,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );

    const request = fetchImageJob("img_demo");
    await expect(request).rejects.toThrow("demo image service");
    await expect(request).rejects.not.toThrow(/private stack|internal endpoint/iu);
  });
});
