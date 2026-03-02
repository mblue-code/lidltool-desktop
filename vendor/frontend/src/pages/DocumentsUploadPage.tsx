import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery } from "@tanstack/react-query";
import { CheckCircle2, Loader2, UploadCloud, XCircle } from "lucide-react";
import { ChangeEvent, DragEvent, useEffect, useMemo, useRef, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";

import {
  DocumentProcessResponse,
  DocumentUploadResponse,
  fetchDocumentStatus,
  processDocument,
  uploadDocument
} from "@/api/documents";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";
import { jsonObjectStringSchema } from "@/lib/json-object-field";
import { formatDateTime } from "@/utils/format";

type TimelineEvent = {
  key: string;
  title: string;
  detail: string;
  createdAt: string;
};

type UploadStatus = "idle" | "uploading" | "processing" | "done" | "error";
type TerminalOcrStatus = "completed" | "failed";

const TERMINAL_OCR_STATUSES = new Set<TerminalOcrStatus>(["completed", "failed"]);

function isTerminalOcrStatus(status: string | undefined): status is TerminalOcrStatus {
  if (!status) {
    return false;
  }
  return TERMINAL_OCR_STATUSES.has(status as TerminalOcrStatus);
}

const uploadFormSchema = z.object({
  file: z
    .custom<File | null>((value) => value === null || value instanceof File)
    .refine((value): value is File => value instanceof File, {
      message: "Select a file before uploading."
    }),
  source: z.string().trim().min(1, "Source is required.").max(120, "Source must be 120 characters or less."),
  metadataJson: jsonObjectStringSchema("Metadata")
});

type UploadFormInput = z.input<typeof uploadFormSchema>;
type UploadFormOutput = z.output<typeof uploadFormSchema>;

const UPLOAD_STATE_CONFIG: Record<
  UploadStatus,
  { label: string; className: string; Icon: typeof Loader2 | null; spin?: boolean }
> = {
  idle:       { label: "Ready",           className: "bg-muted text-muted-foreground",     Icon: null },
  uploading:  { label: "Uploading…",      className: "bg-primary/10 text-primary",         Icon: Loader2, spin: true },
  processing: { label: "Processing OCR…", className: "bg-chart-3/10 text-chart-3",         Icon: Loader2, spin: true },
  done:       { label: "Complete",        className: "bg-success/10 text-success",          Icon: CheckCircle2 },
  error:      { label: "Failed",          className: "bg-destructive/10 text-destructive",  Icon: XCircle },
};

function UploadStateChip({ state }: { state: UploadStatus }): JSX.Element {
  const config = UPLOAD_STATE_CONFIG[state] ?? UPLOAD_STATE_CONFIG.idle;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium",
        config.className
      )}
    >
      {config.Icon ? (
        <config.Icon className={cn("h-3 w-3 shrink-0", config.spin && "animate-spin")} />
      ) : null}
      {config.label}
    </span>
  );
}

function ocrStatusClass(status: string): string {
  switch (status) {
    case "completed": return "border-transparent bg-success/15 text-success";
    case "failed":    return "border-transparent bg-destructive/15 text-destructive";
    default:          return "border-transparent bg-muted text-muted-foreground";
  }
}

