import { useState, useEffect, useRef, useCallback } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import {
  Loader2,
  AlertCircle,
  Download,
  FileText,
  File,
  Archive,
  ArrowLeft,
  Copy,
  Check,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Progress } from "@/components/ui/progress";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { subscribeToJob, getJob, fetchTexSource, downloadUrl } from "@/lib/api";
import type { ProgressEvent, JobResponse } from "@/lib/types";

function humanStatus(event: ProgressEvent): string {
  switch (event.event_type) {
    case "job_started":
      return `Starting conversion of ${event.total_pages} page${event.total_pages !== 1 ? "s" : ""}...`;
    case "page_generating":
      return `Transcribing page ${event.page} of ${event.total_pages}...`;
    case "page_compiling":
      return `Compiling page ${event.page} of ${event.total_pages}...`;
    case "page_compiled_ok":
      return `Page ${event.page} compiled successfully`;
    case "page_fix_attempt":
      return `Fixing compilation errors on page ${event.page} (attempt ${event.retry} of ${event.max_retries})...`;
    case "page_done":
      return `Page ${event.page} of ${event.total_pages} done`;
    case "finalizing":
      return "Assembling final document...";
    case "job_completed":
      return "Conversion complete";
    case "job_failed":
      return event.message || "Conversion failed";
    default:
      return event.message || "Processing...";
  }
}

function ProcessingView({
  latestEvent,
}: {
  latestEvent: ProgressEvent | null;
}) {
  const totalPages = latestEvent?.total_pages ?? 0;
  const currentPage = latestEvent?.page ?? 0;
  // Count completed pages (page_done events advance this)
  const progressPercent =
    totalPages > 0 ? Math.round((currentPage / totalPages) * 100) : 0;
  const statusText = latestEvent ? humanStatus(latestEvent) : "Connecting...";

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Loader2 className="h-5 w-5 animate-spin" />
          Converting
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-2">
          <div className="flex justify-between text-sm">
            <span className="text-muted-foreground">{statusText}</span>
            {totalPages > 0 && (
              <span className="font-medium">{progressPercent}%</span>
            )}
          </div>
          <Progress value={progressPercent} />
        </div>
      </CardContent>
    </Card>
  );
}

function ResultView({ job }: { job: JobResponse }) {
  const [texSource, setTexSource] = useState<string | null>(null);
  const [texLoading, setTexLoading] = useState(false);
  const [copied, setCopied] = useState(false);

  const loadTex = useCallback(() => {
    if (texSource !== null || texLoading || !job.has_tex) return;
    setTexLoading(true);
    fetchTexSource(job.job_id)
      .then(setTexSource)
      .catch(() => setTexSource("Failed to load source."))
      .finally(() => setTexLoading(false));
  }, [job.job_id, job.has_tex, texSource, texLoading]);

  const copyTex = async () => {
    if (!texSource) return;
    await navigator.clipboard.writeText(texSource);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="space-y-6">
      {/* PDF preview */}
      {job.has_pdf && (
        <Card>
          <CardContent className="p-0">
            <iframe
              src={downloadUrl(job.job_id, "output.pdf")}
              className="w-full rounded-lg"
              style={{ height: "70vh" }}
              title="PDF Preview"
            />
          </CardContent>
        </Card>
      )}

      {!job.has_pdf && job.has_tex && (
        <Card>
          <CardContent className="py-4">
            <p className="text-sm text-yellow-600">
              PDF compilation failed, but the .tex source was saved. You can
              download it and compile manually.
            </p>
          </CardContent>
        </Card>
      )}

      {/* Tabs: Downloads / LaTeX Source */}
      <Tabs
        defaultValue="downloads"
        onValueChange={(v) => {
          if (v === "source") loadTex();
        }}
      >
        <TabsList>
          <TabsTrigger value="downloads">Downloads</TabsTrigger>
          {job.has_tex && (
            <TabsTrigger value="source">LaTeX Source</TabsTrigger>
          )}
        </TabsList>

        <TabsContent value="downloads">
          <Card>
            <CardContent className="py-4">
              <div className="grid gap-3">
                {job.has_pdf && (
                  <a href={downloadUrl(job.job_id, "output.pdf", true)}>
                    <Button
                      variant="outline"
                      className="w-full justify-start gap-2"
                    >
                      <File className="h-4 w-4" />
                      Download PDF
                      <Download className="h-4 w-4 ml-auto" />
                    </Button>
                  </a>
                )}
                {job.has_tex && (
                  <a href={downloadUrl(job.job_id, "output.tex", true)}>
                    <Button
                      variant="outline"
                      className="w-full justify-start gap-2"
                    >
                      <FileText className="h-4 w-4" />
                      Download .tex Source
                      <Download className="h-4 w-4 ml-auto" />
                    </Button>
                  </a>
                )}
                <a href={downloadUrl(job.job_id, "all.zip", true)}>
                  <Button
                    variant="outline"
                    className="w-full justify-start gap-2"
                  >
                    <Archive className="h-4 w-4" />
                    Download All (.zip)
                    <Download className="h-4 w-4 ml-auto" />
                  </Button>
                </a>
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        {job.has_tex && (
          <TabsContent value="source">
            <Card>
              <CardContent className="py-4 space-y-3">
                <div className="flex justify-end">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={copyTex}
                    disabled={!texSource}
                  >
                    {copied ? (
                      <>
                        <Check className="mr-2 h-3 w-3" />
                        Copied
                      </>
                    ) : (
                      <>
                        <Copy className="mr-2 h-3 w-3" />
                        Copy to Clipboard
                      </>
                    )}
                  </Button>
                </div>
                {texLoading ? (
                  <p className="text-sm text-muted-foreground">Loading...</p>
                ) : (
                  <pre className="text-xs bg-muted rounded-md p-4 overflow-auto max-h-[60vh] whitespace-pre-wrap">
                    {texSource}
                  </pre>
                )}
              </CardContent>
            </Card>
          </TabsContent>
        )}
      </Tabs>

      <Button asChild className="w-full">
        <Link to="/">Convert Another</Link>
      </Button>
    </div>
  );
}

