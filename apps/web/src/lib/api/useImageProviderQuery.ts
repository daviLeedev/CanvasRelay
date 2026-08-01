"use client";

import { useQuery } from "@tanstack/react-query";

import { fetchImageEditOptions } from "./imageJobs";
import { fetchImageEditProvider, fetchImageProvider } from "./imageProvider";

export function useImageProviderQuery() {
  return useQuery({
    queryKey: ["image-provider"],
    queryFn: ({ signal }) => fetchImageProvider(signal),
    staleTime: 5_000,
    refetchInterval: 10_000,
    retry: 1,
  });
}

export function useImageEditOptionsQuery() {
  return useQuery({
    queryKey: ["image-edit-options"],
    queryFn: ({ signal }) => fetchImageEditOptions(signal),
    staleTime: 30_000,
    retry: 1,
  });
}


export function useImageEditProviderQuery() {
  return useQuery({
    queryKey: ["image-edit-provider"],
    queryFn: ({ signal }) => fetchImageEditProvider(signal),
    staleTime: 5_000,
    refetchInterval: 10_000,
    retry: 1,
  });
}
