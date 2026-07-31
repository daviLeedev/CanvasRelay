import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import { DISPLAY_MODE_KEY } from "./useDisplayPreference";

vi.mock("./StudioStage3D", () => ({
  StudioStage3D: () => <div data-testid="stage-3d-mock">3D workspace</div>,
}));

import { StudioWorkspace } from "./StudioWorkspace";

function renderWorkspace() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  function Wrapper({ children }: Readonly<{ children: ReactNode }>) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  }
  return render(<StudioWorkspace />, { wrapper: Wrapper });
}

describe("StudioWorkspace", () => {
  it("switches between the complete 2D stage and lazily loaded 3D stage", async () => {
    vi.stubGlobal("fetch", vi.fn(() => new Promise<Response>(() => undefined)));
    const user = userEvent.setup();

    renderWorkspace();
    expect(screen.getByTestId("stage-2d")).toBeInTheDocument();
    expect(screen.queryByTestId("stage-3d-mock")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "3D" }));
    expect(await screen.findByTestId("stage-3d-mock")).toBeInTheDocument();
    expect(screen.queryByTestId("stage-2d")).not.toBeInTheDocument();
  });

  it("restores the saved 3D preference", async () => {
    window.localStorage.setItem(DISPLAY_MODE_KEY, "3d");
    vi.stubGlobal("fetch", vi.fn(() => new Promise<Response>(() => undefined)));

    renderWorkspace();
    expect(await screen.findByTestId("stage-3d-mock")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "3D" })).toHaveAttribute("aria-pressed", "true");
  });

  it("restarts the deterministic demo and restores its three initial states", async () => {
    vi.stubGlobal("fetch", vi.fn(() => new Promise<Response>(() => undefined)));
    const user = userEvent.setup();

    renderWorkspace();
    await user.click(screen.getByRole("button", { name: "Demo restart" }));

    expect(screen.getByText("1 queued")).toBeInTheDocument();
    expect(screen.getByText("1 running")).toBeInTheDocument();
    expect(screen.getByText("1 complete")).toBeInTheDocument();
  });
});
