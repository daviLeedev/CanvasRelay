"use client";

import { RotateCcw, Square, WandSparkles } from "lucide-react";
import { type FormEvent, useState } from "react";

import { Button } from "@/components/ui/Button";
import { Field } from "@/components/ui/Field";
import { Select } from "@/components/ui/Select";
import type { ImageJobCreate, ImageJobResponse } from "@/lib/api/imageJobs";

import { DemoResultPreview } from "./DemoResultPreview";
import styles from "./studio.module.css";

type ImageGenerationPanelProps = {
  job: ImageJobResponse | null;
  isBusy: boolean;
  isSubmitting: boolean;
  isCanceling: boolean;
  hasError: boolean;
  canRetry: boolean;
  onSubmit: (input: ImageJobCreate) => Promise<void>;
  onCancel: () => Promise<unknown>;
  onRetry: () => Promise<unknown>;
};

export function ImageGenerationPanel({
  job,
  isBusy,
  isSubmitting,
  isCanceling,
  hasError,
  canRetry,
  onSubmit,
  onCancel,
  onRetry,
}: Readonly<ImageGenerationPanelProps>) {
  const [prompt, setPrompt] = useState("");
  const [aspectRatio, setAspectRatio] = useState<ImageJobCreate["aspectRatio"]>("4:3");
  const [style, setStyle] = useState<ImageJobCreate["style"]>("editorial");
  const [seed, setSeed] = useState("");
  const canGenerate = prompt.trim().length > 0 && !isBusy;

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canGenerate) return;
    const parsedSeed = seed === "" ? undefined : Number(seed);
    await onSubmit({
      prompt: prompt.trim(),
      aspectRatio,
      style,
      ...(Number.isInteger(parsedSeed) ? { seed: parsedSeed } : {}),
    });
  }

  const active = job?.status === "queued" || job?.status === "running";

  return (
    <section className={styles.generationPanel} aria-labelledby="generation-panel-title">
      <header className={styles.panelHeading}>
        <div>
          <span>Deterministic provider</span>
          <h2 id="generation-panel-title">Generate image</h2>
        </div>
        <span className={styles.demoPill}>Demo</span>
      </header>

      <form className={styles.generationForm} onSubmit={handleSubmit}>
        <Field label="Prompt" htmlFor="image-prompt" hint="No external provider or GPU is used.">
          <textarea
            className={styles.promptInput}
            id="image-prompt"
            maxLength={1200}
            rows={4}
            value={prompt}
            onChange={(event) => setPrompt(event.target.value)}
            placeholder="Describe the image to relay"
          />
        </Field>

        <div className={styles.settingGrid}>
          <Field label="Aspect ratio" htmlFor="image-aspect-ratio">
            <Select
              id="image-aspect-ratio"
              value={aspectRatio}
              onChange={(event) => setAspectRatio(event.target.value as ImageJobCreate["aspectRatio"])}
            >
              <option value="1:1">1:1 Square</option>
              <option value="4:3">4:3 Landscape</option>
              <option value="3:4">3:4 Portrait</option>
              <option value="16:9">16:9 Wide</option>
            </Select>
          </Field>
          <Field label="Style" htmlFor="image-style">
            <Select
              id="image-style"
              value={style}
              onChange={(event) => setStyle(event.target.value as ImageJobCreate["style"])}
            >
              <option value="editorial">Editorial</option>
              <option value="product">Product</option>
              <option value="concept">Concept</option>
            </Select>
          </Field>
        </div>

        <Field label="Seed (optional)" htmlFor="image-seed">
          <input
            className={styles.seedInput}
            id="image-seed"
            inputMode="numeric"
            min="0"
            max="2147483647"
            type="number"
            value={seed}
            onChange={(event) => setSeed(event.target.value)}
            placeholder="Derived from prompt"
          />
        </Field>

        <div className={styles.generationActions}>
          <Button variant="primary" type="submit" disabled={!canGenerate}>
            <WandSparkles aria-hidden="true" size={16} />
            {isSubmitting ? "Submitting..." : active ? "Generating..." : "Generate"}
          </Button>
          {active ? (
            <Button type="button" onClick={() => void onCancel()} disabled={isCanceling}>
              <Square aria-hidden="true" size={14} />
              {isCanceling ? "Canceling..." : "Cancel"}
            </Button>
          ) : null}
        </div>
      </form>

      {job ? (
        <div className={styles.liveJob} aria-live="polite">
          <div>
            <span>{job.status}</span>
            <strong>{job.progress}%</strong>
          </div>
          <span className={styles.inspectorProgress} aria-hidden="true">
            <span style={{ width: `${job.progress}%` }} />
          </span>
        </div>
      ) : null}

      {hasError ? (
        <div className={styles.generationError} role="alert">
          <strong>Generation request failed</strong>
          <p>The demo service could not finish the request. Check the API status and try again.</p>
          {canRetry ? (
            <Button type="button" onClick={() => void onRetry()}>
              <RotateCcw aria-hidden="true" size={14} />
              Retry
            </Button>
          ) : null}
        </div>
      ) : null}

      {job?.status === "completed" ? <DemoResultPreview job={job} compact /> : null}
    </section>
  );
}
