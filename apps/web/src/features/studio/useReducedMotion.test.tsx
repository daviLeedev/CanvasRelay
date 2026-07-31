import { act, renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { useReducedMotion } from "./useReducedMotion";

describe("useReducedMotion", () => {
  it("tracks reduced-motion preference changes and removes its listener", () => {
    let matches = true;
    let changeHandler: (() => void) | undefined;
    const removeEventListener = vi.fn();

    vi.spyOn(window, "matchMedia").mockReturnValue({
      get matches() {
        return matches;
      },
      media: "(prefers-reduced-motion: reduce)",
      onchange: null,
      addEventListener: (_event: string, listener: EventListenerOrEventListenerObject) => {
        changeHandler = listener as () => void;
      },
      removeEventListener,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    });

    const { result, unmount } = renderHook(() => useReducedMotion());
    expect(result.current).toBe(true);

    act(() => {
      matches = false;
      changeHandler?.();
    });
    expect(result.current).toBe(false);

    unmount();
    expect(removeEventListener).toHaveBeenCalledWith("change", expect.any(Function));
  });
});
