const defaultApiBaseUrl = "http://localhost:8000";

export function getApiBaseUrl(): string {
  return (process.env.NEXT_PUBLIC_CANVASRELAY_API_URL ?? defaultApiBaseUrl).replace(/\/$/u, "");
}
