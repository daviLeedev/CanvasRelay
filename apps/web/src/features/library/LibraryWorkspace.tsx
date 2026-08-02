"use client";

import { useInfiniteQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Download, Pencil, RefreshCw, RotateCcw, Trash2, X } from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useMemo, useState } from "react";

import { Button } from "@/components/ui/Button";
import { Select } from "@/components/ui/Select";
import {
  deleteImageJobAsset,
  fetchImageJobPage,
  getImageInputUrl,
  getImageResultUrl,
  getImageThumbnailUrl,
  type ImageJobResponse,
} from "@/lib/api/imageJobs";

import styles from "./library.module.css";

type OperationFilter = "all" | ImageJobResponse["settings"]["operation"];

function formatCreatedAt(value: string) {
  return new Intl.DateTimeFormat("en", {
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

export function LibraryWorkspace() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const queryClient = useQueryClient();
  const [operation, setOperation] = useState<OperationFilter>("all");
  const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null);
  const requestedId = searchParams?.get("job") ?? null;
  const query = useInfiniteQuery({
    queryKey: ["image-jobs", "library", operation],
    queryFn: ({ pageParam, signal }) => fetchImageJobPage({
      limit: 24,
      status: "completed",
      operation: operation === "all" ? undefined : operation,
      cursor: pageParam,
      signal,
    }),
    initialPageParam: null as string | null,
    getNextPageParam: (page) => page.nextCursor ?? undefined,
    placeholderData: (previousData) => previousData,
  });
  const jobs = useMemo(() => {
    const unique = new Map<string, ImageJobResponse>();
    for (const page of query.data?.pages ?? []) {
      for (const job of page.items) unique.set(job.id, job);
    }
    return [...unique.values()];
  }, [query.data]);
  const selectedId = requestedId && jobs.some((job) => job.id === requestedId)
    ? requestedId
    : jobs[0]?.id ?? null;
  const selected = jobs.find((job) => job.id === selectedId) ?? null;
  const selectedUrl = selected ? getImageResultUrl(selected) : null;

  function selectJob(jobId: string) {
    const next = new URLSearchParams(searchParams?.toString());
    next.set("job", jobId);
    router.replace(`/library?${next.toString()}`, { scroll: false });
    setPendingDeleteId(null);
  }

  const deletion = useMutation({
    mutationFn: deleteImageJobAsset,
    onSuccess: async (_, deletedId) => {
      setPendingDeleteId(null);
      const next = new URLSearchParams(searchParams?.toString());
      if (next.get("job") === deletedId) next.delete("job");
      router.replace(next.size ? `/library?${next.toString()}` : "/library", { scroll: false });
      await queryClient.invalidateQueries({ queryKey: ["image-jobs"] });
    },
  });

  return (
    <div className={styles.library}>
      <header className={styles.toolbar}>
        <div><span>CanvasRelay media store</span><h1>Image library</h1></div>
        <div className={styles.actions}>
          <label>Type<Select value={operation} onChange={(event) => setOperation(event.target.value as OperationFilter)}>
            <option value="all">All images</option>
            <option value="generate">Generated</option>
            <option value="edit">Edited</option>
          </Select></label>
          <strong>{jobs.length} loaded</strong>
          <Button variant="quiet" onClick={() => void query.refetch()} disabled={query.isFetching}>
            <RefreshCw aria-hidden="true" size={15} />
            {query.isFetching ? "Refreshing" : "Refresh"}
          </Button>
        </div>
      </header>

      <div className={styles.libraryBody}>
        <main className={styles.browser} aria-label="Stored images">
          {query.isPending ? <p className={styles.message}>Loading persistent results...</p> : null}
          {query.isError && !query.data ? (
            <div className={styles.error} role="alert">
              <strong>Library unavailable</strong>
              <p>The stored image index could not be loaded. Check the API and retry.</p>
              <Button onClick={() => void query.refetch()}>Retry</Button>
            </div>
          ) : null}
          {query.isError && query.data ? <p className={styles.refreshError} role="status">Refresh failed. Previously loaded images remain available.</p> : null}
          {query.isSuccess && jobs.length === 0 ? (
            <div className={styles.empty}>
              <h2>No stored images yet</h2>
              <p>Complete an image generation job and it will remain here after refresh.</p>
              <Link href="/image">Open image studio</Link>
            </div>
          ) : null}
          {jobs.length ? (
            <div className={styles.grid}>
              {jobs.map((job, index) => {
                const imageUrl = getImageThumbnailUrl(job);
                if (!imageUrl) return null;
                return (
                  <button
                    className={styles.item}
                    data-selected={job.id === selectedId}
                    key={job.id}
                    type="button"
                    onClick={() => selectJob(job.id)}
                  >
                    <span className={styles.preview}>
                      <Image src={imageUrl} alt={`Result for ${job.prompt}`} fill sizes="(max-width: 700px) 50vw, (max-width: 1100px) 33vw, 20vw" loading={index === 0 ? "eager" : "lazy"} unoptimized />
                    </span>
                    <span className={styles.itemMeta}><strong>{job.settings.operation === "edit" ? "Edit" : "Generate"}</strong><small>{job.settings.aspectRatio} · {formatCreatedAt(job.createdAt)}</small></span>
                  </button>
                );
              })}
            </div>
          ) : null}
          {query.hasNextPage ? <Button className={styles.loadMore} variant="quiet" onClick={() => void query.fetchNextPage()} disabled={query.isFetchingNextPage}>{query.isFetchingNextPage ? "Loading" : "Load older images"}</Button> : null}
        </main>

        <aside className={styles.detail} aria-label="Selected image details">
          {selected && selectedUrl ? (
            <>
              <header className={styles.detailHeader}><div><span>{selected.settings.operation === "edit" ? "Edited image" : "Generated image"}</span><h2>Asset details</h2></div><strong>{formatCreatedAt(selected.createdAt)}</strong></header>
              <div className={styles.detailScroll}>
                <div className={styles.detailPreview}><Image src={selectedUrl} alt={`Selected result for ${selected.prompt}`} fill sizes="360px" unoptimized /></div>
                <section><h3>Prompt</h3><p className={styles.prompt}>{selected.prompt}</p></section>
                <section><h3>Provenance</h3><dl className={styles.metadata}>
                  <div><dt>Provider</dt><dd>{selected.settings.provider}</dd></div>
                  <div><dt>Operation</dt><dd>{selected.settings.operation}</dd></div>
                  <div><dt>Ratio</dt><dd>{selected.settings.aspectRatio}</dd></div>
                  <div><dt>Style</dt><dd>{selected.settings.style}</dd></div>
                  <div><dt>Seed</dt><dd>{selected.settings.seed}</dd></div>
                </dl></section>
                {selected.settings.edit ? <section><h3>Edit settings</h3><p className={styles.pipeline}>{selected.settings.edit.sampler} / {selected.settings.edit.scheduler} · {selected.settings.edit.steps} steps · CFG {selected.settings.edit.cfg}</p><p className={styles.pipeline}>Reference {selected.settings.edit.referenceInfluence} · Grounding {selected.settings.edit.groundingResolution} · {selected.settings.edit.fitMode}</p>{selected.settings.edit.loras.length ? <div className={styles.loraList}>{selected.settings.edit.loras.map((lora) => <p key={lora.id}><strong>{lora.id}</strong><span>Model {lora.modelWeight} · CLIP {lora.clipWeight}</span></p>)}</div> : <p className={styles.pipeline}>No user LoRA recorded.</p>}</section> : null}
                {selected.settings.operation === "edit" ? <section><h3>References</h3><div className={styles.references}><div><Image src={getImageInputUrl(selected.id, "source")} alt="Source reference" fill sizes="112px" unoptimized /><span>Source</span></div>{selected.settings.hasFaceReference ? <div><Image src={getImageInputUrl(selected.id, "identity")} alt="Identity reference" fill sizes="112px" unoptimized /><span>Identity</span></div> : null}</div></section> : null}
                {deletion.isError && pendingDeleteId === selected.id ? <p className={styles.deleteError} role="alert">This image could not be deleted. It may still be used by another saved edit.</p> : null}
              </div>
              <footer className={styles.detailActions}>
                <a href={selectedUrl} download={`canvasrelay-${selected.id}.png`}><Download aria-hidden="true" size={14} />Download</a>
                <Link href={`/edit?sourceJobId=${encodeURIComponent(selected.id)}`}><Pencil aria-hidden="true" size={14} />Edit</Link>
                {selected.settings.operation === "edit" ? <Link href={`/edit?sourceJobId=${encodeURIComponent(selected.id)}&restoreJobId=${encodeURIComponent(selected.id)}`}><RotateCcw aria-hidden="true" size={14} />Edit again</Link> : null}
                {pendingDeleteId === selected.id ? <><Button className={styles.dangerButton} onClick={() => void deletion.mutateAsync(selected.id)} disabled={deletion.isPending}><Trash2 aria-hidden="true" size={14} />Confirm delete</Button><Button variant="quiet" onClick={() => setPendingDeleteId(null)}><X aria-hidden="true" size={14} />Keep</Button></> : <Button variant="quiet" onClick={() => setPendingDeleteId(selected.id)}><Trash2 aria-hidden="true" size={14} />Delete</Button>}
              </footer>
            </>
          ) : <p className={styles.message}>Select a stored image to inspect its provenance.</p>}
        </aside>
      </div>
    </div>
  );
}
