import { act, renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { usePageVisibility } from "./usePageVisibility";

describe("usePageVisibility", () => {
  it("pauses work when the document is hidden and removes its listener", () => {
    let visibilityState: DocumentVisibilityState = "visible";
    vi.spyOn(document, "visibilityState", "get").mockImplementation(() => visibilityState);
    const removeEventListener = vi.spyOn(document, "removeEventListener");

    const { result, unmount } = renderHook(() => usePageVisibility());
    expect(result.current).toBe(true);

    act(() => {
      visibilityState = "hidden";
      document.dispatchEvent(new Event("visibilitychange"));
    });
    expect(result.current).toBe(false);

    unmount();
    expect(removeEventListener).toHaveBeenCalledWith("visibilitychange", expect.any(Function));
  });
});
