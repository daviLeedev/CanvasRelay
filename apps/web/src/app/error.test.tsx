import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import RouteError from "./error";

describe("RouteError", () => {
  it("offers a route retry without exposing the raw exception", async () => {
    const reset = vi.fn();
    const user = userEvent.setup();

    render(<RouteError error={new Error("private stack and internal URL")} reset={reset} />);

    expect(screen.getByText("The studio could not open")).toBeInTheDocument();
    expect(screen.queryByText(/private stack|internal URL/iu)).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Try again" }));
    expect(reset).toHaveBeenCalledOnce();
  });
});
