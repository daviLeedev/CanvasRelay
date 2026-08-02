"use client";

import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CheckSquare,
  Download,
  Grid2X2,
  Pencil,
  RefreshCw,
  RotateCcw,
  Search,
  Tag,
  Trash2,
  X,
} from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import {
  type CSSProperties,
  type FormEvent,
  useDeferredValue,
  useMemo,
  useState,
} from "react";

import { Button } from "@/components/ui/Button";
import { Select } from "@/components/ui/Select";
import {
  deleteImageJobAssets,
  fetchImageJobPage,
  fetchImageJobTags,
  getImageInputUrl,
  getImageResultUrl,
  getImageThumbnailUrl,
  type ImageJobResponse,
  updateImageJobTags,
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

function normalizeTag(value: string) {
  return value.trim().replace(/\s+/g, " ").toLocaleLowerCase();
}

export function LibraryWorkspace() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const queryClient = useQueryClient();
  const [operation, setOperation] = useState<OperationFilter>("all");
  const [searchValue, setSearchValue] = useState("");
  const [tagFilter, setTagFilter] = useState("");
  const [tileSize, setTileSize] = useState(2);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(() => new Set());
  const [confirmBatchDelete, setConfirmBatchDelete] = useState(false);
  const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null);
  const [tagDraft, setTagDraft] = useState("");
  const deferredSearch = useDeferredValue(searchValue.trim());
  const requestedId = searchParams?.get("job") ?? null;
  const columns = 8 - tileSize;

  const query = useInfiniteQuery({
    queryKey: ["image-jobs", "library", operation, deferredSearch, tagFilter],
    queryFn: ({ pageParam, signal }) => fetchImageJobPage({
      limit: 48,
      status: "completed",
      operation: operation === "all" ? undefined : operation,
      search: deferredSearch || undefined,
      tag: tagFilter || undefined,
      cursor: pageParam,
      signal,
    }),
    initialPageParam: null as string | null,
    getNextPageParam: (page) => page.nextCursor ?? undefined,
    placeholderData: (previousData) => previousData,
  });
  const tagQuery = useQuery({
    queryKey: ["image-jobs", "tags"],
    queryFn: ({ signal }) => fetchImageJobTags(signal),
    placeholderData: (previousData) => previousData,
    enabled: query.isSuccess && Boolean(query.data?.pages.some((page) => page.items.length)),
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
  const selectedTags = selected?.tags ?? [];
  const selectionActive = selectedIds.size > 0;

  function replaceSelection(nextIds: Set<string>) {
    setSelectedIds(nextIds);
    setConfirmBatchDelete(false);
  }

  function toggleSelection(jobId: string) {
    const next = new Set(selectedIds);
    if (next.has(jobId)) next.delete(jobId);
    else next.add(jobId);
    replaceSelection(next);
  }

  function selectJob(jobId: string) {
    if (selectionActive) {
      toggleSelection(jobId);
      return;
    }
    const next = new URLSearchParams(searchParams?.toString());
    next.set("job", jobId);
    router.replace(`/library?${next.toString()}`, { scroll: false });
    setPendingDeleteId(null);
    setTagDraft("");
  }

  const deletion = useMutation({
    mutationFn: deleteImageJobAssets,
    onSuccess: async (deletedIds) => {
      setPendingDeleteId(null);
      setTagDraft("");
      replaceSelection(new Set());
      const next = new URLSearchParams(searchParams?.toString());
      if (deletedIds.includes(next.get("job") ?? "")) next.delete("job");
      router.replace(next.size ? `/library?${next.toString()}` : "/library", { scroll: false });
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["image-jobs"] }),
        queryClient.invalidateQueries({ queryKey: ["image-jobs", "tags"] }),
      ]);
    },
  });

  const tagUpdate = useMutation({
    mutationFn: ({ jobId, tags }: { jobId: string; tags: string[] }) =>
      updateImageJobTags(jobId, tags),
    onSuccess: async () => {
      setTagDraft("");
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["image-jobs"] }),
        queryClient.invalidateQueries({ queryKey: ["image-jobs", "tags"] }),
      ]);
    },
  });

  function addTag(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!selected) return;
    const tag = normalizeTag(tagDraft);
    if (!tag || selectedTags.includes(tag) || selectedTags.length >= 12) return;
    tagUpdate.mutate({ jobId: selected.id, tags: [...selectedTags, tag] });
  }

  function removeTag(tag: string) {
    if (!selected) return;
    tagUpdate.mutate({ jobId: selected.id, tags: selectedTags.filter((item) => item !== tag) });
  }

  const hasFilters = Boolean(deferredSearch || tagFilter || operation !== "all");

  return (
    <div className={styles.library}>
      <header className={styles.toolbar}>
        <div className={styles.title}><span>CanvasRelay media store</span><h1>Image library</h1></div>
        <div className={styles.actions}>
          <label className={styles.searchField}>
            <Search aria-hidden="true" size={14} />
            <span className={styles.srOnly}>Search prompts</span>
            <input
              type="search"
              placeholder="Search prompts"
              value={searchValue}
              onChange={(event) => setSearchValue(event.target.value)}
            />
          </label>
          <label>Type<Select value={operation} onChange={(event) => {
            setOperation(event.target.value as OperationFilter);
            replaceSelection(new Set());
          }}>
            <option value="all">All images</option>
            <option value="generate">Generated</option>
            <option value="edit">Edited</option>
          </Select></label>
          <label>Tag<Select value={tagFilter} onChange={(event) => {
            setTagFilter(event.target.value);
            replaceSelection(new Set());
          }}>
            <option value="">All tags</option>
            {(tagQuery.data ?? []).map((tag) => <option key={tag} value={tag}>{tag}</option>)}
          </Select></label>
          <label className={styles.densityControl} title={`${columns} columns`}>
            <Grid2X2 aria-hidden="true" size={14} />
            <span className={styles.srOnly}>Thumbnail size</span>
            <input aria-label="Thumbnail size" type="range" min="0" max="4" step="1" value={tileSize} onChange={(event) => setTileSize(Number(event.target.value))} />
          </label>
          <strong>{jobs.length} loaded</strong>
          <Button variant="quiet" onClick={() => void query.refetch()} disabled={query.isFetching}>
            <RefreshCw aria-hidden="true" size={15} />
            {query.isFetching ? "Refreshing" : "Refresh"}
          </Button>
        </div>
      </header>

      {selectionActive ? (
        <div className={styles.selectionBar} role="status">
          <div><CheckSquare aria-hidden="true" size={16} /><strong>{selectedIds.size} selected</strong><span>Click any tile to change the selection.</span></div>
          <div>
            <Button variant="quiet" onClick={() => replaceSelection(new Set(jobs.map((job) => job.id)))}>Select loaded</Button>
            {confirmBatchDelete ? (
              <>
                <Button className={styles.dangerButton} onClick={() => deletion.mutate([...selectedIds])} disabled={deletion.isPending}>
                  <Trash2 aria-hidden="true" size={14} />{deletion.isPending ? "Deleting" : `Confirm ${selectedIds.size}`}
                </Button>
                <Button variant="quiet" onClick={() => setConfirmBatchDelete(false)}>Keep</Button>
              </>
            ) : <Button variant="quiet" onClick={() => setConfirmBatchDelete(true)}><Trash2 aria-hidden="true" size={14} />Delete selected</Button>}
            <Button variant="quiet" onClick={() => replaceSelection(new Set())}><X aria-hidden="true" size={14} />Exit selection</Button>
          </div>
        </div>
      ) : null}

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
          {deletion.isError ? <p className={styles.refreshError} role="alert">The selected images could not be deleted. A saved edit may still reference one of them.</p> : null}
          {query.isSuccess && jobs.length === 0 ? (
            <div className={styles.empty}>
              <h2>{hasFilters ? "No images match these filters" : "No stored images yet"}</h2>
              <p>{hasFilters ? "Clear the search or choose another tag." : "Complete an image generation job and it will remain here after refresh."}</p>
              {hasFilters ? <Button variant="quiet" onClick={() => { setSearchValue(""); setTagFilter(""); setOperation("all"); }}>Clear filters</Button> : <Link href="/image">Open image studio</Link>}
            </div>
          ) : null}
          {jobs.length ? (
            <div className={styles.grid} style={{ "--library-columns": columns } as CSSProperties}>
              {jobs.map((job, index) => {
                const imageUrl = getImageThumbnailUrl(job);
                if (!imageUrl) return null;
                const marked = selectedIds.has(job.id);
                return (
                  <article className={styles.item} data-selected={!selectionActive && job.id === selectedId} data-marked={marked} key={job.id}>
                    <input
                      className={styles.selector}
                      type="checkbox"
                      aria-label={`Select ${job.settings.operation} from ${formatCreatedAt(job.createdAt)}`}
                      checked={marked}
                      onChange={() => toggleSelection(job.id)}
                    />
                    <button className={styles.itemButton} type="button" onClick={() => selectJob(job.id)}>
                      <span className={styles.preview}>
                        <Image src={imageUrl} alt={`Result for ${job.prompt}`} fill sizes="(max-width: 700px) 50vw, (max-width: 1100px) 33vw, 16vw" loading={index === 0 ? "eager" : "lazy"} unoptimized />
                      </span>
                      <span className={styles.itemMeta}><strong>{job.settings.operation === "edit" ? "Edit" : "Generate"}</strong><small>{job.settings.aspectRatio} · {formatCreatedAt(job.createdAt)}</small></span>
                    </button>
                  </article>
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
                <section>
                  <h3>Tags</h3>
                  <div className={styles.tags}>{selectedTags.map((tag) => <span key={tag}><Tag aria-hidden="true" size={10} />{tag}<button type="button" aria-label={`Remove ${tag} tag`} onClick={() => removeTag(tag)} disabled={tagUpdate.isPending}><X aria-hidden="true" size={10} /></button></span>)}</div>
                  <form className={styles.tagForm} onSubmit={addTag}>
                    <input aria-label="New tag" maxLength={48} placeholder="Add a tag" value={tagDraft} onChange={(event) => setTagDraft(event.target.value)} disabled={selectedTags.length >= 12 || tagUpdate.isPending} />
                    <Button type="submit" variant="quiet" disabled={!normalizeTag(tagDraft) || tagUpdate.isPending || selectedTags.length >= 12}>Add</Button>
                  </form>
                </section>
                <section><h3>Provenance</h3><dl className={styles.metadata}>
                  <div><dt>Provider</dt><dd>{selected.settings.provider}</dd></div>
                  <div><dt>Operation</dt><dd>{selected.settings.operation}</dd></div>
                  <div><dt>Ratio</dt><dd>{selected.settings.aspectRatio}</dd></div>
                  <div><dt>Style</dt><dd>{selected.settings.style}</dd></div>
                  <div><dt>Seed</dt><dd>{selected.settings.seed}</dd></div>
                </dl></section>
                {selected.settings.generation ? <section><h3>Generation settings</h3><p className={styles.pipeline}>{selected.settings.generation.sampler} / {selected.settings.generation.scheduler} · {selected.settings.generation.steps} steps · CFG {selected.settings.generation.cfg} · Shift {selected.settings.generation.shift}</p>{selected.settings.generation.loras.length ? <div className={styles.loraList}>{selected.settings.generation.loras.map((lora) => <p key={lora.id}><strong>{lora.id}</strong><span>Model {lora.modelWeight} · CLIP {lora.clipWeight}</span></p>)}</div> : <p className={styles.pipeline}>No user LoRA recorded.</p>}</section> : null}
                {selected.settings.edit ? <section><h3>Edit settings</h3><p className={styles.pipeline}>{selected.settings.edit.sampler} / {selected.settings.edit.scheduler} · {selected.settings.edit.steps} steps · CFG {selected.settings.edit.cfg}</p><p className={styles.pipeline}>Reference {selected.settings.edit.referenceInfluence} · Grounding {selected.settings.edit.groundingResolution} · {selected.settings.edit.fitMode}</p>{selected.settings.edit.loras.length ? <div className={styles.loraList}>{selected.settings.edit.loras.map((lora) => <p key={lora.id}><strong>{lora.id}</strong><span>Model {lora.modelWeight} · CLIP {lora.clipWeight}</span></p>)}</div> : <p className={styles.pipeline}>No user LoRA recorded.</p>}</section> : null}
                {selected.settings.operation === "edit" ? <section><h3>References</h3><div className={styles.references}><div><Image src={getImageInputUrl(selected.id, "source")} alt="Source reference" fill sizes="112px" unoptimized /><span>Source</span></div>{selected.settings.hasFaceReference ? <div><Image src={getImageInputUrl(selected.id, "identity")} alt="Identity reference" fill sizes="112px" unoptimized /><span>Identity</span></div> : null}</div></section> : null}
                {deletion.isError && pendingDeleteId === selected.id ? <p className={styles.deleteError} role="alert">This image could not be deleted. It may still be used by another saved edit.</p> : null}
              </div>
              <footer className={styles.detailActions}>
                <a href={selectedUrl} download={`canvasrelay-${selected.id}.png`}><Download aria-hidden="true" size={14} />Download</a>
                <Link href={`/edit?sourceJobId=${encodeURIComponent(selected.id)}`}><Pencil aria-hidden="true" size={14} />Edit</Link>
                {selected.settings.operation === "edit" ? <Link href={`/edit?sourceJobId=${encodeURIComponent(selected.id)}&restoreJobId=${encodeURIComponent(selected.id)}`}><RotateCcw aria-hidden="true" size={14} />Edit again</Link> : null}
                {pendingDeleteId === selected.id ? <><Button className={styles.dangerButton} onClick={() => deletion.mutate([selected.id])} disabled={deletion.isPending}><Trash2 aria-hidden="true" size={14} />Confirm delete</Button><Button variant="quiet" onClick={() => setPendingDeleteId(null)}><X aria-hidden="true" size={14} />Keep</Button></> : <Button variant="quiet" onClick={() => setPendingDeleteId(selected.id)}><Trash2 aria-hidden="true" size={14} />Delete</Button>}
              </footer>
            </>
          ) : <p className={styles.message}>Select a stored image to inspect its provenance.</p>}
        </aside>
      </div>
    </div>
  );
}
