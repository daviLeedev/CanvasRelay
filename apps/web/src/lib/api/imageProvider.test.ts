import { describe, expect, it, vi } from "vitest";

import { fetchImageProvider } from "./imageProvider";

describe("image provider API client", () => {
  it("accepts a normalized live provider status", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            provider: "comfyui",
            mode: "live",
            label: "Local ComfyUI",
            ready: true,
            message: "Connected to the configured local generation workflow.",
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      ),
    );

    await expect(fetchImageProvider()).resolves.toMatchObject({ provider: "comfyui", ready: true });
  });

  it("rejects malformed provider details", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ provider: "unknown", ready: "yes" }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      ),
    );

    await expect(fetchImageProvider()).rejects.toThrow("invalid status");
  });
});
