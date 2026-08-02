"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowDown,
  ArrowUp,
  ImagePlus,
  LoaderCircle,
  Trash2,
  Upload,
} from "lucide-react";
import Image from "next/image";
import { useEffect, useMemo, useRef, useState } from "react";

import { Button } from "@/components/ui/Button";
import { Field } from "@/components/ui/Field";
import { Select } from "@/components/ui/Select";
import { StatusIndicator } from "@/components/ui/StatusIndicator";
import {
  cancelImageJob,
  createGPTImageJob,
  fetchImageJob,
  fetchImageJobs,
  fetchOwnerConnection,
  getImageAssetUrls,
  type GPTImageJobInput,
  type ImageJobResponse,
} from "@/lib/api/imageJobs";

import styles from "./gpt-image.module.css";

type Reference = { id: string; file: File; url: string };

const initialInput: Omit<GPTImageJobInput, "references" | "prompt"> = {
  aspectRatio: "1:1",
  style: "editorial",
  mode: "generate",
  quality: "auto",
  size: "1024x1024",
  count: 1,
  moderation: "auto",
  reasoningEffort: "none",
  webSearch: false,
};

function connectionTone(connected: boolean): "success" | "warning" | "danger" {
  return connected ? "success" : "warning";
}

function phaseLabel(job: ImageJobResponse | null) {
  if (!job) return "Ready";
  if (job.status === "completed") return "Completed";
  if (job.status === "failed") return "Failed";
  if (job.status === "canceled") return "Canceled";
  return job.phase === "queued" ? "Queued" : job.phase === "saving" ? "Saving result" : "Generating";
}

