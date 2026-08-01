"use client";

import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, Pencil, RefreshCw, RotateCcw, Square } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useMemo, useState } from "react";

import { Button } from "@/components/ui/Button";
import { Select } from "@/components/ui/Select";
import {
  cancelImageJob,
  fetchImageJob,
  fetchImageJobPage,
  getImageResultUrl,
  retryImageJob,
  type ImageJobResponse,
} from "@/lib/api/imageJobs";

import styles from "./jobs.module.css";

type StatusFilter = "all" | ImageJobResponse["status"];
type OperationFilter = "all" | ImageJobResponse["settings"]["operation"];

function formatTime(value: string | null) {
  if (!value) return "Not recorded";
  return new Intl.DateTimeFormat("en", {
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function phaseLabel(job: ImageJobResponse) {
  if (job.status === "canceled") return "Canceled";
  return job.phase.charAt(0).toUpperCase() + job.phase.slice(1);
}

export function JobCenterWorkspace() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const queryClient = useQueryClient();
  const [status, setStatus] = useState<StatusFilter>("all");
  const [operation, setOperation] = useState<OperationFilter>("all");
  const requestedId = searchParams?.get("job") ?? null;
  const list = useInfiniteQuery({
    queryKey: ["image-jobs", "job-center", status, operation],
    queryFn: ({ pageParam, signal }) => fetchImageJobPage({
      limit: 30,
      status: status === "all" ? undefined : status,
      operation: operation === "all" ? undefined : operation,
      cursor: pageParam,
      signal,
    }),
    initialPageParam: null as string | null,
    getNextPageParam: (page) => page.nextCursor ?? undefined,
    placeholderData: (previousData) => previousData,
    refetchInterval: (query) => {
      const pages = query.state.data?.pages ?? [];
      return pages.some((page) => page.items.some((job) => job.status === "queued" || job.status === "running"))
        ? 2_000
        : false;
    },
  });
  const jobs = useMemo(() => {
    const unique = new Map<string, ImageJobResponse>();
    for (const page of list.data?.pages ?? []) {
      for (const job of page.items) unique.set(job.id, job);
    }
    return [...unique.values()];
  }, [list.data]);
  const selectedId = requestedId ?? jobs[0]?.id ?? null;
  const selectedQuery = useQuery({
    queryKey: ["image-job", selectedId],
    queryFn: ({ signal }) => fetchImageJob(selectedId ?? "", signal),
    enabled: Boolean(selectedId),
    refetchInterval: (query) => {
      const selected = query.state.data;
      return selected?.status === "queued" || selected?.status === "running" ? 1_500 : false;
    },
  });
  const selected = selectedQuery.data ?? jobs.find((job) => job.id === selectedId) ?? null;

  function selectJob(jobId: string) {
    const next = new URLSearchParams(searchParams?.toString());
    next.set("job", jobId);
    router.replace(`/jobs?${next.toString()}`, { scroll: false });
  }

  const cancel = useMutation({
    mutationFn: cancelImageJob,
    onSuccess: (job) => {
      queryClient.setQueryData(["image-job", job.id], job);
      void queryClient.invalidateQueries({ queryKey: ["image-jobs"] });
    },
  });
  const retry = useMutation({
    mutationFn: retryImageJob,
    onSuccess: (job) => {
      queryClient.setQueryData(["image-job", job.id], job);
      void queryClient.invalidateQueries({ queryKey: ["image-jobs"] });
      selectJob(job.id);
    },
  });
  const resultUrl = selected ? getImageResultUrl(selected) : null;
  const active = selected?.status === "queued" || selected?.status === "running";

  return (
    <div className={styles.workspace}>
      <header className={styles.toolbar}>
        <div><span>Persistent operations</span><h1>Job center</h1></div>
        <div className={styles.toolbarActions}>
          <strong>{jobs.length} loaded</strong>
          <Button variant="quiet" onClick={() => void list.refetch()} disabled={list.isFetching}>
            <RefreshCw aria-hidden="true" size={15} />
            {list.isFetching ? "Refreshing" : "Refresh"}
          </Button>
        </div>
      </header>

      <div className={styles.filters} aria-label="Job filters">
        <label>Status<Select value={status} onChange={(event) => setStatus(event.target.value as StatusFilter)}>
          <option value="all">All statuses</option>
          <option value="queued">Queued</option>
          <option value="running">Running</option>
          <option value="completed">Completed</option>
          <option value="failed">Failed</option>
          <option value="canceled">Canceled</option>
        </Select></label>
        <label>Operation<Select value={operation} onChange={(event) => setOperation(event.target.value as OperationFilter)}>
          <option value="all">All operations</option>
          <option value="generate">Generation</option>
          <option value="edit">Edit</option>
        </Select></label>
      </div>

      <div className={styles.content}>
        <main className={styles.jobList} aria-label="Saved jobs">
          {list.isPending ? <p className={styles.message}>Loading saved jobs...</p> : null}
          {list.isError ? <div className={styles.message} role="alert"><strong>Jobs unavailable</strong><span>The saved job index could not be loaded.</span><Button onClick={() => void list.refetch()}>Retry</Button></div> : null}
          {list.isSuccess && jobs.length === 0 ? <p className={styles.message}>No jobs match these filters.</p> : null}
          {jobs.map((job) => (
            <button
              className={styles.jobRow}
              data-selected={job.id === selectedId}
              data-status={job.status}
              key={job.id}
              type="button"
              onClick={() => selectJob(job.id)}
            >
              <span className={styles.statusMark} aria-hidden="true" />
              <span className={styles.jobCopy}><strong>{job.prompt}</strong><small>{job.settings.operation === "edit" ? "Image edit" : "Image generation"} · {formatTime(job.createdAt)}</small></span>
              <span className={styles.jobPhase}>{phaseLabel(job)}</span>
              <span className={styles.progress}>{job.progress !== null ? `${job.progress}%` : "--"}</span>
            </button>
          ))}
          {list.hasNextPage ? <Button className={styles.loadMore} variant="quiet" onClick={() => void list.fetchNextPage()} disabled={list.isFetchingNextPage}>{list.isFetchingNextPage ? "Loading" : "Load older jobs"}</Button> : null}
        </main>

        <aside className={styles.inspector} aria-label="Selected job details">
          {selected ? (
            <>
              <header className={styles.detailHeader}>
                <div><span>{selected.settings.operation === "edit" ? "Image edit" : "Image generation"}</span><h2>{phaseLabel(selected)}</h2></div>
                <strong data-status={selected.status}>{selected.status}</strong>
              </header>
              <div className={styles.detailBody}>
                <section className={styles.progressSection} aria-live="polite">
                  <div><span>Progress</span><strong>{selected.progress !== null ? `${selected.progress}%` : "Provider update pending"}</strong></div>
                  <div className={styles.progressTrack}><span style={{ width: `${selected.progress ?? 0}%` }} /></div>
                  <p>{selected.currentStep !== null && selected.totalSteps !== null ? `Step ${selected.currentStep} of ${selected.totalSteps}` : phaseLabel(selected)}</p>
                  {selected.stalled ? <p className={styles.warning}>The provider has not reported new progress. Your saved job remains available.</p> : null}
                </section>

                <section><h3>Prompt</h3><p className={styles.prompt}>{selected.prompt}</p></section>
                <section><h3>Settings</h3><dl className={styles.metadata}>
                  <div><dt>Provider</dt><dd>{selected.settings.provider}</dd></div>
                  <div><dt>Ratio</dt><dd>{selected.settings.aspectRatio}</dd></div>
                  <div><dt>Style</dt><dd>{selected.settings.style}</dd></div>
                  <div><dt>Seed</dt><dd>{selected.settings.seed}</dd></div>
                  <div><dt>Created</dt><dd>{formatTime(selected.createdAt)}</dd></div>
                  <div><dt>Completed</dt><dd>{formatTime(selected.completedAt)}</dd></div>
                </dl></section>
                {selected.settings.edit ? <section><h3>Edit pipeline</h3><p className={styles.pipeline}>{selected.settings.edit.sampler} / {selected.settings.edit.scheduler} · {selected.settings.edit.steps} steps · CFG {selected.settings.edit.cfg}</p>{selected.settings.edit.loras.map((lora) => <p className={styles.pipeline} key={lora.id}>{lora.id} · Model {lora.modelWeight} · CLIP {lora.clipWeight}</p>)}</section> : null}
                {selected.error ? <section className={styles.error} role="alert"><strong>{selected.error.message}</strong><p>{selected.error.action}</p></section> : null}
              </div>
              <footer className={styles.detailActions}>
                {active ? <Button onClick={() => void cancel.mutateAsync(selected.id)} disabled={cancel.isPending}><Square aria-hidden="true" size={14} />Cancel</Button> : null}
                {selected.status === "failed" && selected.error?.retryable ? <Button onClick={() => void retry.mutateAsync(selected.id)} disabled={retry.isPending}><RotateCcw aria-hidden="true" size={14} />Retry</Button> : null}
                {resultUrl ? <a className={styles.actionLink} href={resultUrl} download={`canvasrelay-${selected.id}.png`}><Download aria-hidden="true" size={14} />Download</a> : null}
                {resultUrl ? <Link className={styles.actionLink} href={`/edit?sourceJobId=${encodeURIComponent(selected.id)}`}><Pencil aria-hidden="true" size={14} />Edit</Link> : null}
              </footer>
            </>
          ) : <p className={styles.message}>Select a job to inspect its saved settings.</p>}
        </aside>
      </div>
    </div>
  );
}
