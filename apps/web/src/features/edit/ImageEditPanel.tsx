"use client";

import {
  ArrowDown,
  ArrowUp,
  ChevronDown,
  Plus,
  RotateCcw,
  Square,
  Upload,
  WandSparkles,
  X,
} from "lucide-react";
import { type DragEvent, type FormEvent, useEffect, useId, useMemo, useRef, useState } from "react";

import { Button } from "@/components/ui/Button";
import { Field } from "@/components/ui/Field";
import { Select } from "@/components/ui/Select";
import type {
  ImageEditJobCreate,
  ImageEditLoraSelection,
  ImageEditProviderOptions,
  ImageJobResponse,
} from "@/lib/api/imageJobs";
import type { ImageProviderResponse } from "@/lib/api/imageProvider";

import styles from "./edit.module.css";

const ACCEPTED_TYPES = ["image/png", "image/jpeg", "image/webp"];

function useFilePreview(file: File | null) {
  const url = useMemo(() => (file ? URL.createObjectURL(file) : null), [file]);
  useEffect(() => () => { if (url) URL.revokeObjectURL(url); }, [url]);
  return url;
}

function ImageInput({
  label,
  hint,
  file,
  linkedPreview,
  linkedLabel,
  required,
  onChange,
  onClearLinked,
}: Readonly<{
  label: string;
  hint: string;
  file: File | null;
  linkedPreview?: string | null;
  linkedLabel?: string;
  required?: boolean;
  onChange: (file: File | null) => void;
  onClearLinked?: () => void;
}>) {
  const inputId = useId();
  const localPreview = useFilePreview(file);
  const preview = localPreview ?? linkedPreview;

  function acceptFile(nextFile: File | undefined) {
    if (nextFile && ACCEPTED_TYPES.includes(nextFile.type)) onChange(nextFile);
  }

  function handleDrop(event: DragEvent<HTMLLabelElement>) {
    event.preventDefault();
    acceptFile(event.dataTransfer.files[0]);
  }

  const filled = Boolean(file || linkedPreview);
  return (
    <div className={styles.fileField}>
      <div className={styles.fileLabel}>
        <strong>{label}</strong>
        <span>{required ? "Required" : "Optional"}</span>
      </div>
      <label
        className={styles.dropzone}
        data-filled={filled ? "true" : "false"}
        htmlFor={inputId}
        onDragOver={(event) => event.preventDefault()}
        onDrop={handleDrop}
      >
        {preview ? (
          // Blob and API input URLs must bypass Next image optimization.
          // eslint-disable-next-line @next/next/no-img-element
          <img src={preview} alt="" />
        ) : <Upload aria-hidden="true" size={18} />}
        <span>
          <strong>{file?.name ?? linkedLabel ?? "Choose or drop an image"}</strong>
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
      {filled ? (
        <button
          className={styles.clearFile}
          type="button"
          aria-label={`Remove ${label.toLowerCase()}`}
          onClick={() => { onChange(null); onClearLinked?.(); }}
        >
          <X aria-hidden="true" size={13} />
        </button>
      ) : null}
    </div>
  );
}

function phaseLabel(job: ImageJobResponse) {
  const labels: Record<ImageJobResponse["phase"], string> = {
    queued: "Queued",
    uploading: "Uploading inputs",
    preparing: "Preparing model",
    sampling: "Sampling",
    saving: "Saving result",
    completed: "Completed",
    failed: "Failed",
    canceled: "Canceled",
  };
  return labels[job.phase];
}

