"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { createDemoJobs } from "./demoJobs";

const HYDRATION_EPOCH_MS = Date.parse("2026-08-01T00:00:00Z");

export function useDemoJobs() {
  const [epochMs, setEpochMs] = useState(HYDRATION_EPOCH_MS);
  const [nowMs, setNowMs] = useState(HYDRATION_EPOCH_MS);

  useEffect(() => {
    const startTimerId = window.setTimeout(() => {
      const startMs = Date.now();
      setEpochMs(startMs);
      setNowMs(startMs);
    }, 0);
    const intervalId = window.setInterval(() => setNowMs(Date.now()), 250);
    return () => {
      window.clearTimeout(startTimerId);
      window.clearInterval(intervalId);
    };
  }, []);

  const restart = useCallback(() => {
    const nextEpoch = Date.now();
    setEpochMs(nextEpoch);
    setNowMs(nextEpoch);
  }, []);

  const jobs = useMemo(() => createDemoJobs(nowMs - epochMs, epochMs), [epochMs, nowMs]);

  return { jobs, restart };
}
