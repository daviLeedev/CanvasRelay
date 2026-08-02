import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { HealthResponse } from "@/lib/api/health";

import { HealthPanel } from "./HealthPanel";

const healthResponse: HealthResponse = {
  status: "ok",
  service: "canvasrelay-api",
  version: "0.1.0",
  demoMode: true,
  timestamp: "2026-07-31T00:00:00Z",
};

function renderPanel() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
    },
  });

  function Wrapper({ children }: Readonly<{ children: ReactNode }>) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  }

  return render(<HealthPanel />, { wrapper: Wrapper });
}

function okResponse(payload: HealthResponse): Response {
  return {
    ok: true,
    json: async () => payload,
  } as Response;
}

describe("HealthPanel", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("shows the loading state while the API request is pending", () => {
    vi.stubGlobal("fetch", vi.fn(() => new Promise<Response>(() => undefined)));

    renderPanel();

    expect(screen.getByText("Checking connection")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Check API connection again" })).toBeDisabled();
  });

  it("shows the generated health contract when the API is online", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(okResponse(healthResponse)));

    renderPanel();

    expect(await screen.findByText("Connected")).toBeInTheDocument();
    expect(screen.getByText("canvasrelay-api - v0.1.0")).toBeInTheDocument();
    expect(screen.getByText("Demo")).toBeInTheDocument();
  });

  it("shows a safe offline state without exposing the raw error", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("internal transport detail")));

    renderPanel();

    expect(await screen.findByText("API unavailable")).toBeInTheDocument();
    expect(screen.queryByText("internal transport detail")).not.toBeInTheDocument();
  });

  it("retries the health request from the status panel", async () => {
    const fetchMock = vi
      .fn()
      .mockRejectedValueOnce(new Error("offline"))
      .mockResolvedValueOnce(okResponse(healthResponse));
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();

    renderPanel();
    expect(await screen.findByText("API unavailable")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Check API connection again" }));

    await waitFor(() => expect(screen.getByText("Connected")).toBeInTheDocument());
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });
});
