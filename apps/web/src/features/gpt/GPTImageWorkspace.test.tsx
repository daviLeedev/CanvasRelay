import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import type { ImageJobResponse } from "@/lib/api/imageJobs";

import { GPTImageWorkspace } from "./GPTImageWorkspace";

const queuedJob: ImageJobResponse = {
  id: "img_gpt_queued",
  status: "queued",
  progress: null,
  phase: "queued",
  currentStep: null,
  totalSteps: null,
  progressSource: "unknown",
  stalled: false,
  estimatedRemainingSeconds: null,
  prompt: "A compact material study",
  tags: [],
  settings: {
    aspectRatio: "1:1",
    style: "editorial",
    seed: 42,
    provider: "openai_oauth",
    operation: "generate",
    hasFaceReference: false,
    sourceJobId: null,
    generation: null,
    edit: null,
    gpt: {
      quality: "auto",
      size: "1024x1024",
      count: 1,
      moderation: "auto",
      reasoningEffort: "none",
      webSearch: false,
    },
  },
  createdAt: "2026-08-02T00:00:00Z",
  startedAt: null,
  completedAt: null,
  result: null,
  assets: [],
  error: null,
};

function renderWorkspace() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  function Wrapper({ children }: Readonly<{ children: ReactNode }>) {
    return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
  }
  return render(<GPTImageWorkspace />, { wrapper: Wrapper });
}

describe("GPTImageWorkspace", () => {
  it("submits a typed owner-connected image request and keeps references out of the result stage", async () => {
    const submissions: FormData[] = [];
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes("/connections/codex")) {
        return new Response(JSON.stringify({
          state: "connected", connected: true, message: "Connected through the local owner login.",
        }), { status: 200, headers: { "Content-Type": "application/json" } });
      }
      if (url.includes("/image-jobs?")) {
        return new Response(JSON.stringify({ items: [] }), {
          status: 200, headers: { "Content-Type": "application/json" },
        });
      }
      if (url.includes("/gpt-image-jobs")) {
        submissions.push(init?.body as FormData);
        return new Response(JSON.stringify(queuedJob), {
          status: 200, headers: { "Content-Type": "application/json" },
        });
      }
      if (url.endsWith("/image-jobs/img_gpt_queued")) {
        return new Response(JSON.stringify(queuedJob), {
          status: 200, headers: { "Content-Type": "application/json" },
        });
      }
      return new Response(null, { status: 404 });
    }));
    const user = userEvent.setup();

    renderWorkspace();

    await user.type(screen.getByLabelText("Prompt"), queuedJob.prompt);
    await user.selectOptions(screen.getByLabelText("Quality"), "high");
    expect(screen.getByText(/Reference images stay in the controls/iu)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Generate image" }));

    await waitFor(() => expect(submissions).toHaveLength(1));
    expect(submissions[0]?.get("prompt")).toBe(queuedJob.prompt);
    expect(submissions[0]?.get("quality")).toBe("high");
    expect(screen.getAllByText("Queued")).toHaveLength(2);
  });
});