function FailedView({ errorMessage }: { errorMessage: string }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-destructive">
          <AlertCircle className="h-5 w-5" />
          Conversion Failed
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <p className="text-sm text-muted-foreground">{errorMessage}</p>
        <Button asChild>
          <Link to="/">Try Again</Link>
        </Button>
      </CardContent>
    </Card>
  );
}

export function JobPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [job, setJob] = useState<JobResponse | null>(null);
  const [latestEvent, setLatestEvent] = useState<ProgressEvent | null>(null);
  const [status, setStatus] = useState<
    "loading" | "processing" | "completed" | "failed"
  >("loading");
  const [errorMessage, setErrorMessage] = useState("");
  const unsubRef = useRef<(() => void) | null>(null);

  useEffect(() => {
    if (!id) return;

    // Fetch initial job state
    getJob(id)
      .then((j) => {
        setJob(j);
        if (j.status === "completed") {
          setStatus("completed");
          return;
        }
        if (j.status === "failed") {
          setStatus("failed");
          setErrorMessage(j.error_message ?? "Unknown error");
          return;
        }

        // Job is pending/processing — connect SSE (replays all past events)
        setStatus("processing");
        const unsub = subscribeToJob(
          id,
          (event: ProgressEvent) => {
            setLatestEvent(event);
            if (event.event_type === "job_completed") {
              // Refetch job to get has_pdf/has_tex
              getJob(id).then((updated) => {
                setJob(updated);
                setStatus("completed");
              });
            } else if (event.event_type === "job_failed") {
              setStatus("failed");
              setErrorMessage(event.message);
            }
          },
          undefined,
          () => {
            // SSE error — job might have finished while we were away
            getJob(id).then((j) => {
              setJob(j);
              if (j.status === "completed") setStatus("completed");
              else if (j.status === "failed") {
                setStatus("failed");
                setErrorMessage(j.error_message ?? "Unknown error");
              }
              // If still processing but SSE is gone (server restart), show last known state
            });
          },
        );
        unsubRef.current = unsub;
      })
      .catch(() => {
        navigate("/");
      });

    return () => {
      unsubRef.current?.();
    };
  }, [id, navigate]);

  if (status === "loading") {
    return (
      <div className="container mx-auto max-w-4xl py-8 px-4 text-center text-muted-foreground">
        Loading...
      </div>
    );
  }

  return (
    <div className="container mx-auto max-w-4xl py-8 px-4">
      <Button variant="ghost" size="sm" className="mb-6 -ml-2" asChild>
        <Link to="/">
          <ArrowLeft className="mr-2 h-4 w-4" />
          Back
        </Link>
      </Button>

      {status === "processing" && <ProcessingView latestEvent={latestEvent} />}
      {status === "completed" && job && <ResultView job={job} />}
      {status === "failed" && <FailedView errorMessage={errorMessage} />}
    </div>
  );
}
