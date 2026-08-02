import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeAll, describe, expect, it, vi } from "vitest";

import type { ImageJobResponse } from "@/lib/api/imageJobs";

import { ImageEditPanel } from "./ImageEditPanel";

const baseProps = {
  job: null,
  sourceJob: null,
  sourceJobPreview: null,
  options: {
    samplers: ["euler", "dpmpp_2m"],
    schedulers: ["simple", "karras"],
    loras: [{ id: "demo-detail", label: "Detail enhancer" }],
    defaults: { steps: 8, cfg: 1, sampler: "euler", scheduler: "simple" },
  },
  isBusy: false,
  isSubmitting: false,
  isCanceling: false,
  hasError: false,
  canRetry: false,
  provider: {
    provider: "comfyui",
    mode: "live",
    label: "Local ComfyUI",
    ready: true,
    message: "Connected to the configured local image edit workflow.",
  } as const,
  providerStatusUnavailable: false,
  onSourceJobChange: vi.fn(),
  onSourcePreview: vi.fn(),
  onSubmit: vi.fn(async () => undefined),
  onCancel: vi.fn(async () => undefined),
  onRetry: vi.fn(async () => undefined),
};

const restoredEditJob: ImageJobResponse = {
  id: "img_saved_edit",
  status: "completed",
  progress: 100,
  phase: "completed",
  currentStep: 11,
  totalSteps: 11,
  progressSource: "provider",
  stalled: false,
  estimatedRemainingSeconds: null,
  prompt: "Restore the saved studio lighting settings",
  settings: {
    aspectRatio: "3:4",
    style: "product",
    seed: 987,
    provider: "comfyui",
    operation: "edit",
    hasFaceReference: true,
    sourceJobId: null,
    edit: {
      steps: 11,
      cfg: 2.1,
      referenceInfluence: 6.2,
      groundingResolution: 1024,
      fitMode: "crop",
      sampler: "dpmpp_2m",
      scheduler: "karras",
      loras: [],
    },
  },
  createdAt: "2026-08-01T00:00:00Z",
  startedAt: "2026-08-01T00:00:01Z",
  completedAt: "2026-08-01T00:00:05Z",
  result: null,
  error: null,
};

beforeAll(() => {
  vi.stubGlobal("URL", {
    ...URL,
    createObjectURL: vi.fn(() => "blob:preview"),
    revokeObjectURL: vi.fn(),
  });
});

describe("ImageEditPanel", () => {
  it("requires a source and accepts an optional face reference", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn(async () => undefined);
    render(<ImageEditPanel {...baseProps} onSubmit={onSubmit} />);

    await user.type(screen.getByLabelText("Edit prompt"), "Replace the background with a studio wall");
    expect(screen.getByRole("button", { name: "Generate edit" })).toBeDisabled();

    const source = new File(["source"], "source.png", { type: "image/png" });
    const face = new File(["face"], "face.webp", { type: "image/webp" });
    await user.upload(screen.getByLabelText(/Source image/iu), source);
    await user.upload(screen.getByLabelText(/Identity reference/iu), face);
    const submit = screen.getByRole("button", { name: "Generate edit" });
    await waitFor(() => expect(submit).toBeEnabled());
    await user.click(submit);

    await waitFor(() =>
      expect(onSubmit).toHaveBeenCalledWith(
        expect.objectContaining({
          prompt: "Replace the background with a studio wall",
          source,
          faceReference: face,
          aspectRatio: "4:3",
          style: "editorial",
        }),
      ),
    );
  });

  it("submits without a face reference", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn(async () => undefined);
    render(<ImageEditPanel {...baseProps} onSubmit={onSubmit} />);
    const source = new File(["source"], "source.jpg", { type: "image/jpeg" });

    await user.upload(screen.getByLabelText(/Source image/iu), source);
    await user.type(screen.getByLabelText("Edit prompt"), "Use softer light");
    const submit = screen.getByRole("button", { name: "Generate edit" });
    await waitFor(() => expect(submit).toBeEnabled());
    await user.click(submit);

    await waitFor(() =>
      expect(onSubmit).toHaveBeenCalledWith(
        expect.not.objectContaining({ faceReference: expect.anything() }),
      ),
    );
  });

  it("submits advanced controls and ordered LoRA weights", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn(async () => undefined);
    render(<ImageEditPanel {...baseProps} onSubmit={onSubmit} />);
    await user.upload(
      screen.getByLabelText(/Source image/iu),
      new File(["source"], "source.png", { type: "image/png" }),
    );
    await user.type(screen.getByLabelText("Edit prompt"), "Refine the lighting");
    await user.click(screen.getByText("Advanced settings"));
    await user.selectOptions(screen.getByLabelText("Sampler"), "dpmpp_2m");
    await user.selectOptions(screen.getByLabelText("Scheduler"), "karras");
    await user.selectOptions(screen.getByLabelText("Add LoRA"), "demo-detail");
    await user.clear(screen.getByLabelText("demo-detail model weight"));
    await user.type(screen.getByLabelText("demo-detail model weight"), "0.7");
    await user.click(screen.getByRole("button", { name: "Generate edit" }));

    await waitFor(() => expect(onSubmit).toHaveBeenCalledWith(expect.objectContaining({
      sampler: "dpmpp_2m",
      scheduler: "karras",
      loras: [{ id: "demo-detail", modelWeight: 0.7, clipWeight: 1 }],
    })));
  });

  it("restores a selected edit job's persisted settings into the form", async () => {
    const user = userEvent.setup();
    render(<ImageEditPanel {...baseProps} job={restoredEditJob} />);

    expect(screen.getByLabelText("Edit prompt")).toHaveValue(restoredEditJob.prompt);
    expect(screen.getByLabelText("Aspect ratio")).toHaveValue("3:4");
    expect(screen.getByLabelText("Style")).toHaveValue("product");
    expect(screen.getByLabelText("Seed (optional)")).toHaveValue(987);

    await user.click(screen.getByText("Advanced settings"));

    expect(screen.getByLabelText("Steps")).toHaveValue(11);
    expect(screen.getByLabelText("CFG")).toHaveValue(2.1);
    expect(screen.getByLabelText("Sampler")).toHaveValue("dpmpp_2m");
    expect(screen.getByLabelText("Scheduler")).toHaveValue("karras");
  });
});
