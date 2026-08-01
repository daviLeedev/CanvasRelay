"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  cancelImageJob,
  createImageJob,
  fetchImageJob,
  fetchImageJobs,
  retryImageJob,
  subscribeImageJob,
  type ImageJobCreate,
  type ImageJobResponse,
} from "@/lib/api/imageJobs";

const POLL_INTERVAL_MS = 1_000;

export function useImageGenerationJob() {
  const queryClient = useQueryClient();
  const submittingRef = useRef(false);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [lastRequest, setLastRequest] = useState<ImageJobCreate | null>(null);
  const [streamJobId, setStreamJobId] = useState<string | null>(null);

  const recentQuery = useQuery({
    queryKey: ["image-jobs", "recent", "generate"],
    queryFn: () => fetchImageJobs(24, undefined, "generate"),
    placeholderData: (previousData) => previousData,
  });

  const restoredId = useMemo(() => {
    const recent = recentQuery.data;
    if (!recent?.length) return null;
    return (recent.find((item) => item.status === "queued" || item.status === "running") ?? recent[0]).id;
  }, [recentQuery.data]);
  const selectedId = activeId ?? restoredId;

  const jobQuery = useQuery({
    queryKey: ["image-job", selectedId],
    queryFn: ({ signal }) => fetchImageJob(selectedId ?? "", signal),
    enabled: selectedId !== null,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      const isActive = status === "queued" || status === "running";
      return isActive && streamJobId !== selectedId ? POLL_INTERVAL_MS : false;
    },
  });

  const createMutation = useMutation({
    mutationFn: createImageJob,
    onSuccess: (job) => {
      queryClient.setQueryData(["image-job", job.id], job);
      queryClient.setQueryData<ImageJobResponse[]>(["image-jobs", "recent", "generate"], (current = []) => [
        job,
        ...current.filter((item) => item.id !== job.id),
      ]);
      setActiveId(job.id);
    },
  });

  const cancelMutation = useMutation({
    mutationFn: cancelImageJob,
    onMutate: async (jobId) => {
      await queryClient.cancelQueries({ queryKey: ["image-job", jobId] });
    },
    onSuccess: (job) => {
      queryClient.setQueryData(["image-job", job.id], job);
      void queryClient.invalidateQueries({ queryKey: ["image-jobs", "recent", "generate"] });
    },
  });

  const retryMutation = useMutation({
    mutationFn: retryImageJob,
    onSuccess: (job) => {
      queryClient.setQueryData(["image-job", job.id], job);
      queryClient.setQueryData<ImageJobResponse[]>(["image-jobs", "recent", "generate"], (current = []) => [
        job,
        ...current.filter((item) => item.id !== job.id),
      ]);
      setActiveId(job.id);
    },
  });

  const recentJob = useMemo(
    () => recentQuery.data?.find((item) => item.id === selectedId) ?? null,
    [recentQuery.data, selectedId],
  );
  const job = (jobQuery.data ?? recentJob ?? createMutation.data ?? null) as ImageJobResponse | null;
  const active = job?.status === "queued" || job?.status === "running";
  const isBusy = active || createMutation.isPending || cancelMutation.isPending || retryMutation.isPending;

  useEffect(() => {
    if (!selectedId || !active || typeof EventSource === "undefined") return;
    return subscribeImageJob(
      selectedId,
      (nextJob) => {
        queryClient.setQueryData(["image-job", nextJob.id], nextJob);
        if (nextJob.status !== "queued" && nextJob.status !== "running") {
          void queryClient.invalidateQueries({ queryKey: ["image-jobs", "recent", "generate"] });
        }
      },
      () => setStreamJobId((current) => (current === selectedId ? null : current)),
      () => setStreamJobId(selectedId),
    );
  }, [active, queryClient, selectedId]);

  const submit = useCallback(
    async (input: ImageJobCreate) => {
      if (submittingRef.current || active) return null;
      submittingRef.current = true;
      setLastRequest(input);
      createMutation.reset();
      try {
        return await createMutation.mutateAsync(input);
      } catch {
        return null;
      } finally {
        submittingRef.current = false;
      }
    },
    [active, createMutation],
  );

  const cancel = useCallback(async () => {
    if (!selectedId || !active || cancelMutation.isPending) return null;
    try {
      return await cancelMutation.mutateAsync(selectedId);
    } catch {
      return null;
    }
  }, [active, cancelMutation, selectedId]);

  const retry = useCallback(async () => {
    if (job?.status === "failed" && job.error?.retryable && selectedId) {
      try {
        return await retryMutation.mutateAsync(selectedId);
      } catch {
        return null;
      }
    }
    if (jobQuery.isError && selectedId) {
      const result = await jobQuery.refetch().catch(() => null);
      return result?.data ?? null;
    }
    if (lastRequest) return await submit(lastRequest);
    return null;
  }, [job, jobQuery, lastRequest, retryMutation, selectedId, submit]);

  const selectJob = useCallback((jobId: string) => setActiveId(jobId), []);

  return {
    job,
    submit,
    cancel,
    retry,
    isBusy,
    isSubmitting: createMutation.isPending,
    isCanceling: cancelMutation.isPending,
    hasError:
      createMutation.isError || jobQuery.isError || cancelMutation.isError || job?.status === "failed",
    canRetry:
      (job?.status === "failed" && job.error?.retryable === true) ||
      lastRequest !== null ||
      (jobQuery.isError && selectedId !== null),
    recentJobs: recentQuery.data ?? [],
    isLoadingRecent: recentQuery.isPending,
    selectJob,
  };
}
