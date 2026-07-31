import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeAll, describe, expect, it, vi } from "vitest";

import { ImageEditPanel } from "./ImageEditPanel";

const baseProps = {
  job: null,
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
});
