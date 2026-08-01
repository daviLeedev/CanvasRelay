import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import { ImageEditWorkspace } from "./ImageEditWorkspace";

const completedEdit = {
  id: "img_edit_complete",
  status: "completed",
  progress: 100,
  phase: "completed",
  currentStep: 8,
  totalSteps: 8,
  progressSource: "provider",
  stalled: false,
  estimatedRemainingSeconds: null,
  prompt: "Use softer studio lighting",
  settings: {
    aspectRatio: "4:3",
    style: "editorial",
    seed: 42,
    provider: "demo",
    operation: "edit",
    hasFaceReference: false,
    sourceJobId: null,
    edit: {
      steps: 8,
      cfg: 1,
      referenceInfluence: 4,
      groundingResolution: 768,
      fitMode: "fit",
      sampler: "euler",
      scheduler: "simple",
      loras: [],
    },
  },
  createdAt: "2026-08-01T00:00:00Z",
  startedAt: "2026-08-01T00:00:01Z",
  completedAt: "2026-08-01T00:00:05Z",
  result: {
    url: "/api/v1/image-jobs/img_edit_complete/result",
    thumbnailUrl: "/api/v1/image-jobs/img_edit_complete/thumbnail",
    mimeType: "image/png",
    width: 1152,
    height: 864,
    sizeBytes: 4096,
    sha256: "a".repeat(64),
    available: true,
  },
  error: null,
} as const;

function renderWorkspace() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  function Wrapper({ children }: Readonly<{ children: ReactNode }>) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  }
  return render(<ImageEditWorkspace />, { wrapper: Wrapper });
}

describe("ImageEditWorkspace", () => {
  it("offers comparison, zoom, download, and completion feedback", async () => {
    vi.stubGlobal("fetch", vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/health")) {
        return new Response(JSON.stringify({
          status: "ok", service: "canvasrelay-api", version: "0.1.0",
          demoMode: true, timestamp: "2026-08-01T00:00:00Z",
        }), { status: 200, headers: { "Content-Type": "application/json" } });
      }
      if (url.includes("/providers/image-edit/options")) {
        return new Response(JSON.stringify({
          samplers: ["euler"], schedulers: ["simple"], loras: [],
          defaults: { steps: 8, cfg: 1, sampler: "euler", scheduler: "simple" },
        }), { status: 200, headers: { "Content-Type": "application/json" } });
      }
      if (url.includes("/providers/image-edit")) {
        return new Response(JSON.stringify({
          provider: "demo", mode: "demo", label: "Deterministic demo",
          ready: true, message: "Ready without a GPU or model files.",
        }), { status: 200, headers: { "Content-Type": "application/json" } });
      }
      if (url.includes("/image-jobs?")) {
        return new Response(JSON.stringify({ items: [completedEdit] }), {
          status: 200, headers: { "Content-Type": "application/json" },
        });
      }
      if (url.endsWith("/image-jobs/img_edit_complete")) {
        return new Response(JSON.stringify(completedEdit), {
          status: 200, headers: { "Content-Type": "application/json" },
        });
      }
      return new Response(null, { status: 404 });
    }));
    const user = userEvent.setup();

    renderWorkspace();

    const compareButton = await screen.findByRole("button", { name: "Compare source and result" });
    expect(screen.queryByRole("slider", { name: "Comparison position" })).not.toBeInTheDocument();
    await user.click(compareButton);
    expect(screen.getByRole("slider", { name: "Comparison position" })).toHaveValue("50");
    expect(screen.getByRole("img", { name: "Edit source comparison" })).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Zoom in" }));
    expect(screen.getByRole("link", { name: "Download result" })).toHaveAttribute(
      "href",
      "http://localhost:8000/api/v1/image-jobs/img_edit_complete/result",
    );
    expect(await screen.findByText("Image edit completed.")).toBeInTheDocument();
  });
});
