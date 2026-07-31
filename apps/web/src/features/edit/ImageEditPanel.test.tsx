import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeAll, describe, expect, it, vi } from "vitest";

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
});
