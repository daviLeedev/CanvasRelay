import type { components } from "@canvasrelay/contracts";

import { getApiBaseUrl } from "@/lib/env";

export type ImageProviderResponse = components["schemas"]["ImageProviderResponse"];

function isImageProviderResponse(value: unknown): value is ImageProviderResponse {
  if (typeof value !== "object" || value === null || Array.isArray(value)) return false;
  const record = value as Record<string, unknown>;
  return (
    (record.provider === "demo" || record.provider === "comfyui") &&
    (record.mode === "demo" || record.mode === "live") &&
    typeof record.label === "string" &&
    typeof record.ready === "boolean" &&
    typeof record.message === "string"
  );
}

export async function fetchImageProvider(signal?: AbortSignal): Promise<ImageProviderResponse> {
  const response = await fetch(`${getApiBaseUrl()}/api/v1/providers/image`, {
    headers: { Accept: "application/json" },
    signal,
  });
  if (!response.ok) throw new Error("The image provider status is unavailable.");
  const payload: unknown = await response.json();
  if (!isImageProviderResponse(payload)) throw new Error("The image provider returned an invalid status.");
  return payload;
}