export function DocumentsUploadPage(): JSX.Element {
  const [uploadResult, setUploadResult] = useState<DocumentUploadResponse | null>(null);
  const [processResult, setProcessResult] = useState<DocumentProcessResponse | null>(null);
  const [timeline, setTimeline] = useState<TimelineEvent[]>([]);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [dropActive, setDropActive] = useState<boolean>(false);
  const [uploadState, setUploadState] = useState<UploadStatus>("idle");

  const lastStatusRef = useRef<string | null>(null);

  const form = useForm<UploadFormInput, unknown, UploadFormOutput>({
    resolver: zodResolver(uploadFormSchema),
    defaultValues: {
      file: null,
      source: "ocr_upload",
      metadataJson: '{"channel":"manual_upload"}'
    }
  });

  const selectedFile = form.watch("file");

  const uploadMutation = useMutation({
    mutationFn: async (payload: {
      file: File;
      source: string;
      metadataJson: Record<string, unknown>;
    }) =>
      uploadDocument({
        file: payload.file,
        source: payload.source,
        metadata: payload.metadataJson
      })
  });

  const processMutation = useMutation({
    mutationFn: async (documentId: string) => processDocument(documentId)
  });

  const activeDocumentId = uploadResult?.document_id ?? null;
  const activeJobId = processResult?.job_id;

  const statusQuery = useQuery({
    queryKey: ["document-status", activeDocumentId, activeJobId],
    queryFn: () =>
      fetchDocumentStatus(activeDocumentId as string, {
        jobId: activeJobId
      }),
    enabled: Boolean(activeDocumentId),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return isTerminalOcrStatus(status) ? false : 2000;
    }
  });

  const currentStatus = statusQuery.data?.status || uploadResult?.status || "pending";

  useEffect(() => {
    if (!statusQuery.data || !activeDocumentId) {
      return;
    }
    const statusKey = `${statusQuery.data.status}:${statusQuery.data.review_status || "none"}`;
    if (lastStatusRef.current === statusKey) {
      return;
    }
    lastStatusRef.current = statusKey;
    const title = `Status ${statusQuery.data.status}`;
    const detail = `Review: ${statusQuery.data.review_status || "unknown"}${
      statusQuery.data.ocr_confidence !== null
        ? `, OCR confidence: ${statusQuery.data.ocr_confidence.toFixed(3)}`
        : ""
    }`;
    setTimeline((previous) => [
      {
        key: `${statusKey}:${Date.now()}`,
        title,
        detail,
        createdAt: new Date().toISOString()
      },
      ...previous
    ]);

    if (isTerminalOcrStatus(statusQuery.data.status)) {
      setUploadState(statusQuery.data.status === "completed" ? "done" : "error");
    }
  }, [activeDocumentId, statusQuery.data]);

  const timelineItems = useMemo(() => timeline.slice(0, 10), [timeline]);

  const handleUpload = form.handleSubmit(async (values) => {
    setStatusMessage(null);
    setErrorMessage(null);
    setUploadState("uploading");
    try {
      const result = await uploadMutation.mutateAsync(values);
      setUploadResult(result);
      setProcessResult(null);
      setTimeline([
        {
          key: `upload:${result.document_id}:${Date.now()}`,
          title: "Upload complete",
          detail: `Document ${result.document_id} stored with MIME ${result.mime_type}.`,
          createdAt: new Date().toISOString()
        }
      ]);
      lastStatusRef.current = null;
      setStatusMessage("Document uploaded. You can now trigger OCR processing.");
      setUploadState("idle");
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "Upload failed");
      setUploadState("error");
    }
  });

  async function handleProcess(): Promise<void> {
    if (!uploadResult) {
      return;
    }
    setStatusMessage(null);
    setErrorMessage(null);
    setUploadState("processing");
    try {
      const result = await processMutation.mutateAsync(uploadResult.document_id);
      setProcessResult(result);
      setTimeline((previous) => [
        {
          key: `process:${result.job_id}:${Date.now()}`,
          title: "Processing started",
          detail: `Job ${result.job_id} status: ${result.status}${result.reused ? " (reused)" : ""}.`,
          createdAt: new Date().toISOString()
        },
        ...previous
      ]);
      setStatusMessage("OCR processing triggered. Status will update automatically.");
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "Failed to start processing");
      setUploadState("error");
    }
  }

  function handleFileInputChange(event: ChangeEvent<HTMLInputElement>): void {
    const nextFile = event.target.files?.[0] || null;
    form.setValue("file", nextFile, {
      shouldDirty: true,
      shouldValidate: true
    });
  }

  function onDropFile(event: DragEvent<HTMLDivElement>): void {
    event.preventDefault();
    setDropActive(false);
    const file = event.dataTransfer.files?.[0] || null;
    if (file) {
      form.setValue("file", file, {
        shouldDirty: true,
        shouldValidate: true
      });
    }
  }

  function onDragOver(event: DragEvent<HTMLDivElement>): void {
    event.preventDefault();
    setDropActive(true);
  }

  function onDragLeave(event: DragEvent<HTMLDivElement>): void {
    event.preventDefault();
    setDropActive(false);
  }

  return (
    <section className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>OCR Document Upload</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div
            className={cn(
              "rounded-lg border border-dashed p-8 text-center transition-colors",
              dropActive ? "border-primary bg-primary/5" : "border-muted-foreground/25 hover:border-muted-foreground/40"
            )}
            onDrop={onDropFile}
            onDragOver={onDragOver}
            onDragLeave={onDragLeave}
            data-testid="upload-dropzone"
          >
            <UploadCloud
              className={cn(
                "mx-auto mb-3 h-10 w-10 transition-colors",
                dropActive ? "text-primary" : "text-muted-foreground/40"
              )}
            />
            <p className="text-sm font-medium">Drop a receipt here, or choose a file</p>
            <p className="mt-1 text-xs text-muted-foreground">
              PDF, image, or text — processed automatically by OCR.
            </p>
            <div className="mt-4 flex flex-wrap items-center justify-center gap-2">
              <Input
                aria-label="Choose document file"
                type="file"
                className="max-w-xs"
                onChange={handleFileInputChange}
              />
            </div>
            {selectedFile ? (
              <p className="mt-2 text-xs text-muted-foreground">{selectedFile.name}</p>
            ) : null}
            {form.formState.errors.file ? (
              <p className="mt-2 text-xs text-destructive">{form.formState.errors.file.message}</p>
            ) : null}
          </div>

          <div className="grid gap-3 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="document-source">Source</Label>
              <Input id="document-source" placeholder="ocr_upload" {...form.register("source")} />
              {form.formState.errors.source ? (
                <p className="text-xs text-destructive">{form.formState.errors.source.message}</p>
              ) : null}
            </div>
            <div className="space-y-2 md:col-span-2">
              <Label htmlFor="document-metadata">Metadata JSON</Label>
              <Textarea id="document-metadata" rows={5} {...form.register("metadataJson")} />
              {form.formState.errors.metadataJson ? (
                <p className="text-xs text-destructive">{form.formState.errors.metadataJson.message}</p>
              ) : null}
            </div>
          </div>

          <div className="flex flex-wrap gap-2">
            <Button
              type="button"
              onClick={() => void handleUpload()}
              disabled={!selectedFile || uploadMutation.isPending}
            >
              {uploadMutation.isPending ? "Uploading..." : "Upload document"}
            </Button>
            <Button
              type="button"
              variant="outline"
              aria-label={processMutation.isPending ? "Starting OCR process" : "Trigger OCR process"}
              onClick={() => void handleProcess()}
              disabled={!uploadResult || processMutation.isPending}
            >
              {processMutation.isPending ? "Starting…" : "Trigger OCR"}
            </Button>
            <UploadStateChip state={uploadState} />
            <span className="sr-only" aria-live="polite">
              State: {uploadState}
            </span>
          </div>

          {statusMessage ? (
            <Alert>
              <AlertTitle>Status</AlertTitle>
              <AlertDescription>{statusMessage}</AlertDescription>
            </Alert>
          ) : null}
          {errorMessage ? (
            <Alert variant="destructive">
              <AlertTitle>Action failed</AlertTitle>
              <AlertDescription>{errorMessage}</AlertDescription>
            </Alert>
          ) : null}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Status Timeline</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="outline" className="font-mono text-xs">
              {uploadResult?.document_id ? `doc: ${uploadResult.document_id}` : "No document yet"}
            </Badge>
            {processResult?.job_id ? (
              <Badge variant="outline" className="font-mono text-xs">
                job: {processResult.job_id}
              </Badge>
            ) : null}
            <Badge className={cn("text-xs", ocrStatusClass(currentStatus))}>
              {currentStatus}
            </Badge>
          </div>
          {timelineItems.length === 0 ? (
            <p className="text-sm text-muted-foreground">No timeline events yet.</p>
          ) : (
            <ol className="relative space-y-3 border-l-2 border-border pl-5">
              {timelineItems.map((event) => (
                <li key={event.key} className="relative">
                  <span className="absolute -left-[1.3125rem] top-1 h-2.5 w-2.5 rounded-full border-2 border-primary bg-background" />
                  <p className="text-sm font-medium">{event.title}</p>
                  <p className="text-xs text-muted-foreground">{event.detail}</p>
                  <p className="mt-0.5 text-xs text-muted-foreground/60">{formatDateTime(event.createdAt)}</p>
                </li>
              ))}
            </ol>
          )}
        </CardContent>
      </Card>
    </section>
  );
}