export function GPTImageWorkspace() {
  const queryClient = useQueryClient();
  const inputRef = useRef<HTMLInputElement>(null);
  const [prompt, setPrompt] = useState("");
  const [settings, setSettings] = useState(initialInput);
  const [references, setReferences] = useState<Reference[]>([]);
  const referencesRef = useRef<Reference[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const connection = useQuery({ queryKey: ["owner-codex-connection"], queryFn: fetchOwnerConnection, retry: false });
  const recent = useQuery({
    queryKey: ["image-jobs", "recent", "owner-gpt"],
    queryFn: () => fetchImageJobs(24),
    placeholderData: (previous) => previous,
  });
  const gptJobs = useMemo(
    () => (recent.data ?? []).filter((job) => String(job.settings.provider) === "openai_oauth"),
    [recent.data],
  );
  const activeId = selectedId ?? gptJobs[0]?.id ?? null;
  const selected = useQuery({
    queryKey: ["image-job", activeId],
    queryFn: ({ signal }) => fetchImageJob(activeId ?? "", signal),
    enabled: activeId !== null,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "queued" || status === "running" ? 900 : false;
    },
  });
  const job = selected.data ?? gptJobs.find((item) => item.id === activeId) ?? null;
  const active = job?.status === "queued" || job?.status === "running";
  const create = useMutation({
    mutationFn: createGPTImageJob,
    onSuccess: (next) => {
      queryClient.setQueryData(["image-job", next.id], next);
      queryClient.setQueryData<ImageJobResponse[]>(["image-jobs", "recent", "owner-gpt"], (current = []) => [
        next,
        ...current.filter((item) => item.id !== next.id),
      ]);
      setSelectedId(next.id);
    },
  });
  const cancel = useMutation({
    mutationFn: cancelImageJob,
    onSuccess: (next) => {
      queryClient.setQueryData(["image-job", next.id], next);
      void queryClient.invalidateQueries({ queryKey: ["image-jobs", "recent", "owner-gpt"] });
    },
  });

  useEffect(() => {
    referencesRef.current = references;
  }, [references]);
  useEffect(() => () => {
    referencesRef.current.forEach((reference) => URL.revokeObjectURL(reference.url));
  }, []);
  useEffect(() => {
    if (job?.status !== "completed" && job?.status !== "failed") return;
    const showTimer = window.setTimeout(() => {
      setToast(job.status === "completed" ? "GPT image completed." : "GPT image did not complete.");
    }, 0);
    const hideTimer = window.setTimeout(() => setToast(null), 3800);
    return () => {
      window.clearTimeout(showTimer);
      window.clearTimeout(hideTimer);
    };
  }, [job?.id, job?.status]);

  const outputUrls = job ? getImageAssetUrls(job) : [];
  const canSubmit = prompt.trim().length > 0 && !active && !create.isPending &&
    (settings.mode !== "edit" || references.length > 0) && references.length <= 5;

  function addReferences(files: FileList | null) {
    if (!files) return;
    const usable = [...files].filter((file) => file.type === "image/png" || file.type === "image/jpeg" || file.type === "image/webp");
    const remaining = Math.max(0, 5 - references.length);
    const next = usable.slice(0, remaining).map((file) => ({ id: crypto.randomUUID(), file, url: URL.createObjectURL(file) }));
    if (usable.length > remaining) setToast("Only five reference images can be used for one GPT image job.");
    setReferences((current) => [...current, ...next]);
  }

  function removeReference(id: string) {
    setReferences((current) => {
      const removed = current.find((item) => item.id === id);
      if (removed) URL.revokeObjectURL(removed.url);
      return current.filter((item) => item.id !== id);
    });
  }

  function moveReference(id: string, direction: -1 | 1) {
    setReferences((current) => {
      const index = current.findIndex((item) => item.id === id);
      const target = index + direction;
      if (index < 0 || target < 0 || target >= current.length) return current;
      const next = [...current];
      [next[index], next[target]] = [next[target], next[index]];
      return next;
    });
  }

  async function submit() {
    if (!canSubmit) return;
    try {
      await create.mutateAsync({ prompt: prompt.trim(), references: references.map((item) => item.file), ...settings });
    } catch {
      setToast("The owner GPT connection could not start this image. Check Settings and try again.");
    }
  }

  return (
    <div className={styles.workspace}>
      <header className={styles.toolbar}>
        <div><span>Owner-connected provider</span><h1>GPT image</h1></div>
        <div className={styles.toolbarStatus}>
          {connection.isPending ? <StatusIndicator label="Checking owner connection" tone="warning" /> : null}
          {connection.data ? <StatusIndicator label={connection.data.connected ? "Owner connection ready" : "Owner connection unavailable"} tone={connectionTone(connection.data.connected)} /> : null}
        </div>
      </header>

      <div className={styles.contentGrid}>
        <main className={styles.stage} aria-label="GPT image result stage">
          <header className={styles.stageHeader}><span>Result</span><strong>{phaseLabel(job)}</strong></header>
          <div className={styles.outputSurface}>
            {outputUrls.length > 0 ? (
              <div className={styles.outputGrid} data-count={outputUrls.length}>
                {outputUrls.map((url, index) => <figure className={styles.outputImage} key={url}><Image src={url} alt={`Generated result ${index + 1}`} fill sizes="(max-width: 760px) 100vw, (max-width: 1160px) 60vw, 72vw" unoptimized priority={index === 0} /></figure>)}
              </div>
            ) : active ? (
              <div className={styles.processing}><LoaderCircle aria-hidden="true" size={28} /><strong>{phaseLabel(job)}</strong><span>Provider progress is shown only when it is available.</span></div>
            ) : job?.status === "failed" ? (
              <div className={styles.processing}><ImagePlus aria-hidden="true" size={28} /><strong>Generation did not complete</strong><span>{job.error?.action ?? "Check the local owner connection and try again."}</span></div>
            ) : (
              <div className={styles.processing}><ImagePlus aria-hidden="true" size={28} /><strong>Compose an image request</strong><span>The final image appears here. Reference images stay in the controls.</span></div>
            )}
          </div>
        </main>

        <aside className={styles.inspector} aria-label="GPT image controls">
          <section className={styles.composer}>
            <header><div><span>Request</span><h2>Generate or edit</h2></div><span className={styles.ownerLabel}>Owner connection</span></header>
            <div className={styles.form}>
              <Field label="Mode" htmlFor="gpt-image-mode">
                <Select id="gpt-image-mode" value={settings.mode} onChange={(event) => setSettings((current) => ({ ...current, mode: event.target.value as GPTImageJobInput["mode"] }))}>
                  <option value="generate">Generate</option><option value="edit">Edit with references</option>
                </Select>
              </Field>
              <Field label="Prompt" htmlFor="gpt-image-prompt" hint={settings.mode === "edit" ? "Reference order is sent with the request." : "Reference images are optional for generation."}>
                <textarea id="gpt-image-prompt" className={styles.prompt} value={prompt} onChange={(event) => setPrompt(event.target.value)} placeholder="Describe the image you want to create." />
              </Field>
              <div className={styles.referenceHeader}><div><strong>References</strong><span>{references.length}/5 images</span></div><Button variant="secondary" onClick={() => inputRef.current?.click()} disabled={references.length >= 5 || active}><Upload aria-hidden="true" size={15} /> Add</Button></div>
              <input ref={inputRef} className={styles.hiddenInput} type="file" accept="image/png,image/jpeg,image/webp" multiple onChange={(event) => { addReferences(event.target.files); event.currentTarget.value = ""; }} />
              {references.length > 0 ? <ol className={styles.referenceList}>{references.map((reference, index) => <li key={reference.id}><span className={styles.referenceThumb}><Image src={reference.url} alt={`Reference ${index + 1}`} fill sizes="64px" unoptimized /></span><div><strong>{reference.file.name}</strong><span>Reference {index + 1}</span></div><div className={styles.referenceActions}><button type="button" aria-label="Move reference earlier" onClick={() => moveReference(reference.id, -1)} disabled={index === 0 || active}><ArrowUp size={14} /></button><button type="button" aria-label="Move reference later" onClick={() => moveReference(reference.id, 1)} disabled={index === references.length - 1 || active}><ArrowDown size={14} /></button><button type="button" aria-label="Remove reference" onClick={() => removeReference(reference.id)} disabled={active}><Trash2 size={14} /></button></div></li>)}</ol> : <p className={styles.referenceEmpty}>No references selected.</p>}
              <div className={styles.settingGrid}>
                <Field label="Quality" htmlFor="gpt-quality"><Select id="gpt-quality" value={settings.quality} onChange={(event) => setSettings((current) => ({ ...current, quality: event.target.value as GPTImageJobInput["quality"] }))}><option value="auto">Auto</option><option value="low">Low</option><option value="medium">Medium</option><option value="high">High</option></Select></Field>
                <Field label="Size" htmlFor="gpt-size"><Select id="gpt-size" value={settings.size} onChange={(event) => setSettings((current) => ({ ...current, size: event.target.value as GPTImageJobInput["size"] }))}><option value="1024x1024">Square</option><option value="1024x1536">Portrait</option><option value="1536x1024">Landscape</option></Select></Field>
                <Field label="Results" htmlFor="gpt-count"><Select id="gpt-count" value={settings.count} onChange={(event) => setSettings((current) => ({ ...current, count: Number(event.target.value) as 1 | 2 }))}><option value={1}>1 image</option><option value={2}>2 images</option></Select></Field>
                <Field label="Moderation" htmlFor="gpt-moderation"><Select id="gpt-moderation" value={settings.moderation} onChange={(event) => setSettings((current) => ({ ...current, moderation: event.target.value as GPTImageJobInput["moderation"] }))}><option value="auto">Auto</option><option value="low">Low</option></Select></Field>
              </div>
              <details className={styles.advanced}><summary>Advanced request options</summary><div><Field label="Reasoning" htmlFor="gpt-reasoning"><Select id="gpt-reasoning" value={settings.reasoningEffort} onChange={(event) => setSettings((current) => ({ ...current, reasoningEffort: event.target.value as GPTImageJobInput["reasoningEffort"] }))}><option value="none">Off</option><option value="low">Low</option><option value="medium">Medium</option><option value="high">High</option></Select></Field><label className={styles.check}><input type="checkbox" checked={settings.webSearch} onChange={(event) => setSettings((current) => ({ ...current, webSearch: event.target.checked }))} /> Use web search when supported</label></div></details>
              {job?.status === "failed" ? <p className={styles.error}>{job.error?.message ?? "The GPT image request did not complete."}</p> : null}
              <div className={styles.actions}><Button variant="primary" onClick={submit} disabled={!canSubmit}>{create.isPending ? "Submitting" : settings.mode === "edit" ? "Create edit" : "Generate image"}</Button>{active ? <Button variant="quiet" onClick={() => void cancel.mutateAsync(job.id)} disabled={cancel.isPending}>Cancel</Button> : null}</div>
            </div>
          </section>
          <section className={styles.recent}><header><div><span>Recent</span><h2>GPT image jobs</h2></div><strong>{gptJobs.length}</strong></header>{gptJobs.length ? <div>{gptJobs.map((item) => <button type="button" key={item.id} data-selected={item.id === job?.id} onClick={() => setSelectedId(item.id)}><span>{item.status}</span><strong>{item.prompt}</strong><small>{new Date(item.createdAt).toLocaleString()}</small></button>)}</div> : <p>No saved GPT image jobs yet.</p>}</section>
        </aside>
      </div>
      {toast ? <div className={styles.toast} role="status" aria-live="polite">{toast}</div> : null}
    </div>
  );
}
