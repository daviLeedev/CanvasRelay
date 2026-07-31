import type { components } from "@canvasrelay/contracts";

import { getApiBaseUrl } from "@/lib/env";

export type ImageJobCreate = components["schemas"]["ImageJobCreate"];
export type ImageJobResponse = components["schemas"]["ImageJobResponse"];
export type ImageJobListResponse = components["schemas"]["ImageJobListResponse"];
export type ImageEditJobCreate = Omit<ImageJobCreate, "prompt"> & {
  prompt: string;
  source: File;
  faceReference?: File;
};

const jobStatuses = new Set<ImageJobResponse["status"]>([
  "queued",
  "running",
  "completed",
  "failed",
  "canceled",
]);
const aspectRatios = new Set<ImageJobResponse["settings"]["aspectRatio"]>(["1:1", "4:3", "3:4", "16:9"]);
const imageStyles = new Set<ImageJobResponse["settings"]["style"]>(["editorial", "product", "concept"]);
const imageProviders = new Set<ImageJobResponse["settings"]["provider"]>(["demo", "comfyui"]);
const imageOperations = new Set<ImageJobResponse["settings"]["operation"]>(["generate", "edit"]);
const imageMimeTypes = new Set<NonNullable<ImageJobResponse["result"]>["mimeType"]>([
  "image/svg+xml",
  "image/png",
  "image/jpeg",
  "image/webp",
]);

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isNullableString(value: unknown): value is string | null {
  return typeof value === "string" || value === null;
}

export function parseImageJob(value: unknown): ImageJobResponse {
  if (!isRecord(value) || !isRecord(value.settings)) {
    throw new Error("Invalid image job response.");
  }
  const resultIsValid =
    value.result === null ||
    (isRecord(value.result) &&
      typeof value.result.url === "string" &&
      typeof value.result.mimeType === "string" &&
      imageMimeTypes.has(value.result.mimeType as NonNullable<ImageJobResponse["result"]>["mimeType"]) &&
      typeof value.result.width === "number" &&
      typeof value.result.height === "number");
  const settingsAreValid =
    typeof value.settings.aspectRatio === "string" &&
    aspectRatios.has(value.settings.aspectRatio as ImageJobResponse["settings"]["aspectRatio"]) &&
    typeof value.settings.style === "string" &&
    imageStyles.has(value.settings.style as ImageJobResponse["settings"]["style"]) &&
    typeof value.settings.seed === "number" &&
    typeof value.settings.provider === "string" &&
    imageProviders.has(value.settings.provider as ImageJobResponse["settings"]["provider"]) &&
    typeof value.settings.operation === "string" &&
    imageOperations.has(value.settings.operation as ImageJobResponse["settings"]["operation"]) &&
    typeof value.settings.hasFaceReference === "boolean";
  const progressIsValid =
    value.progress === null ||
    (typeof value.progress === "number" && value.progress >= 0 && value.progress <= 100);
  const errorIsValid =
    value.error === null ||
    (isRecord(value.error) &&
      typeof value.error.code === "string" &&
      typeof value.error.message === "string" &&
      typeof value.error.action === "string" &&
      typeof value.error.retryable === "boolean");

  if (
    typeof value.id !== "string" ||
    typeof value.status !== "string" ||
    !jobStatuses.has(value.status as ImageJobResponse["status"]) ||
    !progressIsValid ||
    typeof value.prompt !== "string" ||
    typeof value.createdAt !== "string" ||
    !isNullableString(value.startedAt) ||
    !isNullableString(value.completedAt) ||
    !settingsAreValid ||
    !resultIsValid ||
    !errorIsValid
  ) {
    throw new Error("Invalid image job response.");
  }

  return value as ImageJobResponse;
}

function parseImageJobList(value: unknown): ImageJobListResponse {
  if (!isRecord(value) || !Array.isArray(value.items)) {
    throw new Error("Invalid image job list response.");
  }
  return { items: value.items.map(parseImageJob) };
}

async function requestImageJob(path: string, init?: RequestInit): Promise<ImageJobResponse> {
  const headers = new Headers(init?.headers);
  headers.set("Accept", "application/json");
  if (init?.body && !(init.body instanceof FormData)) headers.set("Content-Type", "application/json");
  const response = await fetch(`${getApiBaseUrl()}${path}`, {
    ...init,
    headers,
  });

  if (!response.ok) {
    throw new Error("The image service could not complete the request.");
  }

  try {
    return parseImageJob(await response.json());
  } catch {
    throw new Error("The image service returned an invalid response.");
  }
}

export function createImageJob(input: ImageJobCreate): Promise<ImageJobResponse> {
  return requestImageJob("/api/v1/image-jobs", {
    method: "POST",
    body: JSON.stringify(input),
  });
}

export function createImageEditJob(input: ImageEditJobCreate): Promise<ImageJobResponse> {
  const form = new FormData();
  form.set("prompt", input.prompt);
  form.set("aspectRatio", input.aspectRatio);
  form.set("style", input.style);
  if (typeof input.seed === "number") form.set("seed", String(input.seed));
  form.set("source", input.source);
  if (input.faceReference) form.set("faceReference", input.faceReference);
  return requestImageJob("/api/v1/image-edit-jobs", { method: "POST", body: form });
}

export function fetchImageJob(jobId: string, signal?: AbortSignal): Promise<ImageJobResponse> {
  return requestImageJob(`/api/v1/image-jobs/${encodeURIComponent(jobId)}`, { signal });
}

export async function fetchImageJobs(
  limit = 24,
  status?: ImageJobResponse["status"],
  operation?: ImageJobResponse["settings"]["operation"],
): Promise<ImageJobResponse[]> {
  const search = new URLSearchParams({ limit: String(limit) });
  if (status) search.set("status", status);
  if (operation) search.set("operation", operation);
  const response = await fetch(`${getApiBaseUrl()}/api/v1/image-jobs?${search.toString()}`, {
    headers: { Accept: "application/json" },
  });
  if (!response.ok) throw new Error("The image library could not be loaded.");
  try {
    return parseImageJobList(await response.json()).items;
  } catch {
    throw new Error("The image library returned an invalid response.");
  }
}

export function subscribeImageJob(
  jobId: string,
  onJob: (job: ImageJobResponse) => void,
  onDisconnect: () => void,
  onOpen: () => void = () => undefined,
): () => void {
  const source = new EventSource(
    `${getApiBaseUrl()}/api/v1/image-jobs/${encodeURIComponent(jobId)}/events`,
  );
  source.addEventListener("job", (event) => {
    try {
      onJob(parseImageJob(JSON.parse(event.data) as unknown));
    } catch {
      onDisconnect();
      source.close();
    }
  });
  source.onerror = () => {
    onDisconnect();
    source.close();
  };
  source.onopen = onOpen;
  return () => source.close();
}

export function cancelImageJob(jobId: string): Promise<ImageJobResponse> {
  return requestImageJob(`/api/v1/image-jobs/${encodeURIComponent(jobId)}`, { method: "DELETE" });
}

export function getImageResultUrl(job: ImageJobResponse): string | null {
  const path = job.result?.url;
  if (!path?.startsWith(`/api/v1/image-jobs/${encodeURIComponent(job.id)}/result`)) return null;
  return new URL(path, `${getApiBaseUrl()}/`).toString();
}
