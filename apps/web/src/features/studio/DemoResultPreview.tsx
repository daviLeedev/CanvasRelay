import Image from "next/image";

import type { ImageJobResponse } from "@/lib/api/imageJobs";
import { getImageResultUrl } from "@/lib/api/imageJobs";

import styles from "./studio.module.css";

export function DemoResultPreview({ job, compact = false }: Readonly<{
  job: ImageJobResponse;
  compact?: boolean;
}>) {
  const url = getImageResultUrl(job);
  if (!job.result || !url) return null;

  return (
    <figure className={compact ? styles.compactResult : styles.resultPreview}>
      <div className={styles.resultImageFrame}>
        <Image
          src={url}
          alt={`Deterministic demo result for ${job.prompt}`}
          fill
          sizes={compact ? "280px" : "(max-width: 700px) 90vw, 60vw"}
          unoptimized
        />
        <span className={styles.demoBadge}>Demo result</span>
      </div>
      {!compact ? <figcaption>Generated locally by the deterministic demo renderer.</figcaption> : null}
    </figure>
  );
}
