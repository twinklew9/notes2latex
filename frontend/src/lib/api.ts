import type { JobResponse, ProgressEvent } from "./types";

const API_BASE = "/api/v1";

export async function listJobs(): Promise<JobResponse[]> {
  const res = await fetch(`${API_BASE}/jobs`);
  if (!res.ok) throw new Error("Failed to fetch jobs");
  return res.json();
}

export async function createJob(
  files: File[],
  config: {
    model?: string;
    api_key?: string;
    max_retries?: number;
    dpi?: number;
  },
): Promise<JobResponse> {
  const form = new FormData();
  for (const file of files) {
    form.append("files", file);
  }
  form.append("config", JSON.stringify(config));

  const res = await fetch(`${API_BASE}/jobs`, { method: "POST", body: form });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "Failed to create job");
  }
  return res.json();
}

export async function getJob(jobId: string): Promise<JobResponse> {
  const res = await fetch(`${API_BASE}/jobs/${jobId}`);
  if (!res.ok) throw new Error("Failed to fetch job");
  return res.json();
}

export async function fetchTexSource(jobId: string): Promise<string> {
  const res = await fetch(`${API_BASE}/jobs/${jobId}/download/output.tex`);
  if (!res.ok) throw new Error("Failed to fetch .tex source");
  return res.text();
}

export function subscribeToJob(
  jobId: string,
  onEvent: (event: ProgressEvent) => void,
  onDone?: () => void,
  onError?: (err: Error) => void,
): () => void {
  const source = new EventSource(`${API_BASE}/jobs/${jobId}/events`);

  const handler = (e: MessageEvent) => {
    const data: ProgressEvent = JSON.parse(e.data);
    onEvent(data);
    if (
      data.event_type === "job_completed" ||
      data.event_type === "job_failed"
    ) {
      source.close();
      onDone?.();
    }
  };

  const eventTypes = [
    "job_started",
    "page_generating",
    "page_compiling",
    "page_compiled_ok",
    "page_fix_attempt",
    "page_done",
    "finalizing",
    "job_completed",
    "job_failed",
  ];
  for (const type of eventTypes) {
    source.addEventListener(type, handler);
  }

  source.onerror = () => {
    source.close();
    onError?.(new Error("SSE connection lost"));
  };

  return () => source.close();
}

export function downloadUrl(
  jobId: string,
  filename: string,
  forceDownload = false,
): string {
  const base = `${API_BASE}/jobs/${jobId}/download/${filename}`;
  return forceDownload ? `${base}?download=true` : base;
}
