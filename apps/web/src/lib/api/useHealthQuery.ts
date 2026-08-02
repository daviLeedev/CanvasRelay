"use client";

import { useQuery } from "@tanstack/react-query";

import { fetchHealth } from "./health";

export const healthQueryKey = ["health"] as const;

export function useHealthQuery() {
  return useQuery({
    queryKey: healthQueryKey,
    queryFn: ({ signal }) => fetchHealth(signal),
    staleTime: 30_000,
  });
}
