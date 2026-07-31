import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import type { ImageJobResponse } from "@/lib/api/imageJobs";

import { useImageGenerationJob } from "./useImageGenerationJob";

const queued: ImageJobResponse = {
  id: "img_poll",
  status: "queued",
  progress: 0,
  phase: "queued",
  currentStep: null,
  totalSteps: null,
  progressSource: "inferred",
  stalled: false,
  estimatedRemainingSeconds: null,
  prompt: "A relay test image",
  settings: {
    aspectRatio: "1:1",
    style: "concept",
    seed: 9,
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
};

const running: ImageJobResponse = {
  ...queued,
  status: "running",
  progress: 48,
  startedAt: "2026-08-01T00:00:01Z",
};

const completed: ImageJobResponse = {
  ...running,
  status: "completed",
  progress: 100,
  completedAt: "2026-08-01T00:00:04Z",
  result: {
    url: "/api/v1/image-jobs/img_poll/result",
    mimeType: "image/svg+xml",
    width: 1024,
    height: 1024,
  },
};

function response(body: ImageJobResponse, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

function emptyListResponse() {
  return new Response(JSON.stringify({ items: [] }), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

function wrapper() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return function QueryWrapper({ children }: Readonly<{ children: ReactNode }>) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  };
}

describe("useImageGenerationJob", () => {
  it("polls queued work through running to completed", async () => {
    let getCount = 0;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        if (String(input).includes("image-jobs?")) return emptyListResponse();
        if (init?.method === "POST") return response(queued, 201);
        getCount += 1;
        return response(getCount === 1 ? running : completed);
      }),
    );
    const { result } = renderHook(() => useImageGenerationJob(), { wrapper: wrapper() });

    await act(async () => {
      await result.current.submit({ prompt: queued.prompt, aspectRatio: "1:1", style: "concept", seed: 9 });
    });

    await waitFor(() => expect(result.current.job?.status).toBe("running"));
    await waitFor(() => expect(result.current.job?.status).toBe("completed"), { timeout: 2_000 });
    expect(getCount).toBeGreaterThanOrEqual(2);
  });

  it("cancels the active server job", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        if (String(input).includes("image-jobs?")) return emptyListResponse();
        if (init?.method === "POST") return response(queued, 201);
        if (init?.method === "DELETE") return response({ ...running, status: "canceled", progress: 0 });
        return response(running);
      }),
    );
    const { result } = renderHook(() => useImageGenerationJob(), { wrapper: wrapper() });

    await act(async () => {
      await result.current.submit({ prompt: queued.prompt, aspectRatio: "1:1", style: "concept" });
    });
    await waitFor(() => expect(result.current.job?.status).toBe("running"));
    await act(async () => {
      await result.current.cancel();
    });

    await waitFor(() => expect(result.current.job?.status).toBe("canceled"));
  });

  it("retries the last request after a safe failure", async () => {
    let postCount = 0;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
        if (String(input).includes("image-jobs?")) return emptyListResponse();
        if (init?.method === "POST") {
          postCount += 1;
          return postCount === 1 ? new Response("private failure", { status: 503 }) : response(queued, 201);
        }
        return response(queued);
      }),
    );
    const { result } = renderHook(() => useImageGenerationJob(), { wrapper: wrapper() });

    await act(async () => {
      await result.current.submit({ prompt: queued.prompt, aspectRatio: "1:1", style: "concept" });
    });
    expect(result.current.hasError).toBe(true);

    await act(async () => {
      await result.current.retry();
    });
    await waitFor(() => expect(result.current.job?.status).toBe("queued"));
    expect(postCount).toBe(2);
  });
});
