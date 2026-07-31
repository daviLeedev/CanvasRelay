import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ErrorState } from "./ErrorState";

describe("ErrorState", () => {
  it("runs the retry command without rendering internal exception details", async () => {
    const retry = vi.fn();
    const user = userEvent.setup();

    render(
      <ErrorState
        title="The studio could not open"
        message="Your work is still available."
        onRetry={retry}
      />,
    );

    expect(screen.queryByText(/stack|localhost|exception/iu)).not.toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Try again" }));
    expect(retry).toHaveBeenCalledOnce();
  });
});