export function ImageEditPanel({
  job,
  sourceJob,
  sourceJobPreview,
  options,
  isBusy,
  isSubmitting,
  isCanceling,
  hasError,
  canRetry,
  provider,
  providerStatusUnavailable,
  onSourceJobChange,
  onSourcePreview,
  onSubmit,
  onCancel,
  onRetry,
}: Readonly<{
  job: ImageJobResponse | null;
  sourceJob: ImageJobResponse | null;
  sourceJobPreview: string | null;
  options: ImageEditProviderOptions | null;
  isBusy: boolean;
  isSubmitting: boolean;
  isCanceling: boolean;
  hasError: boolean;
  canRetry: boolean;
  provider: ImageProviderResponse | null;
  providerStatusUnavailable: boolean;
  onSourceJobChange: (job: ImageJobResponse | null) => void;
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
  const [steps, setSteps] = useState(8);
  const [cfg, setCfg] = useState(1);
  const [referenceInfluence, setReferenceInfluence] = useState(4);
  const [groundingResolution, setGroundingResolution] = useState(768);
  const [fitMode, setFitMode] = useState<ImageEditJobCreate["fitMode"]>("fit");
  const [sampler, setSampler] = useState("euler");
  const [scheduler, setScheduler] = useState("simple");
  const [loras, setLoras] = useState<ImageEditLoraSelection[]>([]);
  const restoredJobId = useRef<string | null>(null);
  const active = job?.status === "queued" || job?.status === "running";
  const canEdit = Boolean((source || sourceJob) && prompt.trim()) && !isBusy && provider?.ready !== false;

  useEffect(() => {
    if (!options) return;
    setSampler((current) => options.samplers.includes(current) ? current : options.defaults.sampler);
    setScheduler((current) => options.schedulers.includes(current) ? current : options.defaults.scheduler);
  }, [options]);

  useEffect(() => {
    if (!job || job.settings.operation !== "edit" || restoredJobId.current === job.id) return;
    restoredJobId.current = job.id;
    setPrompt(job.prompt);
    setAspectRatio(job.settings.aspectRatio);
    setStyle(job.settings.style);
    setSeed(String(job.settings.seed));
    const edit = job.settings.edit;
    if (!edit) return;
    setSteps(edit.steps);
    setCfg(edit.cfg);
    setReferenceInfluence(edit.referenceInfluence);
    setGroundingResolution(edit.groundingResolution);
    setFitMode(edit.fitMode);
    setSampler(edit.sampler);
    setScheduler(edit.scheduler);
    setLoras(edit.loras);
  }, [job]);

  function updateSource(file: File | null) {
    setSource(file);
    onSourcePreview(file);
    if (file) onSourceJobChange(null);
  }

  function restoreSettings(nextJob: ImageJobResponse, useResultAsSource = false) {
    setPrompt(nextJob.prompt);
    setAspectRatio(nextJob.settings.aspectRatio);
    setStyle(nextJob.settings.style);
    setSeed(String(nextJob.settings.seed));
    const edit = nextJob.settings.edit;
    if (edit) {
      setSteps(edit.steps);
      setCfg(edit.cfg);
      setReferenceInfluence(edit.referenceInfluence);
      setGroundingResolution(edit.groundingResolution);
      setFitMode(edit.fitMode);
      setSampler(edit.sampler);
      setScheduler(edit.scheduler);
      setLoras(edit.loras);
    }
    if (useResultAsSource) {
      setSource(null);
      onSourcePreview(null);
      onSourceJobChange(nextJob);
    }
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canEdit) return;
    const parsedSeed = seed === "" ? undefined : Number(seed);
    await onSubmit({
      prompt: prompt.trim(),
      aspectRatio,
      style,
      ...(source ? { source } : {}),
      ...(sourceJob ? { sourceJobId: sourceJob.id } : {}),
      ...(faceReference ? { faceReference } : {}),
      ...(Number.isInteger(parsedSeed) ? { seed: parsedSeed } : {}),
      steps,
      cfg,
      referenceInfluence,
      groundingResolution,
      fitMode,
      sampler,
      scheduler,
      loras,
    });
  }

  function addLora(id: string) {
    if (!id || loras.some((item) => item.id === id)) return;
    setLoras((current) => [...current, { id, modelWeight: 1, clipWeight: 1 }]);
  }

  function updateLora(index: number, patch: Partial<ImageEditLoraSelection>) {
    setLoras((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, ...patch } : item));
  }

  function moveLora(index: number, delta: number) {
    setLoras((current) => {
      const target = index + delta;
      if (target < 0 || target >= current.length) return current;
      const next = [...current];
      [next[index], next[target]] = [next[target], next[index]];
      return next;
    });
  }

  return (
    <section className={styles.editPanel} aria-labelledby="edit-panel-title">
      <header className={styles.panelHeading}>
        <div><span>{provider?.label ?? "Image edit provider"}</span><h2 id="edit-panel-title">Edit image</h2></div>
        <span className={styles.modePill} data-mode={provider?.mode ?? "checking"}>
          {providerStatusUnavailable ? "Offline" : provider?.mode === "live" ? "Live" : "Demo"}
        </span>
      </header>

      <form className={styles.editForm} onSubmit={handleSubmit}>
        <ImageInput
          label="Source image"
          hint="PNG, JPEG, WebP, or a completed Library result"
          file={source}
          linkedPreview={sourceJobPreview}
          linkedLabel={sourceJob ? "Library result" : undefined}
          required
          onChange={updateSource}
          onClearLinked={() => onSourceJobChange(null)}
        />
        <ImageInput
          label="Identity reference"
          hint="Optional second edit reference"
          file={faceReference}
          onChange={setFaceReference}
        />

        <Field label="Edit prompt" htmlFor="edit-prompt" hint={provider?.message ?? "Checking image edit workflow."}>
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
            <Select id="edit-aspect-ratio" value={aspectRatio} onChange={(event) => setAspectRatio(event.target.value as ImageEditJobCreate["aspectRatio"])}>
              <option value="1:1">1:1 Square</option><option value="4:3">4:3 Landscape</option>
              <option value="3:4">3:4 Portrait</option><option value="16:9">16:9 Wide</option>
            </Select>
          </Field>
          <Field label="Style" htmlFor="edit-style">
            <Select id="edit-style" value={style} onChange={(event) => setStyle(event.target.value as ImageEditJobCreate["style"])}>
              <option value="editorial">Editorial</option><option value="product">Product</option><option value="concept">Concept</option>
            </Select>
          </Field>
        </div>

        <Field label="Seed (optional)" htmlFor="edit-seed">
          <input className={styles.seedInput} id="edit-seed" inputMode="numeric" min="0" max="2147483647" type="number" value={seed} onChange={(event) => setSeed(event.target.value)} placeholder="Derived from prompt" />
        </Field>

        <details className={styles.advanced}>
          <summary><span>Advanced settings</span><ChevronDown aria-hidden="true" size={15} /></summary>
          <div className={styles.advancedBody}>
            <div className={styles.settingGrid}>
              <Field label="Steps" htmlFor="edit-steps"><input id="edit-steps" type="number" min="4" max="12" value={steps} onChange={(event) => setSteps(Number(event.target.value))} /></Field>
              <Field label="CFG" htmlFor="edit-cfg"><input id="edit-cfg" type="number" min="0" max="4" step="0.1" value={cfg} onChange={(event) => setCfg(Number(event.target.value))} /></Field>
              <Field label="Reference influence" htmlFor="edit-reference"><input id="edit-reference" type="number" min="0" max="10" step="0.1" value={referenceInfluence} onChange={(event) => setReferenceInfluence(Number(event.target.value))} /></Field>
              <Field label="Grounding" htmlFor="edit-grounding"><Select id="edit-grounding" value={groundingResolution} onChange={(event) => setGroundingResolution(Number(event.target.value))}><option value="384">384 px</option><option value="512">512 px</option><option value="768">768 px</option><option value="1024">1024 px</option></Select></Field>
              <Field label="Fit / Crop" htmlFor="edit-fit"><Select id="edit-fit" value={fitMode} onChange={(event) => setFitMode(event.target.value as ImageEditJobCreate["fitMode"])}><option value="fit">Fit</option><option value="crop">Crop</option></Select></Field>
              <Field label="Sampler" htmlFor="edit-sampler"><Select id="edit-sampler" value={sampler} onChange={(event) => setSampler(event.target.value)} disabled={!options?.samplers.length}>{options?.samplers.map((item) => <option key={item}>{item}</option>) ?? <option>euler</option>}</Select></Field>
              <Field label="Scheduler" htmlFor="edit-scheduler"><Select id="edit-scheduler" value={scheduler} onChange={(event) => setScheduler(event.target.value)} disabled={!options?.schedulers.length}>{options?.schedulers.map((item) => <option key={item}>{item}</option>) ?? <option>simple</option>}</Select></Field>
            </div>

            <div className={styles.loraSection}>
              <div className={styles.loraHeading}><strong>LoRA chain</strong><span>Applied top to bottom</span></div>
              <Select aria-label="Add LoRA" value="" onChange={(event) => addLora(event.target.value)} disabled={!options?.loras.length}>
                <option value="">Add allowed LoRA</option>
                {options?.loras.filter((option) => !loras.some((item) => item.id === option.id)).map((option) => <option key={option.id} value={option.id}>{option.label}</option>)}
              </Select>
              {loras.map((item, index) => (
                <div className={styles.loraRow} key={item.id}>
                  <strong>{options?.loras.find((option) => option.id === item.id)?.label ?? item.id}</strong>
                  <label>Model<input aria-label={`${item.id} model weight`} type="number" min="-3" max="10" step="0.05" value={item.modelWeight} onChange={(event) => updateLora(index, { modelWeight: Number(event.target.value) })} /></label>
                  <label>CLIP<input aria-label={`${item.id} CLIP weight`} type="number" min="-3" max="3" step="0.05" value={item.clipWeight} onChange={(event) => updateLora(index, { clipWeight: Number(event.target.value) })} /></label>
                  <div className={styles.loraActions}>
                    <button type="button" aria-label={`Move ${item.id} up`} onClick={() => moveLora(index, -1)} disabled={index === 0}><ArrowUp size={13} /></button>
                    <button type="button" aria-label={`Move ${item.id} down`} onClick={() => moveLora(index, 1)} disabled={index === loras.length - 1}><ArrowDown size={13} /></button>
                    <button type="button" aria-label={`Remove ${item.id}`} onClick={() => setLoras((current) => current.filter((entry) => entry.id !== item.id))}><X size={13} /></button>
                  </div>
                </div>
              ))}
              {!options?.loras.length ? <p className={styles.optionHint}>No public LoRA options are configured for this provider.</p> : null}
            </div>
          </div>
        </details>

        <div className={styles.actions}>
          <Button variant="primary" type="submit" disabled={!canEdit}><WandSparkles aria-hidden="true" size={16} />{isSubmitting ? "Submitting..." : active ? "Editing..." : "Generate edit"}</Button>
          {active ? <Button type="button" onClick={() => void onCancel()} disabled={isCanceling}><Square aria-hidden="true" size={14} />{isCanceling ? "Canceling..." : job?.phase === "queued" ? "Cancel queued" : "Interrupt"}</Button> : null}
        </div>
      </form>

      {job ? (
        <div className={styles.liveJob} aria-live="polite">
          <div><span>{phaseLabel(job)}</span>{job.currentStep !== null && job.totalSteps !== null ? <small>Step {job.currentStep} / {job.totalSteps}</small> : null}</div>
          <strong>{job.progress === null ? "Waiting for provider" : `${job.progress}%`}</strong>
          {job.estimatedRemainingSeconds !== null ? <small>About {job.estimatedRemainingSeconds}s remaining</small> : null}
          {job.stalled ? <p>Model preparation is taking longer than usual.</p> : null}
          {job.status === "completed" ? <Button type="button" variant="quiet" onClick={() => restoreSettings(job, true)}><Plus aria-hidden="true" size={14} />Edit again</Button> : null}
        </div>
      ) : null}

      {hasError ? (
        <div className={styles.editError} role="alert">
          <strong>{job?.error?.message ?? "Edit request failed"}</strong>
          <p>{job?.error?.action ?? "Check the local image workflow and try again."}</p>
          {canRetry ? <Button type="button" onClick={() => void onRetry()}><RotateCcw aria-hidden="true" size={14} />Retry</Button> : null}
        </div>
      ) : null}
    </section>
  );
}
