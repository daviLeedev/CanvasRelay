import { describe, expect, it, vi } from "vitest";

import { createImageJob, fetchImageJob, fetchImageJobs, subscribeImageJob } from "./imageJobs";

const queuedJob = {
  id: "img_demo",
  status: "queued",
  progress: 0,
  prompt: "A structured studio still",
  settings: { aspectRatio: "4:3", style: "editorial", seed: 42, provider: "demo" },
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
    await expect(request).rejects.toThrow("image service");
    await expect(request).rejects.not.toThrow(/private stack|internal endpoint/iu);
  });

  it("loads and validates the persistent job list", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ items: [queuedJob] }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(fetchImageJobs(6, "completed")).resolves.toEqual([queuedJob]);
    expect(String(fetchMock.mock.calls[0]?.[0])).toContain("limit=6&status=completed");
  });

  it("streams typed job updates and closes the subscription", () => {
    const listeners = new Map<string, (event: MessageEvent<string>) => void>();
    const close = vi.fn();
    class FakeEventSource {
      onerror: (() => void) | null = null;
      onopen: (() => void) | null = null;

      addEventListener(name: string, listener: EventListener) {
        listeners.set(name, listener as (event: MessageEvent<string>) => void);
      }

      close = close;
    }
    vi.stubGlobal("EventSource", FakeEventSource);
    const onJob = vi.fn();
    const onDisconnect = vi.fn();
    const onOpen = vi.fn();

    const unsubscribe = subscribeImageJob("img_demo", onJob, onDisconnect, onOpen);
    listeners.get("job")?.(new MessageEvent("job", { data: JSON.stringify(queuedJob) }));
    unsubscribe();

    expect(onJob).toHaveBeenCalledWith(queuedJob);
    expect(onOpen).not.toHaveBeenCalled();
    expect(onDisconnect).not.toHaveBeenCalled();
    expect(close).toHaveBeenCalledOnce();
  });
});
