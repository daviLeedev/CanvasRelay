"use client";

import { RotateCcw, Square, Upload, WandSparkles, X } from "lucide-react";
import { type DragEvent, type FormEvent, useEffect, useId, useMemo, useState } from "react";

import { Button } from "@/components/ui/Button";
import { Field } from "@/components/ui/Field";
import { Select } from "@/components/ui/Select";
import type { ImageEditJobCreate, ImageJobResponse } from "@/lib/api/imageJobs";
import type { ImageProviderResponse } from "@/lib/api/imageProvider";

import styles from "./edit.module.css";

const ACCEPTED_TYPES = ["image/png", "image/jpeg", "image/webp"];

function useFilePreview(file: File | null) {
  const url = useMemo(() => (file ? URL.createObjectURL(file) : null), [file]);
  useEffect(() => {
    return () => {
      if (url) URL.revokeObjectURL(url);
    };
  }, [url]);
  return url;
}

function ImageInput({
  label,
  hint,
  file,
  required,
  onChange,
}: Readonly<{
  label: string;
  hint: string;
  file: File | null;
  required?: boolean;
  onChange: (file: File | null) => void;
}>) {
  const inputId = useId();
  const preview = useFilePreview(file);

  function acceptFile(nextFile: File | undefined) {
    if (nextFile && ACCEPTED_TYPES.includes(nextFile.type)) onChange(nextFile);
  }

  function handleDrop(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault();
    acceptFile(event.dataTransfer.files[0]);
  }

  return (
    <div className={styles.fileField}>
      <div className={styles.fileLabel}>
        <strong>{label}</strong>
        <span>{required ? "Required" : "Optional"}</span>
      </div>
      <label
        className={styles.dropzone}
        data-filled={file ? "true" : "false"}
        htmlFor={inputId}
        onDragOver={(event) => event.preventDefault()}
        onDrop={handleDrop}
      >
        {preview ? (
          // Blob URLs are local-only previews and cannot use Next's optimizer.
          // eslint-disable-next-line @next/next/no-img-element
          <img src={preview} alt="" />
        ) : (
          <Upload aria-hidden="true" size={18} />
        )}
        <span>
          <strong>{file?.name ?? "Choose or drop an image"}</strong>
          <small>{hint}</small>
        </span>
        <input
          id={inputId}
          aria-label={label}
          aria-required={required}
          type="file"
          accept="image/png,image/jpeg,image/webp"
          onChange={(event) => acceptFile(event.target.files?.[0])}
        />
      </label>
      {file ? (
        <button
          className={styles.clearFile}
          type="button"
          aria-label={`Remove ${label.toLowerCase()}`}
          onClick={() => onChange(null)}
        >
          <X aria-hidden="true" size={13} />
        </button>
      ) : null}
    </div>
  );
}

