import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import type { ImageJobResponse } from "@/lib/api/imageJobs";

import { ImageGenerationPanel } from "./ImageGenerationPanel";

const baseProps = {
  job: null,
  isBusy: false,
  isSubmitting: false,
  isCanceling: false,
  hasError: false,
  canRetry: false,
  provider: {
    provider: "demo",
    mode: "demo",
    label: "Deterministic demo",
    ready: true,
    message: "Ready without a GPU or model files.",
  } as const,
  providerStatusUnavailable: false,
  options: {
    samplers: ["euler", "dpmpp_2m"],
    schedulers: ["beta", "simple"],
    loras: [{ id: "demo-detail", label: "Detail enhancer" }],
    defaults: { steps: 8, cfg: 1, shift: 5, sampler: "euler", scheduler: "beta" },
  },
  onSubmit: vi.fn(async () => undefined),
  onCancel: vi.fn(async () => undefined),
  onRetry: vi.fn(async () => undefined),
};

const completedJob: ImageJobResponse = {
  id: "img_complete",
  status: "completed",
  progress: 100,
  phase: "completed",
  currentStep: 8,
  totalSteps: 8,
  progressSource: "provider",
  stalled: false,
  estimatedRemainingSeconds: null,
  prompt: "A structured studio still",
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
  completedAt: "2026-08-01T00:00:04Z",
  result: {
    url: "/api/v1/image-jobs/img_complete/result",
    thumbnailUrl: "/api/v1/image-jobs/img_complete/thumbnail",
    mimeType: "image/svg+xml",
    width: 1152,
    height: 864,
    sizeBytes: 4096,
    sha256: "a".repeat(64),
    available: true,
  },
  error: null,
};

describe("ImageGenerationPanel", () => {
  it("submits prompt and generation settings", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn(async () => undefined);
    render(<ImageGenerationPanel {...baseProps} onSubmit={onSubmit} />);

    await user.type(screen.getByLabelText("Prompt"), "A modular drafting desk");
    await user.selectOptions(screen.getByLabelText("Aspect ratio"), "3:4");
    await user.selectOptions(screen.getByLabelText("Style"), "product");
    await user.type(screen.getByLabelText("Seed (optional)"), "81");
    await user.click(screen.getByRole("button", { name: "Generate" }));

    expect(onSubmit).toHaveBeenCalledWith({
      prompt: "A modular drafting desk",
      aspectRatio: "3:4",
      style: "product",
      seed: 81,
      generation: {
        steps: 8,
        cfg: 1,
        shift: 5,
        sampler: "euler",
        scheduler: "beta",
        loras: [],
      },
    });
  });

  it("prevents duplicate submission while a job is active", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn(async () => undefined);
    render(<ImageGenerationPanel {...baseProps} isBusy onSubmit={onSubmit} />);

    await user.type(screen.getByLabelText("Prompt"), "A complete prompt");
    const button = screen.getByRole("button", { name: "Generate" });
    expect(button).toBeDisabled();
    await user.click(button);
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("submits advanced sampler values and a LoRA chain", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn(async () => undefined);
    render(<ImageGenerationPanel {...baseProps} onSubmit={onSubmit} />);

    await user.type(screen.getByLabelText("Prompt"), "A clean material study");
    await user.click(screen.getByText("Advanced settings"));
    await user.clear(screen.getByLabelText("Steps"));
    await user.type(screen.getByLabelText("Steps"), "12");
    await user.selectOptions(screen.getByLabelText("Scheduler"), "simple");
    await user.selectOptions(screen.getByLabelText("Add generation LoRA"), "demo-detail");
    await user.click(screen.getByRole("button", { name: "Generate" }));

    expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({
      generation: expect.objectContaining({
        steps: 12,
        scheduler: "simple",
        loras: [{ id: "demo-detail", modelWeight: 1, clipWeight: 1 }],
      }),
    }));
  });

  it("cancels an active job and renders a completed demo image", async () => {
    const user = userEvent.setup();
    const onCancel = vi.fn(async () => undefined);
    const { rerender } = render(
      <ImageGenerationPanel
        {...baseProps}
        job={{ ...completedJob, status: "running", progress: 54, result: null, completedAt: null }}
        isBusy
        onCancel={onCancel}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(onCancel).toHaveBeenCalledOnce();

    rerender(<ImageGenerationPanel {...baseProps} job={completedJob} />);
    expect(screen.getByAltText(/Deterministic demo result/iu)).toBeInTheDocument();
    expect(screen.getByText("Demo result")).toBeInTheDocument();
  });

  it("offers a safe retry without exposing raw exceptions", async () => {
    const user = userEvent.setup();
    const onRetry = vi.fn(async () => undefined);
    render(<ImageGenerationPanel {...baseProps} hasError canRetry onRetry={onRetry} />);

    expect(screen.getByRole("alert")).toHaveTextContent("The image service could not finish the request");
    expect(screen.queryByText(/stack|internal URL|traceback/iu)).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Retry" }));
    expect(onRetry).toHaveBeenCalledOnce();
  });

  it("shows live ComfyUI status without pretending unknown progress", () => {
    render(
      <ImageGenerationPanel
        {...baseProps}
        provider={{
          provider: "comfyui",
          mode: "live",
          label: "Local ComfyUI",
          ready: true,
          message: "Connected to the configured local generation workflow.",
        }}
        job={{
          ...completedJob,
          status: "running",
          progress: null,
          currentStep: 3,
          stalled: true,
          settings: { ...completedJob.settings, provider: "comfyui" },
          result: null,
          completedAt: null,
        }}
      />,
    );

    expect(screen.getByText("Live")).toBeInTheDocument();
    expect(screen.getByText("Unavailable")).toBeInTheDocument();
    expect(screen.getByText("Step 3 of 8")).toBeInTheDocument();
    expect(screen.getByText(/taking longer than usual/iu)).toBeInTheDocument();
  });
});
