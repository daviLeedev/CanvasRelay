"use client";

import { ArrowDown, ArrowUp, ChevronDown, RotateCcw, Square, WandSparkles, X } from "lucide-react";
import { type FormEvent, useState } from "react";

import { Button } from "@/components/ui/Button";
import { Field } from "@/components/ui/Field";
import { Select } from "@/components/ui/Select";
import type {
  ImageGenerationProviderOptions,
  ImageJobCreate,
  ImageJobResponse,
} from "@/lib/api/imageJobs";
import type { ImageProviderResponse } from "@/lib/api/imageProvider";

import { DemoResultPreview } from "./DemoResultPreview";
import styles from "./studio.module.css";

type ImageGenerationPanelProps = {
  job: ImageJobResponse | null;
  isBusy: boolean;
  isSubmitting: boolean;
  isCanceling: boolean;
  hasError: boolean;
  canRetry: boolean;
  provider: ImageProviderResponse | null;
  options: ImageGenerationProviderOptions | null;
  providerStatusUnavailable: boolean;
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
  provider,
  options,
  providerStatusUnavailable,
  onSubmit,
  onCancel,
  onRetry,
}: Readonly<ImageGenerationPanelProps>) {
  const [prompt, setPrompt] = useState("");
  const [aspectRatio, setAspectRatio] = useState<ImageJobCreate["aspectRatio"]>("4:3");
  const [style, setStyle] = useState<ImageJobCreate["style"]>("editorial");
  const [seed, setSeed] = useState("");
  const [steps, setSteps] = useState(8);
  const [cfg, setCfg] = useState(1);
  const [shift, setShift] = useState(5);
  const [sampler, setSampler] = useState("euler");
  const [scheduler, setScheduler] = useState("beta");
  type GenerationSettings = NonNullable<ImageJobCreate["generation"]>;
  type GenerationLora = NonNullable<GenerationSettings["loras"]>[number];
  const [loras, setLoras] = useState<GenerationLora[]>([]);
  const canGenerate = prompt.trim().length > 0 && !isBusy && provider?.ready !== false;
  const selectedSampler = options?.samplers.includes(sampler)
    ? sampler
    : (options?.defaults.sampler ?? sampler);
  const selectedScheduler = options?.schedulers.includes(scheduler)
    ? scheduler
    : (options?.defaults.scheduler ?? scheduler);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canGenerate) return;
    const parsedSeed = seed === "" ? undefined : Number(seed);
    await onSubmit({
      prompt: prompt.trim(),
      aspectRatio,
      style,
      ...(Number.isInteger(parsedSeed) ? { seed: parsedSeed } : {}),
      generation: {
        steps,
        cfg,
        shift,
        sampler: selectedSampler,
        scheduler: selectedScheduler,
        loras,
      },
    });
  }

  function addLora(id: string) {
    if (!id || loras.some((item) => item.id === id)) return;
    setLoras((current) => [...current, { id, modelWeight: 1, clipWeight: 1 }]);
  }

  function updateLora(index: number, patch: Partial<GenerationLora>) {
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

  const active = job?.status === "queued" || job?.status === "running";
  const progressLabel = job?.progress === null ? "Unavailable" : `${job?.progress ?? 0}%`;
  const providerLabel = provider?.label ?? "Image provider";
  const providerMode = provider?.mode === "live" ? "Live" : "Demo";
  const stepLabel =
    job?.currentStep !== null && job?.currentStep !== undefined && job.totalSteps
      ? `Step ${job.currentStep} of ${job.totalSteps}`
      : null;

  return (
    <section className={styles.generationPanel} aria-labelledby="generation-panel-title">
      <header className={styles.panelHeading}>
        <div>
          <span>{providerLabel}</span>
          <h2 id="generation-panel-title">Create image</h2>
        </div>
        <span className={styles.demoPill} data-mode={provider?.mode ?? "checking"}>
          {providerStatusUnavailable ? "Offline" : providerMode}
        </span>
      </header>

      <form className={styles.generationForm} onSubmit={handleSubmit}>
        <div className={styles.promptField}>
          <div className={styles.fieldTopline}>
            <label htmlFor="image-prompt">Prompt</label>
            <span>{prompt.length} / 1200</span>
          </div>
          <textarea
            className={styles.promptInput}
            id="image-prompt"
            maxLength={1200}
            rows={4}
            value={prompt}
            onChange={(event) => setPrompt(event.target.value)}
            placeholder="Describe the image to relay"
          />
          <p className={styles.promptHint}>
            {provider?.message ?? "Checking the configured image provider."}
          </p>
        </div>

        <fieldset className={styles.settingsGroup}>
          <legend>Output setup</legend>
          <div className={styles.settingGrid}>
            <label className={styles.compactField} htmlFor="image-aspect-ratio">
              <span>Aspect ratio</span>
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
            </label>
            <label className={styles.compactField} htmlFor="image-style">
              <span>Style</span>
            <Select
              id="image-style"
              value={style}
              onChange={(event) => setStyle(event.target.value as ImageJobCreate["style"])}
            >
              <option value="editorial">Editorial</option>
              <option value="product">Product</option>
              <option value="concept">Concept</option>
            </Select>
            </label>
          </div>

          <label className={styles.compactField} htmlFor="image-seed">
            <span>Seed <small>Optional</small></span>
            <input
              className={styles.seedInput}
              id="image-seed"
              aria-label="Seed (optional)"
              inputMode="numeric"
              min="0"
              max="2147483647"
              type="number"
              value={seed}
              onChange={(event) => setSeed(event.target.value)}
              placeholder="Derived from prompt"
            />
          </label>
        </fieldset>

        <details className={styles.advancedSettings}>
          <summary>
            <span>Advanced settings</span>
            <ChevronDown aria-hidden="true" size={15} />
          </summary>
          <div className={styles.advancedSettingsBody}>
            <div className={styles.settingGrid}>
              <Field label="Steps" htmlFor="image-steps">
                <input id="image-steps" type="number" min="1" max="32" value={steps} onChange={(event) => setSteps(Number(event.target.value))} />
              </Field>
              <Field label="CFG" htmlFor="image-cfg">
                <input id="image-cfg" type="number" min="0" max="12" step="0.1" value={cfg} onChange={(event) => setCfg(Number(event.target.value))} />
              </Field>
              <Field label="Sampler" htmlFor="image-sampler">
                <Select id="image-sampler" value={selectedSampler} onChange={(event) => setSampler(event.target.value)} disabled={!options?.samplers.length}>
                  {options?.samplers.map((item) => <option key={item}>{item}</option>) ?? <option>{selectedSampler}</option>}
                </Select>
              </Field>
              <Field label="Scheduler" htmlFor="image-scheduler">
                <Select id="image-scheduler" value={selectedScheduler} onChange={(event) => setScheduler(event.target.value)} disabled={!options?.schedulers.length}>
                  {options?.schedulers.map((item) => <option key={item}>{item}</option>) ?? <option>{selectedScheduler}</option>}
                </Select>
              </Field>
              <Field label="Shift" htmlFor="image-shift" hint="Model sampling shift">
                <input id="image-shift" type="number" min="0" max="12" step="0.1" value={shift} onChange={(event) => setShift(Number(event.target.value))} />
              </Field>
            </div>

            <div className={styles.generationLoraSection}>
              <div className={styles.generationLoraHeading}>
                <strong>LoRA chain</strong>
                <span>Applied top to bottom</span>
              </div>
              <Select aria-label="Add generation LoRA" value="" onChange={(event) => addLora(event.target.value)} disabled={!options?.loras.length}>
                <option value="">Add allowed LoRA</option>
                {options?.loras.filter((option) => !loras.some((item) => item.id === option.id)).map((option) => <option key={option.id} value={option.id}>{option.label}</option>)}
              </Select>
              {loras.map((item, index) => (
                <div className={styles.generationLoraRow} key={item.id}>
                  <strong>{options?.loras.find((option) => option.id === item.id)?.label ?? item.id}</strong>
                  <label>Model<input aria-label={`${item.id} model weight`} type="number" min="-3" max="10" step="0.05" value={item.modelWeight} onChange={(event) => updateLora(index, { modelWeight: Number(event.target.value) })} /></label>
                  <label>CLIP<input aria-label={`${item.id} CLIP weight`} type="number" min="-3" max="3" step="0.05" value={item.clipWeight} onChange={(event) => updateLora(index, { clipWeight: Number(event.target.value) })} /></label>
                  <div className={styles.generationLoraActions}>
                    <button type="button" aria-label={`Move ${item.id} up`} onClick={() => moveLora(index, -1)} disabled={index === 0}><ArrowUp size={13} /></button>
                    <button type="button" aria-label={`Move ${item.id} down`} onClick={() => moveLora(index, 1)} disabled={index === loras.length - 1}><ArrowDown size={13} /></button>
                    <button type="button" aria-label={`Remove ${item.id}`} onClick={() => setLoras((current) => current.filter((entry) => entry.id !== item.id))}><X size={13} /></button>
                  </div>
                </div>
              ))}
              {!options?.loras.length ? <p className={styles.optionHint}>No allowed LoRA options are configured for this provider.</p> : null}
            </div>
          </div>
        </details>

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
          <div className={styles.runStatusRow}>
            <div>
              <span>Current run</span>
              <strong>{job.phase}</strong>
            </div>
            <div>
              {stepLabel ? <small>{stepLabel}</small> : null}
              <strong>{progressLabel}</strong>
            </div>
          </div>
          {job.progress !== null ? (
            <span className={styles.inspectorProgress} aria-hidden="true">
              <span style={{ width: `${job.progress}%` }} />
            </span>
          ) : null}
          {job.stalled ? (
            <p className={styles.stalledMessage}>The provider is taking longer than usual to prepare.</p>
          ) : null}
        </div>
      ) : null}

      {hasError ? (
        <div className={styles.generationError} role="alert">
          <strong>{job?.error?.message ?? "Generation request failed"}</strong>
          <p>
            {job?.error?.action ??
              "The image service could not finish the request. Check the provider status and try again."}
          </p>
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
