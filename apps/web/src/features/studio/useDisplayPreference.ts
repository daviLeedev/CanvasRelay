"use client";

import { useCallback, useSyncExternalStore } from "react";

import type { DisplayMode } from "./types";

export const DISPLAY_MODE_KEY = "canvasrelay:v1:display-mode";
const preferenceEvent = "canvasrelay:display-mode-change";

function isDisplayMode(value: string | null): value is DisplayMode {
  return value === "2d" || value === "3d";
}

function getSnapshot(): DisplayMode {
  const savedMode = window.localStorage.getItem(DISPLAY_MODE_KEY);
  return isDisplayMode(savedMode) ? savedMode : "2d";
}

function getServerSnapshot(): DisplayMode {
  return "2d";
}

function subscribe(onStoreChange: () => void) {
  const update = () => onStoreChange();
  window.addEventListener("storage", update);
  window.addEventListener(preferenceEvent, update);
  return () => {
    window.removeEventListener("storage", update);
    window.removeEventListener(preferenceEvent, update);
  };
}

export function useDisplayPreference() {
  const mode = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);

  const setMode = useCallback((nextMode: DisplayMode) => {
    window.localStorage.setItem(DISPLAY_MODE_KEY, nextMode);
    window.dispatchEvent(new Event(preferenceEvent));
  }, []);

  return { mode, setMode };
}
