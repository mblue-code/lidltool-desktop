import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Link2, Loader2, MessageSquarePlus, Pencil, ReceiptText, RefreshCw, RotateCcw, Send, ShieldCheck, Table, Upload, X, Zap } from "lucide-react";
import { FormEvent, useMemo, useState } from "react";

import {
  approveIngestionProposal,
  batchApproveIngestionProposals,
  batchCommitIngestionProposals,
  batchRejectIngestionProposals,
  classifyIngestionRows,
  commitIngestionProposal,
  createIngestionSession,
  fetchIngestionAgentSettings,
  IngestionMatchCandidate,
  IngestionProposal,
  parseIngestionFile,
  parseIngestionPastedTable,
  isCreateTransactionPayload,
  refreshIngestionProposalMatches,
  rejectIngestionProposal,
  sendIngestionMessage,
  StatementRow,
  updateIngestionProposal,
  updateIngestionAgentSettings,
  undoIngestionProposal,
  uploadIngestionFile
} from "@/api/ingestion";
import { PageHeader } from "@/components/shared/PageHeader";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { useI18n } from "@/i18n";
import { resolveApiErrorMessage } from "@/lib/backend-messages";
import { formatEurFromCents } from "@/utils/format";

type EditableProposal = {
  merchant_name: string;
  purchased_at: string;
  total: string;
  currency: string;
  source_account_ref: string;
};

function toLocalDateTimeValue(isoValue: string): string {
  const date = new Date(isoValue);
  if (Number.isNaN(date.valueOf())) {
    return "";
  }
  const local = new Date(date.getTime() - date.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 16);
}

function localDateTimeToIso(value: string): string | null {
  const date = new Date(value);
  if (Number.isNaN(date.valueOf())) {
    return null;
  }
  return date.toISOString();
}

function amountInputFromCents(cents: number): string {
  return (cents / 100).toFixed(2);
}

function amountInputToCents(value: string): number | null {
  const parsed = Number(value.trim().replace(",", "."));
  if (!Number.isFinite(parsed) || parsed < 0) {
    return null;
  }
  return Math.round(parsed * 100);
}

function editableFromProposal(proposal: IngestionProposal): EditableProposal | null {
  if (!isCreateTransactionPayload(proposal.payload_json)) {
    return null;
  }
  return {
    merchant_name: proposal.payload_json.merchant_name,
    purchased_at: toLocalDateTimeValue(proposal.payload_json.purchased_at),
    total: amountInputFromCents(proposal.payload_json.total_gross_cents),
    currency: proposal.payload_json.currency,
    source_account_ref: proposal.payload_json.source_account_ref ?? "cash"
  };
}

function statusTone(status: string): string {
  if (status === "committed") {
    return "border-emerald-500/30 bg-emerald-500/5 text-emerald-700 dark:text-emerald-300";
  }
  if (status === "approved" || status === "auto_approved") {
    return "border-blue-500/30 bg-blue-500/5 text-blue-700 dark:text-blue-300";
  }
  if (status === "rejected" || status === "failed") {
    return "border-destructive/30 bg-destructive/5 text-destructive";
  }
  return "border-border bg-muted/40 text-muted-foreground";
}

