import type { components } from "@canvasrelay/contracts";

import { getApiBaseUrl } from "@/lib/env";

export type HealthResponse = components["schemas"]["HealthResponse"];

export async function fetchHealth(signal?: AbortSignal): Promise<HealthResponse> {
  const response = await fetch(`${getApiBaseUrl()}/api/v1/health`, {
    method: "GET",
    headers: { Accept: "application/json" },
    signal,
  });

  if (!response.ok) {
    throw new Error("CanvasRelay API is unavailable.");
  }

  return (await response.json()) as HealthResponse;
}
