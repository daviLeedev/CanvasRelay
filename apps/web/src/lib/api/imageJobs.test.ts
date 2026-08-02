import { describe, expect, it, vi } from "vitest";

import {
  createImageEditJob,
  createImageJob,
  deleteImageJobAsset,
  deleteImageJobAssets,
  fetchImageEditOptions,
  fetchImageGenerationOptions,
  fetchImageJob,
  fetchImageJobPage,
  fetchImageJobTags,
  fetchImageJobs,
  subscribeImageJob,
  updateImageJobTags,
} from "./imageJobs";

const queuedJob = {
  id: "img_demo",
  status: "queued",
  progress: 0,
  phase: "queued",
  currentStep: null,
  totalSteps: null,
  progressSource: "inferred",
  stalled: false,
  estimatedRemainingSeconds: null,
  prompt: "A structured studio still",
  tags: [],
  settings: {
    aspectRatio: "4:3",
    style: "editorial",
    seed: 42,
    provider: "demo",
    operation: "generate",
    hasFaceReference: false,
    sourceJobId: null,
    edit: null,
  },
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

  it("submits source and optional face files as multipart form data", async () => {
    const editedJob = {
      ...queuedJob,
      settings: { ...queuedJob.settings, operation: "edit", hasFaceReference: true },
    } as const;
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(editedJob), { status: 201, headers: { "Content-Type": "application/json" } }),
    );
    vi.stubGlobal("fetch", fetchMock);
    const source = new File(["source"], "source.png", { type: "image/png" });
    const faceReference = new File(["face"], "face.png", { type: "image/png" });

    await createImageEditJob({
      prompt: "Change the lighting",
      aspectRatio: "4:3",
      style: "editorial",
      seed: 7,
      source,
      faceReference,
      steps: 8,
      cfg: 1,
      referenceInfluence: 4,
      groundingResolution: 768,
      fitMode: "fit",
      sampler: "euler",
      scheduler: "simple",
      loras: [],
    });

    const init = fetchMock.mock.calls[0]?.[1] as RequestInit;
    expect(init.body).toBeInstanceOf(FormData);
    expect(new Headers(init.headers).has("Content-Type")).toBe(false);
    const body = init.body as FormData;
    expect(body.get("source")).toBe(source);
    expect(body.get("faceReference")).toBe(faceReference);
    expect(body.get("prompt")).toBe("Change the lighting");
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

  it("submits a Library source by job id without uploading it again", async () => {
    const editedJob = {
      ...queuedJob,
      settings: { ...queuedJob.settings, operation: "edit", sourceJobId: "img_source" },
    } as const;
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify(editedJob), { status: 201, headers: { "Content-Type": "application/json" } }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await createImageEditJob({
      prompt: "Use the Library source",
      aspectRatio: "4:3",
      style: "editorial",
      sourceJobId: "img_source",
      steps: 8,
      cfg: 1,
      referenceInfluence: 4,
      groundingResolution: 768,
      fitMode: "fit",
      sampler: "euler",
      scheduler: "simple",
      loras: [],
    });

    const body = fetchMock.mock.calls[0]?.[1]?.body as FormData;
    expect(body.get("sourceJobId")).toBe("img_source");
    expect(body.has("source")).toBe(false);
  });

  it("loads provider-owned edit options", async () => {
    const options = {
      samplers: ["euler"],
      schedulers: ["simple"],
      loras: [{ id: "detail", label: "Detail enhancer" }],
      defaults: { steps: 8, cfg: 1, sampler: "euler", scheduler: "simple" },
    };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(
      new Response(JSON.stringify(options), { status: 200, headers: { "Content-Type": "application/json" } }),
    ));

    await expect(fetchImageEditOptions()).resolves.toEqual(options);
  });

  it("loads provider-owned generation options", async () => {
    const options = {
      samplers: ["euler"],
      schedulers: ["beta"],
      loras: [{ id: "detail", label: "Detail enhancement" }],
      defaults: { steps: 8, cfg: 1, shift: 5, sampler: "euler", scheduler: "beta" },
    };
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(
      new Response(JSON.stringify(options), { status: 200, headers: { "Content-Type": "application/json" } }),
    ));

    await expect(fetchImageGenerationOptions()).resolves.toEqual(options);
  });

  it("loads and validates the persistent job list", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ items: [queuedJob] }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await expect(fetchImageJobs(6, "completed", "generate")).resolves.toEqual([queuedJob]);
    expect(String(fetchMock.mock.calls[0]?.[0])).toContain("limit=6&status=completed&operation=generate");
  });

  it("returns a validated page cursor and deletes an owned Library asset", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ items: [queuedJob], nextCursor: "page-two" }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      )
      .mockResolvedValueOnce(new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(fetchImageJobPage({ limit: 1 })).resolves.toMatchObject({ nextCursor: "page-two" });
    await expect(deleteImageJobAsset("img_demo")).resolves.toBeUndefined();
    expect(fetchMock.mock.calls[1]?.[1]).toMatchObject({ method: "DELETE" });
  });

  it("updates tags, lists tags, and deletes selected assets", async () => {
    const taggedJob = { ...queuedJob, status: "completed", tags: ["review"] };
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response(JSON.stringify(taggedJob), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ tags: ["review"] }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }))
      .mockResolvedValueOnce(new Response(JSON.stringify({ deletedIds: [queuedJob.id] }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }));
    vi.stubGlobal("fetch", fetchMock);

    await expect(updateImageJobTags(queuedJob.id, ["review"])).resolves.toMatchObject({
      tags: ["review"],
    });
    await expect(fetchImageJobTags()).resolves.toEqual(["review"]);
    await expect(deleteImageJobAssets([queuedJob.id])).resolves.toEqual([queuedJob.id]);

    expect(fetchMock.mock.calls[0]?.[1]).toMatchObject({ method: "PATCH" });
    expect(fetchMock.mock.calls[2]?.[1]).toMatchObject({ method: "POST" });
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
