import { Clock3, ImageOff } from "lucide-react";
import Image from "next/image";

import { getImageResultUrl, type ImageJobResponse } from "@/lib/api/imageJobs";

import styles from "./studio.module.css";

export function RecentImageJobs({
  jobs,
  selectedId,
  loading,
  onSelect,
}: Readonly<{
  jobs: ImageJobResponse[];
  selectedId?: string;
  loading: boolean;
  onSelect: (jobId: string) => void;
}>) {
  return (
    <section className={styles.recentJobs} aria-labelledby="recent-jobs-title">
      <header>
        <div>
          <span>Persistent history</span>
          <h2 id="recent-jobs-title">Recent jobs</h2>
        </div>
        <strong>{jobs.length}</strong>
      </header>
      {loading ? <p className={styles.recentEmpty}>Loading recent jobs...</p> : null}
      {!loading && jobs.length === 0 ? (
        <p className={styles.recentEmpty}>Generated images will remain here after refresh.</p>
      ) : null}
      {jobs.length > 0 ? (
        <div className={styles.recentGrid}>
          {jobs.slice(0, 6).map((item, index) => {
            const imageUrl = getImageResultUrl(item);
            return (
              <button
                type="button"
                className={styles.recentItem}
                data-selected={item.id === selectedId}
                onClick={() => onSelect(item.id)}
                title={item.prompt}
                key={item.id}
              >
                <span className={styles.recentThumb}>
                  {imageUrl ? (
                    <Image
                      src={imageUrl}
                      alt=""
                      fill
                      sizes="112px"
                      loading={index === 0 ? "eager" : "lazy"}
                      unoptimized
                    />
                  ) : item.status === "failed" ? (
                    <ImageOff aria-hidden="true" size={18} />
                  ) : (
                    <Clock3 aria-hidden="true" size={18} />
                  )}
                </span>
                <span className={styles.recentCopy}>
                  <strong>{item.prompt}</strong>
                  <small>
                    {item.settings.style} · {item.settings.aspectRatio} · {item.settings.provider}
                  </small>
                </span>
                <span className={styles.recentStatus} data-status={item.status}>{item.status}</span>
              </button>
            );
          })}
        </div>
      ) : null}
    </section>
  );
}
