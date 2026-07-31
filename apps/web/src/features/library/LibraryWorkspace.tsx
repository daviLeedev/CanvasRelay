"use client";

import { ExternalLink, Pencil, RefreshCw } from "lucide-react";
import Image from "next/image";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";

import { Button } from "@/components/ui/Button";
import { fetchImageJobs, getImageResultUrl } from "@/lib/api/imageJobs";

import styles from "./library.module.css";

function formatCreatedAt(value: string) {
  return new Intl.DateTimeFormat("en", {
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

export function LibraryWorkspace() {
  const query = useQuery({
    queryKey: ["image-jobs", "library"],
    queryFn: () => fetchImageJobs(48, "completed"),
  });

  return (
    <div className={styles.library}>
      <header className={styles.toolbar}>
        <div>
          <span>Stored locally</span>
          <h1>Image library</h1>
        </div>
        <div className={styles.actions}>
          <strong>{query.data?.length ?? 0} results</strong>
          <Button variant="quiet" onClick={() => void query.refetch()} disabled={query.isFetching}>
            <RefreshCw aria-hidden="true" size={15} />
            {query.isFetching ? "Refreshing" : "Refresh"}
          </Button>
        </div>
      </header>

      <main className={styles.libraryBody}>
        {query.isPending ? <p className={styles.message}>Loading persistent results...</p> : null}
        {query.isError ? (
          <div className={styles.error} role="alert">
            <strong>Library unavailable</strong>
            <p>The stored image index could not be loaded. Check the API and retry.</p>
            <Button onClick={() => void query.refetch()}>Retry</Button>
          </div>
        ) : null}
        {query.isSuccess && query.data.length === 0 ? (
          <div className={styles.empty}>
            <h2>No stored images yet</h2>
            <p>Complete an image generation job and it will remain here after refresh.</p>
            <Link href="/image">Open image studio</Link>
          </div>
        ) : null}
        {query.data?.length ? (
          <div className={styles.grid}>
            {query.data.map((job, index) => {
              const imageUrl = getImageResultUrl(job);
              if (!imageUrl) return null;
              return (
                <article className={styles.item} key={job.id}>
                  <a className={styles.preview} href={imageUrl} target="_blank" rel="noreferrer">
                    <Image
                      src={imageUrl}
                      alt={`Generated result for ${job.prompt}`}
                      fill
                      sizes="(max-width: 700px) 50vw, (max-width: 1100px) 33vw, 25vw"
                      loading={index === 0 ? "eager" : "lazy"}
                      unoptimized
                    />
                    <ExternalLink aria-hidden="true" size={15} />
                  </a>
                  <div className={styles.meta}>
                    <p title={job.prompt}>{job.prompt}</p>
                    <dl>
                      <div><dt>Type</dt><dd>{job.settings.operation === "edit" ? "Edit" : "Generate"}</dd></div>
                      <div><dt>Provider</dt><dd>{job.settings.provider}</dd></div>
                      <div><dt>Ratio</dt><dd>{job.settings.aspectRatio}</dd></div>
                      <div><dt>Created</dt><dd>{formatCreatedAt(job.createdAt)}</dd></div>
                    </dl>
                    {job.settings.edit ? (
                      <details className={styles.details}>
                        <summary>Edit settings</summary>
                        <p>{job.settings.edit.sampler} / {job.settings.edit.scheduler} · {job.settings.edit.steps} steps · CFG {job.settings.edit.cfg}</p>
                        {job.settings.edit.loras.map((lora) => (
                          <p key={lora.id}>{lora.id} · Model {lora.modelWeight} · CLIP {lora.clipWeight}</p>
                        ))}
                      </details>
                    ) : null}
                    <Link className={styles.editLink} href={`/edit?sourceJobId=${encodeURIComponent(job.id)}`}>
                      <Pencil aria-hidden="true" size={14} />Edit
                    </Link>
                  </div>
                </article>
              );
            })}
          </div>
        ) : null}
      </main>
    </div>
  );
}
