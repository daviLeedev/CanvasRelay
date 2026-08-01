import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { JobCenterWorkspace } from "./JobCenterWorkspace";

const navigation = vi.hoisted(() => ({
  replace: vi.fn(),
  search: new URLSearchParams(),
}));
vi.mock("next/navigation", () => ({
  useRouter: () => navigation,
  useSearchParams: () => navigation.search,
}));

const failedJob = {
  id: "img_failed",
  status: "failed",
  progress: null,
  phase: "failed",
  currentStep: null,
  totalSteps: null,
  progressSource: "provider",
  stalled: false,
  estimatedRemainingSeconds: null,
  prompt: "A saved retryable operation",
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
  startedAt: "2026-08-01T00:00:01Z",
  completedAt: "2026-08-01T00:00:03Z",
  result: null,
  error: {
    code: "provider_restarted",
    message: "The inference provider restarted before this job completed.",
    action: "Your settings were preserved. Retry the job when the provider is ready.",
    retryable: true,
  },
} as const;

function renderJobs() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  function Wrapper({ children }: Readonly<{ children: ReactNode }>) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  }
  return render(<JobCenterWorkspace />, { wrapper: Wrapper });
}

describe("JobCenterWorkspace", () => {
  beforeEach(() => {
    navigation.replace.mockReset();
    navigation.search = new URLSearchParams("job=img_failed");
  });

  it("restores a selected durable job and retries with the saved settings", async () => {
    const retriedJob = { ...failedJob, id: "img_retried", status: "queued", phase: "queued", progress: 0, error: null };
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes("/image-jobs?") && !init?.method) {
        return new Response(JSON.stringify({ items: [failedJob], nextCursor: null }), {
          status: 200, headers: { "Content-Type": "application/json" },
        });
      }
      if (url.endsWith("/image-jobs/img_failed") && !init?.method) {
        return new Response(JSON.stringify(failedJob), {
          status: 200, headers: { "Content-Type": "application/json" },
        });
      }
      if (url.endsWith("/image-jobs/img_failed/retry") && init?.method === "POST") {
        return new Response(JSON.stringify(retriedJob), {
          status: 201, headers: { "Content-Type": "application/json" },
        });
      }
      return new Response(null, { status: 404 });
    });
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();

    renderJobs();
    expect((await screen.findAllByText(failedJob.prompt)).length).toBeGreaterThan(0);
    expect(screen.getByText(failedJob.error.action)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Retry" }));

    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/api/v1/image-jobs/img_failed/retry",
      expect.objectContaining({ method: "POST" }),
    );
    expect(navigation.replace).toHaveBeenCalledWith("/jobs?job=img_retried", { scroll: false });
  });
});
