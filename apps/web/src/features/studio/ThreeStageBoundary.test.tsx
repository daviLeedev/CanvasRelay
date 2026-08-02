import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { createDemoJobs } from "./demoJobs";
import { ThreeStageBoundary } from "./ThreeStageBoundary";

function BrokenStage(): never {
  throw new Error("webgl implementation detail");
}

describe("ThreeStageBoundary", () => {
  it("keeps the 2D jobs usable and offers an explicit fallback command", async () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    const fallback = vi.fn();
    const user = userEvent.setup();
    const jobs = createDemoJobs(0, Date.parse("2026-08-01T00:00:00Z"));

    render(
      <ThreeStageBoundary
        jobs={jobs}
        selectedId={jobs[1]?.id ?? ""}
        onSelect={() => undefined}
        onFallback={fallback}
      >
        <BrokenStage />
      </ThreeStageBoundary>,
    );

    expect(screen.getByText("3D view is unavailable")).toBeInTheDocument();
    expect(screen.getByTestId("stage-2d")).toBeInTheDocument();
    expect(screen.queryByText("webgl implementation detail")).not.toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Use 2D view" }));
    expect(fallback).toHaveBeenCalledOnce();
  });
});
