import { act, renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { DISPLAY_MODE_KEY, useDisplayPreference } from "./useDisplayPreference";

describe("useDisplayPreference", () => {
  it("defaults to 2D without persisting job or server data", () => {
    const { result } = renderHook(() => useDisplayPreference());

    expect(result.current.mode).toBe("2d");
    expect(window.localStorage.length).toBe(0);
  });

  it("persists and restores the namespaced display preference", () => {
    const first = renderHook(() => useDisplayPreference());

    act(() => first.result.current.setMode("3d"));
    expect(window.localStorage.getItem(DISPLAY_MODE_KEY)).toBe("3d");
    first.unmount();

    const restored = renderHook(() => useDisplayPreference());
    expect(restored.result.current.mode).toBe("3d");
  });
});