export function ImageEditPanel({
  job,
  isBusy,
  isSubmitting,
  isCanceling,
  hasError,
  canRetry,
  provider,
  providerStatusUnavailable,
  onSourcePreview,
  onSubmit,
  onCancel,
  onRetry,
}: Readonly<{
  job: ImageJobResponse | null;
  isBusy: boolean;
  isSubmitting: boolean;
  isCanceling: boolean;
  hasError: boolean;
  canRetry: boolean;
  provider: ImageProviderResponse | null;
  providerStatusUnavailable: boolean;
  onSourcePreview: (file: File | null) => void;
  onSubmit: (input: ImageEditJobCreate) => Promise<void>;
  onCancel: () => Promise<unknown>;
  onRetry: () => Promise<unknown>;
}>) {
  const [source, setSource] = useState<File | null>(null);
  const [faceReference, setFaceReference] = useState<File | null>(null);
  const [prompt, setPrompt] = useState("");
  const [aspectRatio, setAspectRatio] = useState<ImageEditJobCreate["aspectRatio"]>("4:3");
  const [style, setStyle] = useState<ImageEditJobCreate["style"]>("editorial");
  const [seed, setSeed] = useState("");
  const active = job?.status === "queued" || job?.status === "running";
  const canEdit = Boolean(source && prompt.trim()) && !isBusy && provider?.ready !== false;

  function updateSource(file: File | null) {
    setSource(file);
    onSourcePreview(file);
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canEdit || !source) return;
    const parsedSeed = seed === "" ? undefined : Number(seed);
    await onSubmit({
      prompt: prompt.trim(),
      aspectRatio,
      style,
      source,
      ...(faceReference ? { faceReference } : {}),
      ...(Number.isInteger(parsedSeed) ? { seed: parsedSeed } : {}),
    });
  }

  return (
    <section className={styles.editPanel} aria-labelledby="edit-panel-title">
      <header className={styles.panelHeading}>
        <div>
          <span>{provider?.label ?? "Image edit provider"}</span>
          <h2 id="edit-panel-title">Edit image</h2>
        </div>
        <span className={styles.modePill} data-mode={provider?.mode ?? "checking"}>
          {providerStatusUnavailable ? "Offline" : provider?.mode === "live" ? "Live" : "Demo"}
        </span>
      </header>

      <form className={styles.editForm} onSubmit={handleSubmit}>
        <ImageInput
          label="Source image"
          hint="PNG, JPEG or WebP up to 20 MB"
          file={source}
          required
          onChange={updateSource}
        />
        <ImageInput
          label="Identity reference"
          hint="Optional second edit reference"
          file={faceReference}
          onChange={setFaceReference}
        />

        <Field
          label="Edit prompt"
          htmlFor="edit-prompt"
          hint={provider?.message ?? "Checking the configured image edit workflow."}
        >
          <textarea
            className={styles.promptInput}
            id="edit-prompt"
            maxLength={1200}
            rows={4}
            value={prompt}
            onChange={(event) => setPrompt(event.target.value)}
            placeholder="Describe the intended change"
          />
        </Field>

        <div className={styles.settingGrid}>
          <Field label="Aspect ratio" htmlFor="edit-aspect-ratio">
            <Select
              id="edit-aspect-ratio"
              value={aspectRatio}
              onChange={(event) => setAspectRatio(event.target.value as ImageEditJobCreate["aspectRatio"])}
            >
              <option value="1:1">1:1 Square</option>
              <option value="4:3">4:3 Landscape</option>
              <option value="3:4">3:4 Portrait</option>
              <option value="16:9">16:9 Wide</option>
            </Select>
          </Field>
          <Field label="Style" htmlFor="edit-style">
            <Select
              id="edit-style"
              value={style}
              onChange={(event) => setStyle(event.target.value as ImageEditJobCreate["style"])}
            >
              <option value="editorial">Editorial</option>
              <option value="product">Product</option>
              <option value="concept">Concept</option>
            </Select>
          </Field>
        </div>

        <Field label="Seed (optional)" htmlFor="edit-seed">
          <input
            className={styles.seedInput}
            id="edit-seed"
            inputMode="numeric"
            min="0"
            max="2147483647"
            type="number"
            value={seed}
            onChange={(event) => setSeed(event.target.value)}
            placeholder="Derived from prompt"
          />
        </Field>

        <div className={styles.actions}>
          <Button variant="primary" type="submit" disabled={!canEdit}>
            <WandSparkles aria-hidden="true" size={16} />
            {isSubmitting ? "Submitting..." : active ? "Editing..." : "Generate edit"}
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
          <span>{job.status}</span>
          <strong>{job.progress === null ? "Progress unavailable" : `${job.progress}%`}</strong>
        </div>
      ) : null}

      {hasError ? (
        <div className={styles.editError} role="alert">
          <strong>{job?.error?.message ?? "Edit request failed"}</strong>
          <p>{job?.error?.action ?? "Check the local image workflow and try again."}</p>
          {canRetry ? (
            <Button type="button" onClick={() => void onRetry()}>
              <RotateCcw aria-hidden="true" size={14} />
              Retry
            </Button>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}