export function IngestionPage() {
  const { locale, t } = useI18n();
  const queryClient = useQueryClient();
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [input, setInput] = useState("");
  const [pastedTable, setPastedTable] = useState("");
  const [proposals, setProposals] = useState<IngestionProposal[]>([]);
  const [rows, setRows] = useState<StatementRow[]>([]);
  const [drafts, setDrafts] = useState<Record<string, EditableProposal>>({});
  const [matchCandidates, setMatchCandidates] = useState<Record<string, IngestionMatchCandidate[]>>({});
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const copy = locale === "de"
    ? {
        title: "Ingestion",
        description: "Erfasse lose Ausgaben als prüfbare Vorschläge, bevor etwas ins Ledger geschrieben wird.",
        inputLabel: "Text eingeben",
        inputPlaceholder: "Ich habe heute 25 Euro bar im Eisladen bezahlt.",
        tablePlaceholder: "Datum;Empfänger;Beschreibung;Betrag;Währung\n30.04.2026;Bäckerei;Frühstück;-4,20;EUR",
        send: "Vorschlag erstellen",
        uploadCsv: "CSV hochladen",
        parseTable: "Tabelle parsen",
        classifyRows: "Zeilen klassifizieren",
        parsedRows: "Geparste Zeilen",
        reviewFirst: "Review First",
        yoloAuto: "YOLO Auto",
        reviewFirstDescription: "Review First ist Standard. YOLO Auto committet nur sichere, hoch-konfidente Vorschläge.",
        proposals: "Vorschläge",
        empty: "Noch keine Vorschläge. Gib eine Ausgabe ein, um den Review-Fluss zu starten.",
        merchant: "Händler",
        purchasedAt: "Datum",
        amount: "Betrag",
        currency: "Währung",
        source: "Quelle",
        save: "Änderungen speichern",
        approve: "Freigeben",
        reject: "Ablehnen",
        commit: "Commit",
        committed: "Transaktion erstellt",
        createFailed: "Ingestion konnte nicht verarbeitet werden",
        confidence: "Konfidenz",
        commitResult: "Commit-Ergebnis",
        refreshMatches: "Matches suchen",
        alreadyCovered: "Schon abgedeckt",
        createNewAnyway: "Neu erstellen",
        batchApprove: "Bereite freigeben",
        batchCommit: "Freigegebene committen",
        batchReject: "Offene ablehnen",
        undo: "Rückgängig",
        unsupported: "Dieser Vorschlagstyp hat keine direkten Bearbeitungsfelder."
      }
    : {
        title: "Ingestion",
        description: "Turn loose spending notes into reviewable proposals before anything is written to the ledger.",
        inputLabel: "Input",
        inputPlaceholder: "I paid 25 euros cash at the ice cream store today.",
        tablePlaceholder: "Date,Payee,Description,Amount,Currency\n2026-04-30,Ice Cream Store,Cash,-5.50,EUR",
        send: "Create proposal",
        uploadCsv: "Upload CSV",
        parseTable: "Parse table",
        classifyRows: "Classify rows",
        parsedRows: "Parsed rows",
        reviewFirst: "Review First",
        yoloAuto: "YOLO Auto",
        reviewFirstDescription: "Review First is the default. YOLO Auto only commits safe high-confidence proposals.",
        proposals: "Proposals",
        empty: "No proposals yet. Enter an expense to start the review flow.",
        merchant: "Merchant",
        purchasedAt: "Date",
        amount: "Amount",
        currency: "Currency",
        source: "Source",
        save: "Save edits",
        approve: "Approve",
        reject: "Reject",
        commit: "Commit",
        committed: "Transaction created",
        createFailed: "Ingestion could not be processed",
        confidence: "Confidence",
        commitResult: "Commit result",
        refreshMatches: "Find matches",
        alreadyCovered: "Already covered",
        createNewAnyway: "Create new anyway",
        batchApprove: "Approve ready",
        batchCommit: "Commit approved",
        batchReject: "Reject open",
        undo: "Undo",
        unsupported: "This proposal type has no direct edit fields."
      };

  const settingsQuery = useQuery({
    queryKey: ["ingestion-agent-settings"],
    queryFn: fetchIngestionAgentSettings
  });
  const settingsMutation = useMutation({
    mutationFn: updateIngestionAgentSettings,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["ingestion-agent-settings"] });
    }
  });
  const approvalMode = settingsQuery.data?.approval_mode ?? "review_first";

  const createSessionMutation = useMutation({ mutationFn: createIngestionSession });
  async function ensureSession(inputKind = "free_text"): Promise<string> {
    if (sessionId) {
      return sessionId;
    }
    const created = await createSessionMutation.mutateAsync({
      title: inputKind === "csv" ? "Statement intake" : "Manual text intake",
      input_kind: inputKind,
      approval_mode: approvalMode
    });
    setSessionId(created.id);
    return created.id;
  }

  const sendMessageMutation = useMutation({
    mutationFn: async (message: string) => {
      const activeSessionId = await ensureSession("free_text");
      return sendIngestionMessage(activeSessionId, message);
    },
    onSuccess: (result) => {
      setProposals((previous) => {
        const byId = new Map(previous.map((proposal) => [proposal.id, proposal]));
        for (const proposal of result.proposals) {
          byId.set(proposal.id, proposal);
        }
        return Array.from(byId.values());
      });
      setDrafts((previous) => {
        const next = { ...previous };
        for (const proposal of result.proposals) {
          const editable = editableFromProposal(proposal);
          if (editable) {
            next[proposal.id] = editable;
          }
        }
        return next;
      });
      setInput("");
      setNotice(null);
    }
  });
  const updateMutation = useMutation({ mutationFn: ({ id, payload }: { id: string; payload: Record<string, unknown> }) => updateIngestionProposal(id, { payload }) });
  const uploadMutation = useMutation({
    mutationFn: async (file: File) => {
      const activeSessionId = await ensureSession("csv");
      const uploaded = await uploadIngestionFile(activeSessionId, file);
      return parseIngestionFile(uploaded.id);
    },
    onSuccess: (result) => {
      setRows(result.items);
      if (result.proposals?.length) {
        appendProposals(result.proposals);
      }
    }
  });
  const pasteMutation = useMutation({
    mutationFn: async (text: string) => {
      const activeSessionId = await ensureSession("pasted_table");
      return parseIngestionPastedTable(activeSessionId, text);
    },
    onSuccess: (result) => setRows(result.items)
  });
  const classifyRowsMutation = useMutation({
    mutationFn: async () => {
      const activeSessionId = await ensureSession("csv");
      return classifyIngestionRows(activeSessionId);
    },
    onSuccess: (result) => {
      setProposals((previous) => {
        const byId = new Map(previous.map((proposal) => [proposal.id, proposal]));
        for (const proposal of result.items) {
          byId.set(proposal.id, proposal);
        }
        return Array.from(byId.values());
      });
    }
  });
  const approveMutation = useMutation({ mutationFn: approveIngestionProposal });
  const rejectMutation = useMutation({ mutationFn: rejectIngestionProposal });
  const refreshMatchesMutation = useMutation({ mutationFn: refreshIngestionProposalMatches });
  const commitMutation = useMutation({
    mutationFn: commitIngestionProposal,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["transactions"] });
    }
  });
  const undoMutation = useMutation({ mutationFn: undoIngestionProposal });
  const batchApproveMutation = useMutation({ mutationFn: batchApproveIngestionProposals });
  const batchCommitMutation = useMutation({ mutationFn: batchCommitIngestionProposals });
  const batchRejectMutation = useMutation({ mutationFn: batchRejectIngestionProposals });

  const summary = useMemo(() => {
    return {
      total: proposals.length,
      ready: proposals.filter((proposal) => proposal.status === "approved").length,
      committed: proposals.filter((proposal) => proposal.status === "committed").length
    };
  }, [proposals]);

  function appendProposals(items: IngestionProposal[]): void {
    setProposals((previous) => {
      const byId = new Map(previous.map((proposal) => [proposal.id, proposal]));
      for (const proposal of items) {
        byId.set(proposal.id, proposal);
      }
      return Array.from(byId.values());
    });
    setDrafts((previous) => {
      const next = { ...previous };
      for (const proposal of items) {
        const editable = editableFromProposal(proposal);
        if (editable) {
          next[proposal.id] = editable;
        }
      }
      return next;
    });
  }

  async function submitInput(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    setErrorMessage(null);
    const message = input.trim();
    if (!message) {
      return;
    }
    try {
      await sendMessageMutation.mutateAsync(message);
    } catch (error) {
      setErrorMessage(resolveApiErrorMessage(error, t, copy.createFailed));
    }
  }

  async function uploadCsvFile(file: File | null): Promise<void> {
    if (!file) {
      return;
    }
    setErrorMessage(null);
    try {
      await uploadMutation.mutateAsync(file);
    } catch (error) {
      setErrorMessage(resolveApiErrorMessage(error, t, copy.createFailed));
    }
  }

  async function parsePastedTable(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    const text = pastedTable.trim();
    if (!text) {
      return;
    }
    setErrorMessage(null);
    try {
      await pasteMutation.mutateAsync(text);
    } catch (error) {
      setErrorMessage(resolveApiErrorMessage(error, t, copy.createFailed));
    }
  }

  async function classifyRows(): Promise<void> {
    setErrorMessage(null);
    try {
      await classifyRowsMutation.mutateAsync();
    } catch (error) {
      setErrorMessage(resolveApiErrorMessage(error, t, copy.createFailed));
    }
  }

  function mergeProposal(next: IngestionProposal): void {
    setProposals((previous) => previous.map((proposal) => (proposal.id === next.id ? next : proposal)));
    const editable = editableFromProposal(next);
    if (editable) {
      setDrafts((previous) => ({ ...previous, [next.id]: editable }));
    }
  }

  async function saveProposal(proposal: IngestionProposal): Promise<IngestionProposal | null> {
    const editable = drafts[proposal.id];
    if (!editable || !isCreateTransactionPayload(proposal.payload_json)) {
      return null;
    }
    const purchasedAt = localDateTimeToIso(editable.purchased_at);
    const amountCents = amountInputToCents(editable.total);
    if (!purchasedAt || amountCents === null || !editable.merchant_name.trim()) {
      setErrorMessage(copy.createFailed);
      return null;
    }
    const nextPayload = {
      ...proposal.payload_json,
      purchased_at: purchasedAt,
      merchant_name: editable.merchant_name.trim(),
      total_gross_cents: amountCents,
      currency: editable.currency.trim().toUpperCase() || "EUR",
      source_account_ref: editable.source_account_ref.trim() || "cash"
    };
    const updated = await updateMutation.mutateAsync({ id: proposal.id, payload: nextPayload });
    mergeProposal(updated);
    return updated;
  }

  async function approve(proposal: IngestionProposal): Promise<void> {
    setErrorMessage(null);
    try {
      const updated = (await saveProposal(proposal)) ?? proposal;
      const approved = await approveMutation.mutateAsync(updated.id);
      mergeProposal(approved);
    } catch (error) {
      setErrorMessage(resolveApiErrorMessage(error, t, copy.createFailed));
    }
  }

  async function reject(proposal: IngestionProposal): Promise<void> {
    setErrorMessage(null);
    try {
      const rejected = await rejectMutation.mutateAsync(proposal.id);
      mergeProposal(rejected);
    } catch (error) {
      setErrorMessage(resolveApiErrorMessage(error, t, copy.createFailed));
    }
  }

  async function commit(proposal: IngestionProposal): Promise<void> {
    setErrorMessage(null);
    try {
      const committed = await commitMutation.mutateAsync(proposal.id);
      mergeProposal(committed);
      setNotice(copy.committed);
    } catch (error) {
      setErrorMessage(resolveApiErrorMessage(error, t, copy.createFailed));
    }
  }

  async function undo(proposal: IngestionProposal): Promise<void> {
    setErrorMessage(null);
    try {
      const updated = await undoMutation.mutateAsync(proposal.id);
      mergeProposal(updated);
    } catch (error) {
      setErrorMessage(resolveApiErrorMessage(error, t, copy.createFailed));
    }
  }

  async function runBatch(action: "approve" | "commit" | "reject"): Promise<void> {
    setErrorMessage(null);
    const proposalIds = proposals
      .filter((proposal) => {
        if (action === "approve") {
          return proposal.status === "pending_review";
        }
        if (action === "commit") {
          return proposal.status === "approved" || proposal.status === "auto_approved";
        }
        return proposal.status === "pending_review" || proposal.status === "draft";
      })
      .map((proposal) => proposal.id);
    if (proposalIds.length === 0) {
      return;
    }
    try {
      const result =
        action === "approve"
          ? await batchApproveMutation.mutateAsync(proposalIds)
          : action === "commit"
            ? await batchCommitMutation.mutateAsync(proposalIds)
            : await batchRejectMutation.mutateAsync(proposalIds);
      appendProposals(result.items);
    } catch (error) {
      setErrorMessage(resolveApiErrorMessage(error, t, copy.createFailed));
    }
  }

  async function refreshMatches(proposal: IngestionProposal): Promise<void> {
    setErrorMessage(null);
    try {
      const result = await refreshMatchesMutation.mutateAsync(proposal.id);
      setMatchCandidates((previous) => ({ ...previous, [proposal.id]: result.items }));
    } catch (error) {
      setErrorMessage(resolveApiErrorMessage(error, t, copy.createFailed));
    }
  }

  async function markAlreadyCovered(proposal: IngestionProposal, candidate: IngestionMatchCandidate): Promise<void> {
    setErrorMessage(null);
    try {
      const updated = await updateIngestionProposal(proposal.id, {
        payload: {
          type: "already_covered",
          statement_row_id: proposal.statement_row_id,
          transaction_id: candidate.transaction_id,
          confidence: Math.max(candidate.score, 0.8),
          reason: "Deterministic match candidate selected by user.",
          match_score: candidate.score
        }
      });
      mergeProposal(updated);
    } catch (error) {
      setErrorMessage(resolveApiErrorMessage(error, t, copy.createFailed));
    }
  }

  const busy =
    createSessionMutation.isPending ||
    sendMessageMutation.isPending ||
    uploadMutation.isPending ||
    pasteMutation.isPending ||
    classifyRowsMutation.isPending ||
    updateMutation.isPending ||
    approveMutation.isPending ||
    rejectMutation.isPending ||
    refreshMatchesMutation.isPending ||
    commitMutation.isPending ||
    undoMutation.isPending ||
    batchApproveMutation.isPending ||
    batchCommitMutation.isPending ||
    batchRejectMutation.isPending ||
    settingsMutation.isPending;

  return (
    <div className="space-y-6">
      <PageHeader title={copy.title} description={copy.description}>
        <div className="flex items-center gap-2 rounded-lg border border-border/70 bg-background px-3 py-2 text-sm">
          {approvalMode === "yolo_auto" ? <Zap className="h-4 w-4 text-amber-500" /> : <ShieldCheck className="h-4 w-4 text-primary" />}
          <div>
            <p className="font-medium">{approvalMode === "yolo_auto" ? copy.yoloAuto : copy.reviewFirst}</p>
            <p className="text-xs text-muted-foreground">{copy.reviewFirstDescription}</p>
          </div>
          <Button
            type="button"
            size="sm"
            variant={approvalMode === "yolo_auto" ? "secondary" : "outline"}
            disabled={busy}
            onClick={() =>
              void settingsMutation.mutateAsync({
                approval_mode: approvalMode === "yolo_auto" ? "review_first" : "yolo_auto"
              })
            }
          >
            {approvalMode === "yolo_auto" ? copy.reviewFirst : copy.yoloAuto}
          </Button>
        </div>
      </PageHeader>

      {errorMessage ? (
        <Alert variant="destructive">
          <AlertTitle>{copy.createFailed}</AlertTitle>
          <AlertDescription>{errorMessage}</AlertDescription>
        </Alert>
      ) : null}
      {notice ? (
        <Alert>
          <Check className="h-4 w-4" />
          <AlertTitle>{notice}</AlertTitle>
        </Alert>
      ) : null}

      <section className="grid gap-6 xl:grid-cols-[minmax(320px,0.8fr)_minmax(0,1.4fr)]">
        <div className="space-y-4">
        <form className="space-y-4 rounded-lg border border-border/70 bg-card p-4" onSubmit={submitInput}>
          <div className="flex items-center gap-2">
            <MessageSquarePlus className="h-5 w-5 text-primary" />
            <Label htmlFor="ingestion-input" className="text-base font-semibold">
              {copy.inputLabel}
            </Label>
          </div>
          <Textarea
            id="ingestion-input"
            value={input}
            placeholder={copy.inputPlaceholder}
            rows={8}
            onChange={(event) => setInput(event.target.value)}
          />
          <Button type="submit" className="gap-2" disabled={busy || !input.trim()}>
            {busy && sendMessageMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
            {copy.send}
          </Button>
          <div className="grid grid-cols-3 gap-3 border-t pt-4 text-sm">
            <div>
              <p className="text-muted-foreground">Total</p>
              <p className="text-lg font-semibold">{summary.total}</p>
            </div>
            <div>
              <p className="text-muted-foreground">Ready</p>
              <p className="text-lg font-semibold">{summary.ready}</p>
            </div>
            <div>
              <p className="text-muted-foreground">Done</p>
              <p className="text-lg font-semibold">{summary.committed}</p>
            </div>
          </div>
        </form>

        <section className="space-y-4 rounded-lg border border-border/70 bg-card p-4">
          <div className="flex items-center gap-2">
            <Upload className="h-5 w-5 text-primary" />
            <h2 className="text-base font-semibold">{copy.uploadCsv}</h2>
          </div>
          <Input
            type="file"
            accept=".csv,text/csv,.txt,.pdf,application/pdf,image/png,image/jpeg,image/webp"
            disabled={busy}
            onChange={(event) => void uploadCsvFile(event.target.files?.[0] ?? null)}
          />
          <form className="space-y-3" onSubmit={parsePastedTable}>
            <div className="flex items-center gap-2">
              <Table className="h-4 w-4 text-muted-foreground" />
              <Label htmlFor="pasted-table">{copy.parseTable}</Label>
            </div>
            <Textarea
              id="pasted-table"
              rows={5}
              value={pastedTable}
              placeholder={copy.tablePlaceholder}
              onChange={(event) => setPastedTable(event.target.value)}
            />
            <div className="flex flex-wrap gap-2">
              <Button type="submit" variant="outline" className="gap-2" disabled={busy || !pastedTable.trim()}>
                <Table className="h-4 w-4" />
                {copy.parseTable}
              </Button>
              <Button type="button" className="gap-2" disabled={busy || rows.length === 0} onClick={() => void classifyRows()}>
                <RefreshCw className="h-4 w-4" />
                {copy.classifyRows}
              </Button>
            </div>
          </form>
          {rows.length > 0 ? (
            <div className="space-y-2 border-t pt-3">
              <p className="text-sm font-medium">{copy.parsedRows}</p>
              <div className="max-h-56 overflow-auto rounded-md border">
                {rows.slice(0, 12).map((row) => (
                  <div key={row.id} className="grid grid-cols-[70px_1fr_auto] gap-2 border-b px-3 py-2 text-xs last:border-b-0">
                    <span className="text-muted-foreground">{row.status}</span>
                    <span className="truncate">{row.payee ?? row.description ?? "Row"}</span>
                    <span>{row.amount_cents === null ? "n/a" : formatEurFromCents(Math.abs(row.amount_cents))}</span>
                  </div>
                ))}
              </div>
            </div>
          ) : null}
        </section>
        </div>

        <section className="space-y-3">
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <ReceiptText className="h-5 w-5 text-primary" />
              <h2 className="text-base font-semibold">{copy.proposals}</h2>
            </div>
            <div className="flex flex-wrap justify-end gap-2">
              <Button type="button" size="sm" variant="outline" disabled={busy || !proposals.some((proposal) => proposal.status === "pending_review")} onClick={() => void runBatch("approve")}>
                {copy.batchApprove}
              </Button>
              <Button type="button" size="sm" disabled={busy || !proposals.some((proposal) => proposal.status === "approved" || proposal.status === "auto_approved")} onClick={() => void runBatch("commit")}>
                {copy.batchCommit}
              </Button>
              <Button type="button" size="sm" variant="ghost" disabled={busy || !proposals.some((proposal) => proposal.status === "pending_review" || proposal.status === "draft")} onClick={() => void runBatch("reject")}>
                {copy.batchReject}
              </Button>
            </div>
          </div>

          {proposals.length === 0 ? (
            <div className="rounded-lg border border-dashed border-border p-8 text-sm text-muted-foreground">
              {copy.empty}
            </div>
          ) : (
            <div className="space-y-3">
              {proposals.map((proposal) => {
                const editable = drafts[proposal.id];
                const payload = proposal.payload_json;
                const canEdit = editable && isCreateTransactionPayload(payload);
                return (
                  <article key={proposal.id} className="rounded-lg border border-border/70 bg-card p-4">
                    <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="font-semibold">{proposal.type.replace(/_/g, " ")}</span>
                          <span className={`rounded-full border px-2 py-0.5 text-xs ${statusTone(proposal.status)}`}>
                            {proposal.status.replace(/_/g, " ")}
                          </span>
                        </div>
                        <p className="mt-1 text-sm text-muted-foreground">{proposal.explanation}</p>
                      </div>
                      <p className="text-sm text-muted-foreground">
                        {copy.confidence}: {proposal.confidence === null ? "n/a" : Math.round(proposal.confidence * 100)}%
                      </p>
                    </div>

                    {canEdit ? (
                      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
                        <div className="space-y-1 xl:col-span-2">
                          <Label htmlFor={`merchant-${proposal.id}`}>{copy.merchant}</Label>
                          <Input
                            id={`merchant-${proposal.id}`}
                            value={editable.merchant_name}
                            disabled={proposal.status === "committed"}
                            onChange={(event) =>
                              setDrafts((previous) => ({
                                ...previous,
                                [proposal.id]: { ...editable, merchant_name: event.target.value }
                              }))
                            }
                          />
                        </div>
                        <div className="space-y-1">
                          <Label htmlFor={`date-${proposal.id}`}>{copy.purchasedAt}</Label>
                          <Input
                            id={`date-${proposal.id}`}
                            type="datetime-local"
                            value={editable.purchased_at}
                            disabled={proposal.status === "committed"}
                            onChange={(event) =>
                              setDrafts((previous) => ({
                                ...previous,
                                [proposal.id]: { ...editable, purchased_at: event.target.value }
                              }))
                            }
                          />
                        </div>
                        <div className="space-y-1">
                          <Label htmlFor={`amount-${proposal.id}`}>{copy.amount}</Label>
                          <Input
                            id={`amount-${proposal.id}`}
                            inputMode="decimal"
                            value={editable.total}
                            disabled={proposal.status === "committed"}
                            onChange={(event) =>
                              setDrafts((previous) => ({
                                ...previous,
                                [proposal.id]: { ...editable, total: event.target.value }
                              }))
                            }
                          />
                        </div>
                        <div className="space-y-1">
                          <Label htmlFor={`currency-${proposal.id}`}>{copy.currency}</Label>
                          <Input
                            id={`currency-${proposal.id}`}
                            value={editable.currency}
                            disabled={proposal.status === "committed"}
                            onChange={(event) =>
                              setDrafts((previous) => ({
                                ...previous,
                                [proposal.id]: { ...editable, currency: event.target.value }
                              }))
                            }
                          />
                        </div>
                      </div>
                    ) : (
                      <p className="rounded-md bg-muted p-3 text-sm text-muted-foreground">{copy.unsupported}</p>
                    )}

                    {isCreateTransactionPayload(payload) ? (
                      <p className="mt-3 text-sm text-muted-foreground">
                        {copy.commitResult}: {payload.merchant_name} · {formatEurFromCents(payload.total_gross_cents)}
                      </p>
                    ) : null}

                    <div className="mt-4 flex flex-wrap gap-2">
                      {proposal.status !== "committed" && proposal.status !== "rejected" ? (
                        <Button type="button" variant="outline" size="sm" className="gap-2" onClick={() => void saveProposal(proposal)}>
                          <Pencil className="h-4 w-4" />
                          {copy.save}
                        </Button>
                      ) : null}
                      {proposal.type === "create_transaction" && proposal.status === "pending_review" ? (
                        <Button type="button" variant="outline" size="sm" className="gap-2" onClick={() => void refreshMatches(proposal)}>
                          <RefreshCw className="h-4 w-4" />
                          {copy.refreshMatches}
                        </Button>
                      ) : null}
                      {proposal.status === "pending_review" || proposal.status === "draft" ? (
                        <>
                          <Button type="button" size="sm" className="gap-2" onClick={() => void approve(proposal)}>
                            <Check className="h-4 w-4" />
                            {copy.approve}
                          </Button>
                          <Button type="button" variant="ghost" size="sm" className="gap-2" onClick={() => void reject(proposal)}>
                            <X className="h-4 w-4" />
                            {copy.reject}
                          </Button>
                        </>
                      ) : null}
                      {proposal.status === "approved" || proposal.status === "auto_approved" ? (
                        <Button type="button" size="sm" className="gap-2" onClick={() => void commit(proposal)}>
                          <ReceiptText className="h-4 w-4" />
                          {copy.commit}
                        </Button>
                      ) : null}
                      {proposal.status === "committed" && proposal.commit_result_json?.transaction_id ? (
                        <Button type="button" size="sm" variant="outline" className="gap-2" onClick={() => void undo(proposal)}>
                          <RotateCcw className="h-4 w-4" />
                          {copy.undo}
                        </Button>
                      ) : null}
                    </div>

                    {matchCandidates[proposal.id]?.length ? (
                      <div className="mt-4 space-y-2 border-t pt-4">
                        {matchCandidates[proposal.id].map((candidate) => (
                          <div
                            key={candidate.transaction_id}
                            className="grid gap-3 rounded-md border border-border/70 bg-muted/20 p-3 text-sm md:grid-cols-[1fr_auto]"
                          >
                            <div>
                              <p className="font-medium">
                                {candidate.transaction.merchant_name ?? "Existing transaction"} ·{" "}
                                {formatEurFromCents(candidate.transaction.total_gross_cents)}
                              </p>
                              <p className="text-muted-foreground">
                                {new Date(candidate.transaction.purchased_at).toLocaleDateString()} ·{" "}
                                {Math.round(candidate.score * 100)}% · {candidate.transaction.source_id}
                              </p>
                            </div>
                            <div className="flex flex-wrap gap-2 md:justify-end">
                              <Button
                                type="button"
                                size="sm"
                                variant="outline"
                                className="gap-2"
                                onClick={() => void markAlreadyCovered(proposal, candidate)}
                              >
                                <Link2 className="h-4 w-4" />
                                {copy.alreadyCovered}
                              </Button>
                              <Button
                                type="button"
                                size="sm"
                                variant="ghost"
                                onClick={() =>
                                  setMatchCandidates((previous) => ({
                                    ...previous,
                                    [proposal.id]: []
                                  }))
                                }
                              >
                                {copy.createNewAnyway}
                              </Button>
                            </div>
                          </div>
                        ))}
                      </div>
                    ) : null}
                  </article>
                );
              })}
            </div>
          )}
        </section>
      </section>
    </div>
  );
}
