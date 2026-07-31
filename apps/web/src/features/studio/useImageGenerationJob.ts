"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useRef, useState } from "react";

import {
  cancelImageJob,
  createImageJob,
  fetchImageJob,
  type ImageJobCreate,
  type ImageJobResponse,
} from "@/lib/api/imageJobs";

const POLL_INTERVAL_MS = 250;

export function useImageGenerationJob() {
  const queryClient = useQueryClient();
  const submittingRef = useRef(false);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [lastRequest, setLastRequest] = useState<ImageJobCreate | null>(null);

  const jobQuery = useQuery({
    queryKey: ["image-job", activeId],
    queryFn: ({ signal }) => fetchImageJob(activeId ?? "", signal),
    enabled: activeId !== null,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "queued" || status === "running" ? POLL_INTERVAL_MS : false;
    },
  });

  const createMutation = useMutation({
    mutationFn: createImageJob,
    onSuccess: (job) => {
      queryClient.setQueryData(["image-job", job.id], job);
      setActiveId(job.id);
    },
  });

  const cancelMutation = useMutation({
    mutationFn: cancelImageJob,
    onMutate: async (jobId) => {
      await queryClient.cancelQueries({ queryKey: ["image-job", jobId] });
    },
    onSuccess: (job) => queryClient.setQueryData(["image-job", job.id], job),
  });

  const job = (jobQuery.data ?? createMutation.data ?? null) as ImageJobResponse | null;
  const active = job?.status === "queued" || job?.status === "running";
  const isBusy = active || createMutation.isPending || cancelMutation.isPending;

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
    if (!activeId || !active || cancelMutation.isPending) return null;
    try {
      return await cancelMutation.mutateAsync(activeId);
    } catch {
      return null;
    }
  }, [active, activeId, cancelMutation]);

  const retry = useCallback(async () => {
    if (jobQuery.isError && activeId) {
      const result = await jobQuery.refetch().catch(() => null);
      return result?.data ?? null;
    }
    if (lastRequest) return await submit(lastRequest);
    return null;
  }, [activeId, jobQuery, lastRequest, submit]);

  return {
    job,
    submit,
    cancel,
    retry,
    isBusy,
    isSubmitting: createMutation.isPending,
    isCanceling: cancelMutation.isPending,
    hasError: createMutation.isError || jobQuery.isError || cancelMutation.isError,
    canRetry: lastRequest !== null || (jobQuery.isError && activeId !== null),
  };
}
