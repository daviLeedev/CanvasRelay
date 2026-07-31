import type { components } from "@canvasrelay/contracts";

import { getApiBaseUrl } from "@/lib/env";

export type ImageJobCreate = components["schemas"]["ImageJobCreate"];
export type ImageJobResponse = components["schemas"]["ImageJobResponse"];

const jobStatuses = new Set<ImageJobResponse["status"]>([
  "queued",
  "running",
  "completed",
  "canceled",
]);
const aspectRatios = new Set<ImageJobResponse["settings"]["aspectRatio"]>(["1:1", "4:3", "3:4", "16:9"]);
const imageStyles = new Set<ImageJobResponse["settings"]["style"]>(["editorial", "product", "concept"]);

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isNullableString(value: unknown): value is string | null {
  return typeof value === "string" || value === null;
}

function parseImageJob(value: unknown): ImageJobResponse {
  if (!isRecord(value) || !isRecord(value.settings)) {
    throw new Error("Invalid image job response.");
  }
  const resultIsValid =
    value.result === null ||
    (isRecord(value.result) &&
      typeof value.result.url === "string" &&
      value.result.mimeType === "image/svg+xml" &&
      typeof value.result.width === "number" &&
      typeof value.result.height === "number");
  const settingsAreValid =
    typeof value.settings.aspectRatio === "string" &&
    aspectRatios.has(value.settings.aspectRatio as ImageJobResponse["settings"]["aspectRatio"]) &&
    typeof value.settings.style === "string" &&
    imageStyles.has(value.settings.style as ImageJobResponse["settings"]["style"]) &&
    typeof value.settings.seed === "number";

  if (
    typeof value.id !== "string" ||
    typeof value.status !== "string" ||
    !jobStatuses.has(value.status as ImageJobResponse["status"]) ||
    typeof value.progress !== "number" ||
    value.progress < 0 ||
    value.progress > 100 ||
    typeof value.prompt !== "string" ||
    typeof value.createdAt !== "string" ||
    !isNullableString(value.startedAt) ||
    !isNullableString(value.completedAt) ||
    !settingsAreValid ||
    !resultIsValid ||
    !(value.error === null || isRecord(value.error))
  ) {
    throw new Error("Invalid image job response.");
  }

  return value as ImageJobResponse;
}

async function requestImageJob(path: string, init?: RequestInit): Promise<ImageJobResponse> {
  const headers = new Headers(init?.headers);
  headers.set("Accept", "application/json");
  if (init?.body) headers.set("Content-Type", "application/json");
  const response = await fetch(`${getApiBaseUrl()}${path}`, {
    ...init,
    headers,
  });

  if (!response.ok) {
    throw new Error("The demo image service could not complete the request.");
  }

  try {
    return parseImageJob(await response.json());
  } catch {
    throw new Error("The demo image service returned an invalid response.");
  }
}

export function createImageJob(input: ImageJobCreate): Promise<ImageJobResponse> {
  return requestImageJob("/api/v1/image-jobs", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function fetchImageJob(jobId: string, signal?: AbortSignal): Promise<ImageJobResponse> {
  return requestImageJob(`/api/v1/image-jobs/${encodeURIComponent(jobId)}`, { signal });
}

export function cancelImageJob(jobId: string): Promise<ImageJobResponse> {
  return requestImageJob(`/api/v1/image-jobs/${encodeURIComponent(jobId)}`, { method: "DELETE" });
}

export function getImageResultUrl(job: ImageJobResponse): string | null {
  const path = job.result?.url;
  if (!path?.startsWith(`/api/v1/image-jobs/${encodeURIComponent(job.id)}/result`)) return null;
  return new URL(path, `${getApiBaseUrl()}/`).toString();
}
