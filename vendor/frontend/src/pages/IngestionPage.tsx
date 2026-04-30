import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, HelpCircle, Link2, Loader2, MessageSquarePlus, Pencil, ReceiptText, RefreshCw, RotateCcw, Send, ShieldCheck, Table, Upload, X, Zap } from "lucide-react";
import { FormEvent, useEffect, useMemo, useRef, useState } from "react";

import {
  archiveIngestionSession,
  approveIngestionProposal,
  batchApproveIngestionProposals,
  batchCommitIngestionProposals,
  batchRejectIngestionProposals,
  classifyIngestionRows,
  commitIngestionProposal,
  createIngestionSession,
  fetchIngestionAgentSettings,
  fetchIngestionSession,
  fetchIngestionProposals,
  fetchIngestionRows,
  IngestionMatchCandidate,
  IngestionProposal,
  parseIngestionFile,
  parseIngestionPastedTable,
  isCreateTransactionPayload,
  refreshIngestionProposalMatches,
  rejectIngestionProposal,
  sendIngestionMessage,
  StatementRow,
  updateIngestionSession,
  updateIngestionProposal,
  updateIngestionAgentSettings,
  undoIngestionProposal,
  uploadIngestionFile
} from "@/api/ingestion";
import { fetchAIAgentConfig } from "@/api/aiSettings";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { useI18n } from "@/i18n";
import { resolveApiErrorMessage } from "@/lib/backend-messages";
import { formatEurFromCents } from "@/utils/format";
import { Link } from "react-router-dom";

type EditableProposal = {
  merchant_name: string;
  purchased_at: string;
  total: string;
  direction: "outflow" | "inflow";
  ledger_scope: "household" | "investment" | "internal" | "unknown";
  dashboard_include: boolean;
  currency: string;
  source_account_ref: string;
};

const ACTIVE_INGESTION_SESSION_STORAGE_KEY = "outlays.ingestion.activeSessionId";

type CashflowProposalPayload = {
  type: "create_cashflow_entry";
  effective_date: string;
  direction: "outflow" | "inflow";
  ledger_scope?: "household" | "investment" | "internal" | "unknown";
  dashboard_include?: boolean;
  category: string;
  amount_cents: number;
  currency: string;
  description?: string | null;
  source_type?: string;
  notes?: string | null;
  confidence?: number;
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
    direction: proposal.payload_json.direction ?? "outflow",
    ledger_scope: proposal.payload_json.ledger_scope ?? "household",
    dashboard_include: proposal.payload_json.dashboard_include ?? true,
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

function proposalReviewRank(proposal: IngestionProposal): number {
  const status = effectiveProposalStatus(proposal);
  if (proposal.type === "already_covered" || proposal.type === "link_existing_transaction") {
    return 40;
  }
  if (proposal.type === "ignore") {
    return 35;
  }
  if (status === "committed" || status === "rejected") {
    return 30;
  }
  if (status === "approved" || status === "auto_approved") {
    return 10;
  }
  return 0;
}

function sortProposalsForReview(items: IngestionProposal[]): IngestionProposal[] {
  return [...items].sort((left, right) => {
    const rankDelta = proposalReviewRank(left) - proposalReviewRank(right);
    if (rankDelta !== 0) {
      return rankDelta;
    }
    return new Date(left.created_at).getTime() - new Date(right.created_at).getTime();
  });
}

function proposalCardClassName(proposal: IngestionProposal): string {
  if (proposal.type === "already_covered" || proposal.type === "link_existing_transaction") {
    return "rounded-lg border border-amber-300/70 bg-amber-50/70 p-4 dark:border-amber-500/30 dark:bg-amber-950/20";
  }
  if (proposal.type === "ignore") {
    return "rounded-lg border border-muted bg-muted/30 p-4";
  }
  return "rounded-lg border border-border/70 bg-card p-4";
}

function stringValue(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function numberValue(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function rawCellsFromPayload(payload: Record<string, unknown>): string[] {
  const rawCells = payload.raw_cells;
  if (!Array.isArray(rawCells)) {
    return [];
  }
  return rawCells.map((cell) => String(cell ?? "").trim()).filter(Boolean);
}

function isCashflowProposalPayload(payload: Record<string, unknown>): payload is CashflowProposalPayload {
  return payload.type === "create_cashflow_entry";
}

function isCommittableProposal(proposal: IngestionProposal): boolean {
  return [
    "create_transaction",
    "create_cashflow_entry",
    "already_covered",
    "link_existing_transaction",
    "create_recurring_bill_candidate",
    "ignore"
  ].includes(proposal.type);
}

function effectiveProposalStatus(proposal: IngestionProposal): string {
  return proposal.commit_result_json ? "committed" : proposal.status;
}

function isTerminalProposal(proposal: IngestionProposal): boolean {
  const status = effectiveProposalStatus(proposal);
  return status === "committed" || status === "rejected";
}

export function IngestionPage() {
  const { locale, t } = useI18n();
  const queryClient = useQueryClient();
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [input, setInput] = useState("");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [pastedTable, setPastedTable] = useState("");
  const [proposals, setProposals] = useState<IngestionProposal[]>([]);
  const [rows, setRows] = useState<StatementRow[]>([]);
  const [drafts, setDrafts] = useState<Record<string, EditableProposal>>({});
  const [matchCandidates, setMatchCandidates] = useState<Record<string, IngestionMatchCandidate[]>>({});
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [agentStatus, setAgentStatus] = useState<string | null>(null);
  const [personalSystemPrompt, setPersonalSystemPrompt] = useState("");
  const [showHelp, setShowHelp] = useState(false);
  const [clearDonePromptOpen, setClearDonePromptOpen] = useState(false);
  const [clearDonePromptDismissedSessionId, setClearDonePromptDismissedSessionId] = useState<string | null>(null);

  const copy = locale === "de"
    ? {
        title: "Ingestion Agent",
        description: "Agent-first Erfassung für Text, CSV, PDF, Fotos und Screenshots.",
        modelRequiredTitle: "LLM-Modell verbinden",
        modelRequiredDescription:
          "Für echte Agent-Extraktion aus freiem Text, PDFs, Bildern und E-Mail-Screenshots muss ein ChatGPT/Codex-, API- oder lokales Modell verbunden sein. Ohne Modell laufen nur die lokalen Parser und Platzhalter-Vorschläge.",
        modelSettings: "AI-Einstellungen öffnen",
        inputLabel: "Agent Intake",
        policyTitle: "Dauerhafte Agent-Vorgaben",
        policyDescription: "Optional. Diese Vorgaben werden für jede neue Ingestion mitgegeben. Der aktuelle Auftrag steht unten im Intake-Feld und wird nicht hier gespeichert.",
        policyPlaceholder: "Dauerhafte Beispiele: Mieteinnahmen aus der Wohnung nicht ins Haushaltsbuch aufnehmen. Gehalt und Kindergeld als Haushalts-Einnahmen erfassen. Depot-, Dividenden- und Broker-Bewegungen ignorieren oder zur Prüfung markieren.",
        savePolicy: "Dauerhafte Vorgaben speichern",
        policySaved: "Dauerhafte Agent-Vorgaben gespeichert",
        policySummary: "Erweiterte Standardregeln",
        policyUnsaved: "Ungespeicherte Änderungen",
        policyEmpty: "Keine dauerhaften Vorgaben gespeichert",
        direction: "Richtung",
        outflow: "Ausgabe",
        inflow: "Einnahme",
        ledgerScope: "Bereich",
        household: "Haushalt",
        investment: "Investment",
        internal: "Intern",
        unknown: "Unklar",
        dashboardInclude: "Im Haushalts-Dashboard",
        inputPlaceholder: "Beschreibe, was der Agent erfassen soll. Optional: hänge CSV, PDF, Foto oder Screenshot an.\n\nBeispiel: Das ist eine wiederkehrende Rechnung ab jetzt. Erste Abbuchung ist am 15. Mai, alle weiteren Infos stehen im Screenshot.",
        tablePlaceholder: "Datum;Empfänger;Beschreibung;Betrag;Währung\n30.04.2026;Bäckerei;Frühstück;-4,20;EUR",
        send: "Agent starten",
        uploadFile: "Evidence anhängen",
        uploadFileDescription:
          "CSV und eingefügte Tabellen werden lokal in Statement-Zeilen gestaged. PDFs, Bilder und Screenshots werden gespeichert, per OCR-/Vision-Modell extrahiert und als Review-Vorschläge zurückgegeben.",
        uploadHelp: "Unterstützt: CSV, Text, PDF, PNG und JPG. Excel bitte aktuell als CSV speichern.",
        agentUploading: "Evidence wird hochgeladen...",
        agentParsing: "Evidence wird vorbereitet...",
        agentClassifying: "Agent interpretiert und matched Zeilen...",
        agentReady: "Agent-Ergebnisse sind bereit.",
        progressSummary: (rowCount: number, proposalCount: number) => `${rowCount} Zeilen gestaged, ${proposalCount} Vorschläge sichtbar.`,
        uploadComplete: "Datei verarbeitet",
        documentProposalCreated: "Dokument extrahiert. Prüfe den Vorschlag vor dem Commit.",
        rowsStaged: "Statement-Zeilen gestaged. Klassifiziere sie für Matching und Vorschläge.",
        parseTable: "Raw-Tabelle einfügen",
        classifyRows: "Agent klassifiziert Zeilen",
        csvLocal: "CSV/Tabelle: raw staging, dann Agent-Interpretation und Matching gegen bestehende Transaktionen.",
        documentsNeedModel: "PDF/Bild/Screenshot: OCR-/Vision-Extraktion nutzt dein verbundenes Modell oder lokalen OCR-Anbieter.",
        parsedRows: "Gestagte Evidence-Zeilen",
        advancedTable: "Erweitert: Raw-Tabelle einfügen",
        attachedFile: "Angehängte Datei",
        removeFile: "Entfernen",
        largeBatchTitle: "Viele Zeilen erkannt",
        largeBatchDescription:
          "Der Agent kann diese Zeilen gesammelt interpretieren. Agent Review zeigt alles zur Prüfung, YOLO Auto committet vollständige Vorschläge automatisch.",
        yoloClassifyBatch: "YOLO Auto aktivieren und klassifizieren",
        reviewFirst: "Agent Review",
        yoloAuto: "YOLO Auto",
        reviewFirstDescription: "Standard: Der Agent interpretiert und matched, du prüfst und committest.",
        yoloAutoDescription: "YOLO Auto committet vollständige Agent-Vorschläge automatisch. Bestehende Matches werden abgedeckt, unvollständige Zeilen bleiben offen.",
        modeTitle: "Ingestion-Modus",
        switchToReview: "Agent Review nutzen",
        switchToYolo: "YOLO Auto aktivieren",
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
        documentEvidence: "Dokument-Evidence",
        extraction: "Extraktion",
        semantic: "Semantik",
        preview: "Vorschau",
        refreshMatches: "Matches suchen",
        alreadyCovered: "Schon abgedeckt",
        createNewAnyway: "Neu erstellen",
        batchApprove: "Bereite freigeben",
        batchCommit: "Freigegebene committen",
        batchReject: "Offene Vorschläge ablehnen",
        clearReview: "Review leeren",
        clearReviewDone: "Review geleert.",
        allDoneTitle: "Ingestion ist erledigt",
        allDoneDescription: "Alle sichtbaren Vorschläge sind committed oder abgelehnt. Du kannst diese Ansicht jetzt leeren; die erstellten Transaktionen und Cashflow-Einträge bleiben erhalten.",
        clearDoneReview: "Ansicht leeren",
        keepDoneReview: "Noch anzeigen",
        undo: "Rückgängig",
        unsupported: "Dieser Vorschlagstyp hat keine direkten Bearbeitungsfelder.",
        total: "Gesamt",
        ready: "Bereit",
        done: "Erledigt",
        needsDecision: "Entscheidung nötig",
        rowEvidence: "Bankzeile",
        rawCells: "Original-Zellen",
        suggestedDecision: "Vorschlag",
        lowConfidence: "niedrig",
        helpTitle: "So funktioniert der Ingestion Agent",
        helpText:
          "Der Agent interpretiert Text und Dateien, erstellt Vorschläge und sucht automatisch nach vorhandenen Lidl-/Amazon-/Connector-Transaktionen. Schon abgedeckte Zeilen werden unten markiert. Prüfen bedeutet: noch nicht sicher genug; du kannst daraus eine Einnahme/Ausgabe machen oder sie ignorieren.",
        closeHelp: "Verstanden",
        convertToTransaction: "Als Transaktion prüfen",
        convertToIncome: "Als Einnahme erfassen",
        ignoreRow: "Ignorieren",
        proposalTypeLabels: {
          create_transaction: "Transaktion erstellen",
          create_cashflow_entry: "Cashflow-Eintrag",
          link_existing_transaction: "Mit vorhandener Transaktion verknüpfen",
          already_covered: "Schon abgedeckt",
          create_recurring_bill: "Wiederkehrende Rechnung erstellen",
          create_recurring_bill_candidate: "Wiederkehrende Rechnung prüfen",
          link_recurring_occurrence: "Wiederkehrende Buchung verknüpfen",
          ignore: "Ignorieren",
          needs_review: "Prüfen"
        } as Record<string, string>,
        statusLabels: {
          draft: "Entwurf",
          pending_review: "Offen",
          auto_approved: "Automatisch freigegeben",
          approved: "Freigegeben",
          committing: "Committet...",
          committed: "Committet",
          rejected: "Abgelehnt",
          failed: "Fehlgeschlagen"
        } as Record<string, string>
      }
    : {
        title: "Ingestion Agent",
        description: "Agent-first intake for text, CSV, PDFs, photos, and screenshots.",
        modelRequiredTitle: "Connect an LLM model",
        modelRequiredDescription:
          "Real agent extraction from free text, PDFs, images, and email screenshots needs a connected ChatGPT/Codex, API, or local model. Without one, only local parsers and placeholder review proposals are available.",
        modelSettings: "Open AI settings",
        inputLabel: "Agent intake",
        policyTitle: "Persistent agent defaults",
        policyDescription: "Optional. These defaults are sent with every new ingestion. The current task belongs in the intake field below and is not saved here.",
        policyPlaceholder: "Persistent examples: Do not ingest rental income from the apartment into the household book. Treat salary and child benefit as household income. Ignore or review broker, dividend, and securities movements.",
        savePolicy: "Save persistent defaults",
        policySaved: "Persistent agent defaults saved",
        policySummary: "Advanced default rules",
        policyUnsaved: "Unsaved changes",
        policyEmpty: "No persistent defaults saved",
        direction: "Direction",
        outflow: "Outflow",
        inflow: "Inflow",
        ledgerScope: "Scope",
        household: "Household",
        investment: "Investment",
        internal: "Internal",
        unknown: "Unknown",
        dashboardInclude: "In household dashboard",
        inputPlaceholder: "Tell the agent what to ingest. Optionally attach a CSV, PDF, photo, or screenshot.\n\nExample: This is a recurring bill starting now. First billing is May 15, the rest of the details are in the screenshot.",
        tablePlaceholder: "Date,Payee,Description,Amount,Currency\n2026-04-30,Ice Cream Store,Cash,-5.50,EUR",
        send: "Run agent",
        uploadFile: "Attach evidence",
        uploadFileDescription:
          "CSV and pasted tables are staged locally as statement rows. PDFs, images, and screenshots are stored, extracted through the OCR/vision model path, and returned as review proposals.",
        uploadHelp: "Supported: CSV, text, PDF, PNG, and JPG. Save Excel files as CSV for now.",
        agentUploading: "Uploading evidence...",
        agentParsing: "Preparing evidence...",
        agentClassifying: "Agent is interpreting and matching rows...",
        agentReady: "Agent results are ready.",
        progressSummary: (rowCount: number, proposalCount: number) => `${rowCount} rows staged, ${proposalCount} proposals visible.`,
        uploadComplete: "File processed",
        documentProposalCreated: "Document extracted. Review the proposal before committing.",
        rowsStaged: "Statement rows staged. Classify them for matching and proposals.",
        parseTable: "Paste raw table",
        classifyRows: "Agent classifies rows",
        csvLocal: "CSV/table: raw staging, then agent interpretation and matching against existing transactions.",
        documentsNeedModel: "PDF/image/screenshot: OCR/vision extraction uses your connected model or local OCR provider.",
        parsedRows: "Staged evidence rows",
        advancedTable: "Advanced: paste raw table",
        attachedFile: "Attached file",
        removeFile: "Remove",
        largeBatchTitle: "Large batch detected",
        largeBatchDescription:
          "The agent can interpret these rows as a batch. Agent Review shows everything for review; YOLO Auto commits complete proposals automatically.",
        yoloClassifyBatch: "Enable YOLO Auto and classify",
        reviewFirst: "Agent Review",
        yoloAuto: "YOLO Auto",
        reviewFirstDescription: "Default: the agent interprets and matches, then you review and commit.",
        yoloAutoDescription: "YOLO Auto commits complete agent proposals automatically. Existing matches are marked covered; incomplete rows stay open.",
        modeTitle: "Ingestion mode",
        switchToReview: "Use Agent Review",
        switchToYolo: "Enable YOLO Auto",
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
        documentEvidence: "Document evidence",
        extraction: "Extraction",
        semantic: "Semantic",
        preview: "Preview",
        refreshMatches: "Find matches",
        alreadyCovered: "Already covered",
        createNewAnyway: "Create new anyway",
        batchApprove: "Approve ready",
        batchCommit: "Commit approved",
        batchReject: "Reject open proposals",
        clearReview: "Clear review",
        clearReviewDone: "Review cleared.",
        allDoneTitle: "Ingestion is complete",
        allDoneDescription: "All visible proposals are committed or rejected. You can clear this view now; created transactions and cashflow entries stay in the database.",
        clearDoneReview: "Clear view",
        keepDoneReview: "Keep visible",
        undo: "Undo",
        unsupported: "This proposal type has no direct edit fields.",
        total: "Total",
        ready: "Ready",
        done: "Done",
        needsDecision: "Decision needed",
        rowEvidence: "Bank row",
        rawCells: "Original cells",
        suggestedDecision: "Suggestion",
        lowConfidence: "low",
        helpTitle: "How the Ingestion Agent works",
        helpText:
          "The agent interprets text and files, creates proposals, and automatically searches existing Lidl/Amazon/connector transactions. Already covered rows are marked at the bottom. Review means not safe enough yet; you can turn the row into income/expense or ignore it.",
        closeHelp: "Got it",
        convertToTransaction: "Review as transaction",
        convertToIncome: "Record as income",
        ignoreRow: "Ignore",
        proposalTypeLabels: {
          create_transaction: "Create transaction",
          create_cashflow_entry: "Cashflow entry",
          link_existing_transaction: "Link existing transaction",
          already_covered: "Already covered",
          create_recurring_bill: "Create recurring bill",
          create_recurring_bill_candidate: "Review recurring bill",
          link_recurring_occurrence: "Link recurring occurrence",
          ignore: "Ignore",
          needs_review: "Review"
        } as Record<string, string>,
        statusLabels: {
          draft: "Draft",
          pending_review: "Open",
          auto_approved: "Auto approved",
          approved: "Approved",
          committing: "Committing...",
          committed: "Committed",
          rejected: "Rejected",
          failed: "Failed"
        } as Record<string, string>
      };

  const settingsQuery = useQuery({
    queryKey: ["ingestion-agent-settings"],
    queryFn: fetchIngestionAgentSettings
  });
  const agentConfigQuery = useQuery({
    queryKey: ["ai-agent-config"],
    queryFn: fetchAIAgentConfig
  });
  const settingsMutation = useMutation({
    mutationFn: updateIngestionAgentSettings,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["ingestion-agent-settings"] });
    }
  });
  useEffect(() => {
    if (settingsQuery.data) {
      setPersonalSystemPrompt(settingsQuery.data.personal_system_prompt || "");
    }
  }, [settingsQuery.data?.personal_system_prompt]);
  const activeSessionIdRef = useRef<string | null>(null);
  const validatedSessionIdsRef = useRef(new Set<string>());

  function setActiveSession(nextSessionId: string | null): void {
    activeSessionIdRef.current = nextSessionId;
    setSessionId(nextSessionId);
    if (typeof window === "undefined") {
      return;
    }
    if (nextSessionId) {
      window.localStorage.setItem(ACTIVE_INGESTION_SESSION_STORAGE_KEY, nextSessionId);
    } else {
      window.localStorage.removeItem(ACTIVE_INGESTION_SESSION_STORAGE_KEY);
    }
  }

  function isMissingIngestionSessionError(error: unknown): boolean {
    const candidate = error as { code?: unknown; message?: unknown } | null;
    return candidate?.code === "session_not_found" ||
      (typeof candidate?.message === "string" && candidate.message.toLowerCase().includes("ingestion session not found"));
  }

  useEffect(() => {
    if (typeof window === "undefined") {
      return;
    }
    const activeSessionId = window.localStorage.getItem(ACTIVE_INGESTION_SESSION_STORAGE_KEY);
    if (activeSessionId) {
      setActiveSession(activeSessionId);
    }
    if (window.localStorage.getItem("outlays.ingestion.helpSeen") !== "1") {
      setShowHelp(true);
    }
  }, []);
  const approvalMode = settingsQuery.data?.approval_mode ?? "review_first";
  const hasEnabledModel = Boolean(agentConfigQuery.data?.available_models.some((model) => model.enabled));

  const createSessionMutation = useMutation({ mutationFn: createIngestionSession });
  async function ensureSession(inputKind = "free_text"): Promise<string> {
    const currentSessionId = activeSessionIdRef.current ?? sessionId;
    if (currentSessionId) {
      if (validatedSessionIdsRef.current.has(currentSessionId)) {
        return currentSessionId;
      }
      try {
        await fetchIngestionSession(currentSessionId);
        validatedSessionIdsRef.current.add(currentSessionId);
        return currentSessionId;
      } catch (error) {
        if (!isMissingIngestionSessionError(error)) {
          throw error;
        }
        validatedSessionIdsRef.current.delete(currentSessionId);
        setActiveSession(null);
      }
    }
    const created = await createSessionMutation.mutateAsync({
      title: inputKind === "csv" ? "Statement intake" : "Manual text intake",
      input_kind: inputKind,
      approval_mode: approvalMode
    });
    validatedSessionIdsRef.current.add(created.id);
    setActiveSession(created.id);
    return created.id;
  }

  const sendMessageMutation = useMutation({
    mutationFn: async (message: string) => {
      setAgentStatus(null);
      const activeSessionId = await ensureSession("free_text");
      return sendIngestionMessage(activeSessionId, message);
    },
    onSuccess: (result) => {
      setProposals((previous) => {
        const byId = new Map(previous.map((proposal) => [proposal.id, proposal]));
        for (const proposal of result.proposals) {
          byId.set(proposal.id, proposal);
        }
        return sortProposalsForReview(Array.from(byId.values()));
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
    mutationFn: async ({ file, contextText }: { file: File; contextText: string }) => {
      const activeSessionId = await ensureSession("file");
      setAgentStatus(copy.agentUploading);
      const uploaded = await uploadIngestionFile(activeSessionId, file, contextText);
      setAgentStatus(copy.agentParsing);
      const parsed = await parseIngestionFile(uploaded.id);
      return parsed;
    },
    onSuccess: (result) => {
      setRows(result.items);
      if (result.proposals?.length) {
        appendProposals(result.proposals);
        setNotice(copy.documentProposalCreated);
        setAgentStatus(copy.agentReady);
      } else if (result.count > 0) {
        setNotice(copy.agentClassifying);
        setAgentStatus(copy.agentClassifying);
        classifyRowsMutation.mutate(undefined, {
          onError: (error) => {
            setAgentStatus(null);
            setErrorMessage(resolveApiErrorMessage(error, t, copy.createFailed));
          }
        });
      } else {
        setNotice(copy.uploadComplete);
        setAgentStatus(null);
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
      setAgentStatus(copy.agentClassifying);
      return classifyIngestionRows(activeSessionId);
    },
    onSuccess: (result) => {
      appendProposals(result.items);
      setNotice(copy.agentReady);
      setAgentStatus(copy.agentReady);
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
  const archiveSessionMutation = useMutation({ mutationFn: archiveIngestionSession });
  const updateSessionMutation = useMutation({ mutationFn: ({ id, body }: { id: string; body: Parameters<typeof updateIngestionSession>[1] }) => updateIngestionSession(id, body) });

  const shouldPollIngestion = Boolean(sessionId) && (uploadMutation.isPending || classifyRowsMutation.isPending);
  const liveRowsQuery = useQuery({
    queryKey: ["ingestion-rows", sessionId],
    queryFn: () => fetchIngestionRows(sessionId ?? ""),
    enabled: Boolean(sessionId),
    refetchInterval: shouldPollIngestion ? 3000 : false
  });
  const liveProposalsQuery = useQuery({
    queryKey: ["ingestion-proposals", sessionId],
    queryFn: () => fetchIngestionProposals(sessionId ?? ""),
    enabled: Boolean(sessionId),
    refetchInterval: shouldPollIngestion ? 3000 : false
  });

  useEffect(() => {
    if (liveRowsQuery.data) {
      setRows(liveRowsQuery.data.items);
    }
  }, [liveRowsQuery.data]);

  useEffect(() => {
    if (liveProposalsQuery.data) {
      replaceProposals(liveProposalsQuery.data.items);
    }
  }, [liveProposalsQuery.data]);

  const summary = useMemo(() => {
    return {
      total: proposals.length,
      ready: proposals.filter((proposal) => proposal.status === "approved").length,
      committed: proposals.filter((proposal) => effectiveProposalStatus(proposal) === "committed").length
    };
  }, [proposals]);
  const sortedProposals = useMemo(() => sortProposalsForReview(proposals), [proposals]);
  const rowsById = useMemo(() => new Map(rows.map((row) => [row.id, row])), [rows]);
  const reviewComplete = proposals.length > 0 && proposals.every(isTerminalProposal);

  function draftsFromProposals(items: IngestionProposal[]): Record<string, EditableProposal> {
    const next: Record<string, EditableProposal> = {};
    for (const proposal of items) {
      const editable = editableFromProposal(proposal);
      if (editable) {
        next[proposal.id] = editable;
      }
    }
    return next;
  }

  function replaceProposals(items: IngestionProposal[]): void {
    const sorted = sortProposalsForReview(items);
    setProposals(sorted);
    setDrafts(draftsFromProposals(sorted));
  }

  function appendProposals(items: IngestionProposal[]): void {
    setProposals((previous) => {
      const byId = new Map(previous.map((proposal) => [proposal.id, proposal]));
      for (const proposal of items) {
        byId.set(proposal.id, proposal);
      }
      return sortProposalsForReview(Array.from(byId.values()));
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
    if (!message && !selectedFile) {
      return;
    }
    try {
      if (selectedFile) {
        await uploadMutation.mutateAsync({ file: selectedFile, contextText: message });
        setInput("");
        setSelectedFile(null);
      } else {
        await sendMessageMutation.mutateAsync(message);
      }
    } catch (error) {
      setAgentStatus(null);
      setErrorMessage(resolveApiErrorMessage(error, t, copy.createFailed));
    }
  }

  async function parsePastedTableFromState(): Promise<void> {
    const text = pastedTable.trim();
    if (!text) {
      return;
    }
    setErrorMessage(null);
    try {
      await pasteMutation.mutateAsync(text);
    } catch (error) {
      setAgentStatus(null);
      setErrorMessage(resolveApiErrorMessage(error, t, copy.createFailed));
    }
  }

  async function classifyRows(): Promise<void> {
    setErrorMessage(null);
    try {
      await classifyRowsMutation.mutateAsync();
    } catch (error) {
      setAgentStatus(null);
      setErrorMessage(resolveApiErrorMessage(error, t, copy.createFailed));
    }
  }

  async function enableYoloAndClassifyRows(): Promise<void> {
    setErrorMessage(null);
    try {
      const activeSessionId = await ensureSession("csv");
      await settingsMutation.mutateAsync({ approval_mode: "yolo_auto" });
      await updateSessionMutation.mutateAsync({ id: activeSessionId, body: { approval_mode: "yolo_auto" } });
      await classifyRowsMutation.mutateAsync();
      setNotice(copy.yoloAuto);
    } catch (error) {
      setAgentStatus(null);
      setErrorMessage(resolveApiErrorMessage(error, t, copy.createFailed));
    }
  }

  function mergeProposal(next: IngestionProposal): void {
    setProposals((previous) => sortProposalsForReview(previous.map((proposal) => (proposal.id === next.id ? next : proposal))));
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
      direction: editable.direction,
      ledger_scope: editable.ledger_scope,
      dashboard_include: editable.dashboard_include,
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

  async function convertReviewProposal(proposal: IngestionProposal, directionOverride?: "outflow" | "inflow"): Promise<void> {
    setErrorMessage(null);
    try {
      const payload = proposal.payload_json;
      const amount = numberValue(payload.amount_cents);
      const merchant = stringValue(payload.counterparty) ?? stringValue(payload.summary)?.split(" · ")[1] ?? "Bankzeile";
      const occurredAt = stringValue(payload.occurred_at);
      if (amount === null || !occurredAt || !merchant) {
        setErrorMessage(copy.createFailed);
        return;
      }
      const direction = directionOverride ?? (stringValue(payload.direction) === "inflow" ? "inflow" : "outflow");
      const rawCells = rawCellsFromPayload(payload);
      const updated = await updateMutation.mutateAsync({
        id: proposal.id,
        payload: {
          type: "create_transaction",
          purchased_at: occurredAt,
          merchant_name: merchant,
          total_gross_cents: Math.abs(amount),
          direction,
          ledger_scope: stringValue(payload.ledger_scope) ?? "household",
          dashboard_include: direction === "outflow" && (stringValue(payload.ledger_scope) ?? "household") === "household",
          currency: stringValue(payload.currency) ?? "EUR",
          source_id: "agent_ingest",
          source_display_name: "Agent Ingestion",
          source_account_ref: "bank_statement",
          source_transaction_id: null,
          idempotency_key: `ingest-review:${proposal.statement_row_id ?? proposal.id}`,
          confidence: direction === "inflow" ? 0.74 : 0.78,
          items: [],
          discounts: [],
          raw_payload: {
            input_kind: "statement_row",
            statement_row_id: proposal.statement_row_id,
            evidence: stringValue(payload.summary) ?? stringValue(payload.reason) ?? "",
            raw_cells: rawCells
          }
        }
      });
      mergeProposal(updated);
    } catch (error) {
      setErrorMessage(resolveApiErrorMessage(error, t, copy.createFailed));
    }
  }

  async function ignoreReviewProposal(proposal: IngestionProposal): Promise<void> {
    setErrorMessage(null);
    try {
      const updated = await updateMutation.mutateAsync({
        id: proposal.id,
        payload: {
          type: "ignore",
          statement_row_id: proposal.statement_row_id,
          reason: stringValue(proposal.payload_json.reason) ?? copy.ignoreRow,
          confidence: 0.8
        }
      });
      mergeProposal(updated);
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
        const status = effectiveProposalStatus(proposal);
        if (action === "approve") {
          return status === "pending_review" && isCommittableProposal(proposal);
        }
        if (action === "commit") {
          return (status === "approved" || status === "auto_approved") && isCommittableProposal(proposal);
        }
        return status === "pending_review" || status === "draft";
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

  async function clearReview(): Promise<void> {
    setErrorMessage(null);
    try {
      if (sessionId) {
        try {
          await archiveSessionMutation.mutateAsync(sessionId);
        } catch (error) {
          if (!isMissingIngestionSessionError(error)) {
            throw error;
          }
        }
      }
      setActiveSession(null);
      setRows([]);
      setProposals([]);
      setDrafts({});
      setMatchCandidates({});
      setInput("");
      setSelectedFile(null);
      setPastedTable("");
      setAgentStatus(null);
      setClearDonePromptOpen(false);
      setClearDonePromptDismissedSessionId(null);
      setNotice(copy.clearReviewDone);
      await queryClient.invalidateQueries({ queryKey: ["ingestion-rows"] });
      await queryClient.invalidateQueries({ queryKey: ["ingestion-proposals"] });
    } catch (error) {
      setErrorMessage(resolveApiErrorMessage(error, t, copy.createFailed));
    }
  }

  async function refreshMatches(proposal: IngestionProposal): Promise<void> {
    setErrorMessage(null);
    try {
      const result = await refreshMatchesMutation.mutateAsync(proposal.id);
      const topCandidate = result.items[0];
      if (topCandidate && topCandidate.score >= 0.9) {
        await markAlreadyCovered(proposal, topCandidate);
        setMatchCandidates((previous) => ({ ...previous, [proposal.id]: [] }));
        return;
      }
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

  async function savePersonalPolicy(): Promise<void> {
    setErrorMessage(null);
    try {
      await settingsMutation.mutateAsync({ personal_system_prompt: personalSystemPrompt });
      setNotice(copy.policySaved);
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
    archiveSessionMutation.isPending ||
    updateSessionMutation.isPending ||
    settingsMutation.isPending;

  const modeDescription = approvalMode === "yolo_auto" ? copy.yoloAutoDescription : copy.reviewFirstDescription;
  const savedPersonalSystemPrompt = settingsQuery.data?.personal_system_prompt || "";
  const hasUnsavedPersonalSystemPrompt = personalSystemPrompt !== savedPersonalSystemPrompt;

  useEffect(() => {
    if (!sessionId || busy || !reviewComplete || clearDonePromptDismissedSessionId === sessionId) {
      return;
    }
    setClearDonePromptOpen(true);
  }, [busy, clearDonePromptDismissedSessionId, reviewComplete, sessionId]);

  return (
    <div className="mx-auto w-full max-w-[1680px] space-y-5">
      <header className="grid gap-4 2xl:grid-cols-[minmax(0,1fr)_minmax(440px,0.86fr)] 2xl:items-start">
        <div className="min-w-0 space-y-2">
          <div className="flex items-center gap-2 text-xs font-medium uppercase tracking-[0.18em] text-muted-foreground">
            <ReceiptText className="h-4 w-4" />
            <span>{copy.title}</span>
          </div>
          <h1 className="max-w-3xl text-3xl font-semibold tracking-tight">{copy.title}</h1>
          <p className="max-w-4xl text-sm leading-6 text-muted-foreground">{copy.description}</p>
        </div>
        <div className={`rounded-lg border p-3 shadow-sm ${approvalMode === "yolo_auto" ? "border-amber-500/40 bg-amber-500/10" : "border-border/70 bg-card/80"}`}>
          <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
            <div className="min-w-0">
              <p className="text-xs font-medium uppercase tracking-[0.16em] text-muted-foreground">{copy.modeTitle}</p>
              <div className="mt-1 flex items-center gap-2">
                {approvalMode === "yolo_auto" ? <Zap className="h-4 w-4 shrink-0 text-amber-500" /> : <ShieldCheck className="h-4 w-4 shrink-0 text-primary" />}
                <p className="font-semibold">{approvalMode === "yolo_auto" ? copy.yoloAuto : copy.reviewFirst}</p>
              </div>
              <p className="mt-1 text-xs leading-5 text-muted-foreground">{modeDescription}</p>
            </div>
            <div className="flex shrink-0 flex-wrap gap-2">
              <Button type="button" size="icon" variant="outline" aria-label={copy.helpTitle} onClick={() => setShowHelp(true)}>
                <HelpCircle className="h-4 w-4" />
              </Button>
              <Button
                type="button"
                size="sm"
                variant={approvalMode === "yolo_auto" ? "secondary" : "default"}
                className="gap-2"
                disabled={busy}
                onClick={() =>
                  void settingsMutation.mutateAsync({
                    approval_mode: approvalMode === "yolo_auto" ? "review_first" : "yolo_auto"
                  })
                }
              >
                {approvalMode === "yolo_auto" ? <ShieldCheck className="h-4 w-4" /> : <Zap className="h-4 w-4" />}
                {approvalMode === "yolo_auto" ? copy.switchToReview : copy.switchToYolo}
              </Button>
            </div>
          </div>
        </div>
      </header>

      {showHelp ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="w-full max-w-xl rounded-lg border border-border bg-card p-5 shadow-xl">
            <div className="flex items-start justify-between gap-4">
              <div>
                <h2 className="text-lg font-semibold">{copy.helpTitle}</h2>
                <p className="mt-2 text-sm text-muted-foreground">{copy.helpText}</p>
              </div>
              <Button type="button" size="icon" variant="ghost" onClick={() => setShowHelp(false)}>
                <X className="h-4 w-4" />
              </Button>
            </div>
            <div className="mt-4 flex justify-end">
              <Button
                type="button"
                onClick={() => {
                  window.localStorage.setItem("outlays.ingestion.helpSeen", "1");
                  setShowHelp(false);
                }}
              >
                {copy.closeHelp}
              </Button>
            </div>
          </div>
        </div>
      ) : null}

      {clearDonePromptOpen ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="w-full max-w-lg rounded-lg border border-border bg-card p-5 shadow-xl">
            <div className="flex items-start justify-between gap-4">
              <div>
                <h2 className="text-lg font-semibold">{copy.allDoneTitle}</h2>
                <p className="mt-2 text-sm leading-6 text-muted-foreground">{copy.allDoneDescription}</p>
              </div>
              <Button
                type="button"
                size="icon"
                variant="ghost"
                onClick={() => {
                  setClearDonePromptOpen(false);
                  setClearDonePromptDismissedSessionId(sessionId);
                }}
              >
                <X className="h-4 w-4" />
              </Button>
            </div>
            <div className="mt-5 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
              <Button
                type="button"
                variant="outline"
                onClick={() => {
                  setClearDonePromptOpen(false);
                  setClearDonePromptDismissedSessionId(sessionId);
                }}
              >
                {copy.keepDoneReview}
              </Button>
              <Button
                type="button"
                onClick={() => {
                  setClearDonePromptOpen(false);
                  void clearReview();
                }}
              >
                {copy.clearDoneReview}
              </Button>
            </div>
          </div>
        </div>
      ) : null}

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
      {agentStatus && (uploadMutation.isPending || classifyRowsMutation.isPending) ? (
        <Alert>
          <Loader2 className="h-4 w-4 animate-spin" />
          <AlertTitle>{agentStatus}</AlertTitle>
          <AlertDescription>
            {rows.length > 0 || proposals.length > 0 ? copy.progressSummary(rows.length, proposals.length) : modeDescription}
          </AlertDescription>
        </Alert>
      ) : null}
      {!agentConfigQuery.isLoading && !hasEnabledModel ? (
        <Alert>
          <ShieldCheck className="h-4 w-4" />
          <AlertTitle>{copy.modelRequiredTitle}</AlertTitle>
          <AlertDescription className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
            <span>{copy.modelRequiredDescription}</span>
            <Button asChild type="button" variant="outline" size="sm" className="shrink-0">
              <Link to="/settings/ai">{copy.modelSettings}</Link>
            </Button>
          </AlertDescription>
        </Alert>
      ) : null}

      <details className="rounded-lg border border-border/70 bg-card/60 p-4">
        <summary className="cursor-pointer list-none">
          <div className="flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <h2 className="text-base font-semibold">{copy.policySummary}</h2>
                {hasUnsavedPersonalSystemPrompt ? (
                  <span className="rounded-full border border-amber-500/40 bg-amber-500/10 px-2 py-0.5 text-xs text-amber-700 dark:text-amber-300">
                    {copy.policyUnsaved}
                  </span>
                ) : null}
              </div>
              <p className="text-sm text-muted-foreground">
                {savedPersonalSystemPrompt ? copy.policyDescription : copy.policyEmpty}
              </p>
            </div>
            <span className="rounded-md border border-border px-3 py-2 text-sm text-muted-foreground">
              {copy.policyTitle}
            </span>
          </div>
        </summary>
        <div className="mt-4 space-y-3 rounded-md border border-border/70 bg-background/35 p-3">
          <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
            <div className="min-w-0">
              <h3 className="font-medium">{copy.policyTitle}</h3>
              <p className="text-sm leading-6 text-muted-foreground">{copy.policyDescription}</p>
            </div>
            <Button
              type="button"
              variant="outline"
              disabled={settingsMutation.isPending || !hasUnsavedPersonalSystemPrompt}
              onClick={() => void savePersonalPolicy()}
            >
              {settingsMutation.isPending ? <Loader2 className="mr-2 h-4 w-4 animate-spin" /> : null}
              {copy.savePolicy}
            </Button>
          </div>
          <Textarea
            value={personalSystemPrompt}
            rows={4}
            placeholder={copy.policyPlaceholder}
            onChange={(event) => setPersonalSystemPrompt(event.target.value)}
          />
        </div>
      </details>

      <section className="grid gap-5 2xl:grid-cols-[minmax(380px,0.72fr)_minmax(0,1.28fr)]">
        <div className="space-y-4">
        <form className="space-y-4 rounded-lg border border-border/70 bg-card/90 p-4 shadow-sm" onSubmit={submitInput}>
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
          <div className="space-y-2 rounded-md border border-dashed border-border/80 bg-background/40 p-3">
            <div className="flex items-center gap-2 text-sm font-medium">
              <Upload className="h-4 w-4 text-primary" />
              {copy.uploadFile}
            </div>
            <Input
              type="file"
              accept=".csv,text/csv,.txt,text/plain,.md,text/markdown,.pdf,application/pdf,image/png,image/jpeg"
              disabled={busy}
              onChange={(event) => setSelectedFile(event.target.files?.[0] ?? null)}
            />
            {selectedFile ? (
              <div className="flex items-center justify-between gap-3 rounded-md bg-muted/40 px-3 py-2 text-sm">
                <span className="truncate">{copy.attachedFile}: {selectedFile.name}</span>
                <Button type="button" size="sm" variant="ghost" onClick={() => setSelectedFile(null)}>
                  {copy.removeFile}
                </Button>
              </div>
            ) : null}
            <p className="text-xs text-muted-foreground">{copy.uploadHelp}</p>
          </div>
          <Button type="submit" className="gap-2" disabled={busy || (!input.trim() && !selectedFile)}>
            {busy && (sendMessageMutation.isPending || uploadMutation.isPending) ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
            {copy.send}
          </Button>
          <div className="grid grid-cols-3 gap-3 border-t pt-4 text-sm">
            <div>
              <p className="text-muted-foreground">{copy.total}</p>
              <p className="text-lg font-semibold">{summary.total}</p>
            </div>
            <div>
              <p className="text-muted-foreground">{copy.ready}</p>
              <p className="text-lg font-semibold">{summary.ready}</p>
            </div>
            <div>
              <p className="text-muted-foreground">{copy.done}</p>
              <p className="text-lg font-semibold">{summary.committed}</p>
            </div>
          </div>
          <details className="border-t pt-4">
            <summary className="cursor-pointer text-sm font-medium text-muted-foreground">{copy.advancedTable}</summary>
            <div className="mt-3 space-y-3">
              <Textarea
                id="pasted-table"
                rows={5}
                value={pastedTable}
                placeholder={copy.tablePlaceholder}
                onChange={(event) => setPastedTable(event.target.value)}
              />
              <div className="flex flex-wrap gap-2">
                <Button type="button" variant="outline" className="gap-2" disabled={busy || !pastedTable.trim()} onClick={() => void parsePastedTableFromState()}>
                  <Table className="h-4 w-4" />
                  {copy.parseTable}
                </Button>
                <Button type="button" className="gap-2" disabled={busy || rows.length === 0} onClick={() => void classifyRows()}>
                  <RefreshCw className="h-4 w-4" />
                  {copy.classifyRows}
                </Button>
              </div>
            </div>
          </details>
          {rows.length > 0 ? (
            <div className="space-y-2 border-t pt-3">
              <p className="text-sm font-medium">{copy.parsedRows}</p>
              {rows.length >= 20 ? (
                <Alert>
                  <Zap className="h-4 w-4" />
                  <AlertTitle>{copy.largeBatchTitle}</AlertTitle>
                  <AlertDescription className="space-y-3">
                    <span className="block leading-relaxed">{copy.largeBatchDescription}</span>
                    <Button
                      type="button"
                      size="sm"
                      className="w-full justify-center gap-2 sm:w-auto"
                      disabled={busy}
                      onClick={() => void enableYoloAndClassifyRows()}
                    >
                      <Zap className="h-4 w-4" />
                      {copy.yoloClassifyBatch}
                    </Button>
                  </AlertDescription>
                </Alert>
              ) : null}
              <div className="max-h-56 overflow-auto rounded-md border">
                {rows.slice(0, 12).map((row) => {
                  const rawRowText = typeof row.raw_json?.row_text === "string" ? row.raw_json.row_text : null;
                  return (
                    <div key={row.id} className="grid grid-cols-[70px_minmax(0,1fr)_auto] gap-2 border-b px-3 py-2 text-xs last:border-b-0">
                      <span className="text-muted-foreground">{row.status}</span>
                      <span className="truncate">{row.payee ?? row.description ?? rawRowText ?? "Raw row"}</span>
                      <span>{row.amount_cents === null ? "model" : formatEurFromCents(Math.abs(row.amount_cents))}</span>
                    </div>
                  );
                })}
              </div>
            </div>
          ) : null}
        </form>
        </div>

        <section className="space-y-3">
          <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <div>
            <div className="flex items-center gap-2">
              <ReceiptText className="h-5 w-5 text-primary" />
              <h2 className="text-base font-semibold">{copy.proposals}</h2>
            </div>
          </div>
            <div className="flex flex-wrap gap-2 lg:justify-end">
              <Button type="button" size="sm" variant="outline" disabled={busy || (!sessionId && proposals.length === 0 && rows.length === 0)} onClick={() => void clearReview()}>
                {copy.clearReview}
              </Button>
              <Button type="button" size="sm" variant="outline" disabled={busy || !proposals.some((proposal) => effectiveProposalStatus(proposal) === "pending_review" && isCommittableProposal(proposal))} onClick={() => void runBatch("approve")}>
                {copy.batchApprove}
              </Button>
              <Button type="button" size="sm" disabled={busy || !proposals.some((proposal) => (effectiveProposalStatus(proposal) === "approved" || effectiveProposalStatus(proposal) === "auto_approved") && isCommittableProposal(proposal))} onClick={() => void runBatch("commit")}>
                {copy.batchCommit}
              </Button>
              <Button type="button" size="sm" variant="ghost" disabled={busy || !proposals.some((proposal) => effectiveProposalStatus(proposal) === "pending_review" || effectiveProposalStatus(proposal) === "draft")} onClick={() => void runBatch("reject")}>
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
              {sortedProposals.map((proposal) => {
                const editable = drafts[proposal.id];
                const payload = proposal.payload_json;
                const canEdit = editable && isCreateTransactionPayload(payload);
                const cashflowPayload = isCashflowProposalPayload(payload) ? payload : null;
                const row = proposal.statement_row_id ? rowsById.get(proposal.statement_row_id) : null;
                const rowRaw = row?.raw_json && typeof row.raw_json === "object" && !Array.isArray(row.raw_json)
                  ? row.raw_json as Record<string, unknown>
                  : null;
                const rawCells = rawCellsFromPayload(payload).length
                  ? rawCellsFromPayload(payload)
                  : Array.isArray(rowRaw?.cells)
                    ? rowRaw.cells.map((cell) => String(cell ?? "").trim()).filter(Boolean)
                    : [];
                const rowSummary = stringValue(payload.summary) ?? stringValue(payload.reason) ?? row?.payee ?? row?.description ?? stringValue(rowRaw?.row_text);
                const payloadAmount = numberValue(payload.amount_cents);
                const payloadDirection = stringValue(payload.direction);
                const payloadLedgerScope = stringValue(payload.ledger_scope);
                const payloadCounterparty = stringValue(payload.counterparty);
                const rawPayload = payload.raw_payload && typeof payload.raw_payload === "object" && !Array.isArray(payload.raw_payload)
                  ? payload.raw_payload as Record<string, unknown>
                  : null;
                const diagnostics = proposal.model_metadata_json.diagnostics &&
                  typeof proposal.model_metadata_json.diagnostics === "object" &&
                  !Array.isArray(proposal.model_metadata_json.diagnostics)
                  ? proposal.model_metadata_json.diagnostics as Record<string, unknown>
                  : null;
                const displayStatus = effectiveProposalStatus(proposal);
                return (
                  <article key={proposal.id} className={proposalCardClassName(proposal)}>
                    <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
                      <div>
                        <div className="flex flex-wrap items-center gap-2">
                          <span className="font-semibold">{copy.proposalTypeLabels[proposal.type] ?? proposal.type.replace(/_/g, " ")}</span>
                          <span className={`rounded-full border px-2 py-0.5 text-xs ${statusTone(displayStatus)}`}>
                            {copy.statusLabels[displayStatus] ?? displayStatus.replace(/_/g, " ")}
                          </span>
                          {isCreateTransactionPayload(proposal.payload_json) ? (
                            <>
                              <span className="rounded-full border border-border px-2 py-0.5 text-xs">
                                {(proposal.payload_json.direction ?? "outflow") === "inflow" ? copy.inflow : copy.outflow}
                              </span>
                              <span className="rounded-full border border-border px-2 py-0.5 text-xs">
                                {proposal.payload_json.ledger_scope ?? "household"}
                              </span>
                            </>
                          ) : null}
                          {proposal.type === "already_covered" || proposal.type === "link_existing_transaction" ? (
                            <span className="rounded-full border border-amber-400/60 bg-amber-100 px-2 py-0.5 text-xs text-amber-900 dark:border-amber-500/40 dark:bg-amber-950/40 dark:text-amber-200">
                              {copy.alreadyCovered}
                            </span>
                          ) : null}
                        </div>
                        <p className="mt-1 text-sm text-muted-foreground">{proposal.explanation}</p>
                      </div>
                      {proposal.type === "needs_review" ? (
                        <p className="rounded-full border border-amber-400/60 bg-amber-100 px-2 py-1 text-xs font-medium text-amber-900 dark:border-amber-500/40 dark:bg-amber-950/40 dark:text-amber-200">
                          {copy.needsDecision}
                        </p>
                      ) : (
                        <p className="text-sm text-muted-foreground">
                          {copy.confidence}: {proposal.confidence === null ? "n/a" : Math.round(proposal.confidence * 100)}%
                        </p>
                      )}
                    </div>

                    {canEdit ? (
                      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-6">
                        <div className="space-y-1 xl:col-span-2">
                          <Label htmlFor={`merchant-${proposal.id}`}>{copy.merchant}</Label>
                          <Input
                            id={`merchant-${proposal.id}`}
                            value={editable.merchant_name}
                            disabled={displayStatus === "committed"}
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
                            disabled={displayStatus === "committed"}
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
                            disabled={displayStatus === "committed"}
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
                            disabled={displayStatus === "committed"}
                            onChange={(event) =>
                              setDrafts((previous) => ({
                                ...previous,
                                [proposal.id]: { ...editable, currency: event.target.value }
                              }))
                            }
                          />
                        </div>
                        <div className="space-y-1">
                          <Label htmlFor={`direction-${proposal.id}`}>{copy.direction}</Label>
                          <select
                            id={`direction-${proposal.id}`}
                            className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                            value={editable.direction}
                            disabled={displayStatus === "committed"}
                            onChange={(event) =>
                              setDrafts((previous) => ({
                                ...previous,
                                [proposal.id]: { ...editable, direction: event.target.value as EditableProposal["direction"] }
                              }))
                            }
                          >
                            <option value="outflow">{copy.outflow}</option>
                            <option value="inflow">{copy.inflow}</option>
                          </select>
                        </div>
                        <div className="space-y-1">
                          <Label htmlFor={`scope-${proposal.id}`}>{copy.ledgerScope}</Label>
                          <select
                            id={`scope-${proposal.id}`}
                            className="flex h-10 w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
                            value={editable.ledger_scope}
                            disabled={displayStatus === "committed"}
                            onChange={(event) =>
                              setDrafts((previous) => ({
                                ...previous,
                                [proposal.id]: { ...editable, ledger_scope: event.target.value as EditableProposal["ledger_scope"] }
                              }))
                            }
                          >
                            <option value="household">{copy.household}</option>
                            <option value="investment">{copy.investment}</option>
                            <option value="internal">{copy.internal}</option>
                            <option value="unknown">{copy.unknown}</option>
                          </select>
                        </div>
                        <label className="flex items-center gap-2 self-end rounded-md border border-border px-3 py-2 text-sm">
                          <input
                            type="checkbox"
                            checked={editable.dashboard_include}
                            disabled={displayStatus === "committed"}
                            onChange={(event) =>
                              setDrafts((previous) => ({
                                ...previous,
                                [proposal.id]: { ...editable, dashboard_include: event.target.checked }
                              }))
                            }
                          />
                          {copy.dashboardInclude}
                        </label>
                      </div>
                    ) : cashflowPayload ? (
                      <div className="grid gap-3 rounded-md border border-border/70 bg-muted/20 p-3 text-sm sm:grid-cols-2 xl:grid-cols-5">
                        <div>
                          <p className="text-xs font-medium uppercase text-muted-foreground">{copy.purchasedAt}</p>
                          <p className="mt-1 font-medium">{new Date(`${cashflowPayload.effective_date}T00:00:00`).toLocaleDateString()}</p>
                        </div>
                        <div>
                          <p className="text-xs font-medium uppercase text-muted-foreground">{copy.amount}</p>
                          <p className="mt-1 font-medium">{formatEurFromCents(cashflowPayload.amount_cents)}</p>
                        </div>
                        <div>
                          <p className="text-xs font-medium uppercase text-muted-foreground">{copy.direction}</p>
                          <p className="mt-1 font-medium">{cashflowPayload.direction === "inflow" ? copy.inflow : copy.outflow}</p>
                        </div>
                        <div>
                          <p className="text-xs font-medium uppercase text-muted-foreground">{copy.ledgerScope}</p>
                          <p className="mt-1 font-medium">{cashflowPayload.ledger_scope ?? copy.household}</p>
                        </div>
                        <div>
                          <p className="text-xs font-medium uppercase text-muted-foreground">{copy.merchant}</p>
                          <p className="mt-1 font-medium">{cashflowPayload.description ?? cashflowPayload.category}</p>
                        </div>
                      </div>
                    ) : proposal.type === "needs_review" || proposal.type === "ignore" ? (
                      <div className="space-y-3 rounded-md border border-border/70 bg-muted/20 p-3 text-sm">
                        <div className="flex flex-wrap items-center justify-between gap-3">
                          <div>
                            <p className="text-xs font-medium uppercase text-muted-foreground">{copy.rowEvidence}</p>
                            <p className="mt-1 font-medium">{rowSummary ?? copy.needsDecision}</p>
                          </div>
                          <div className="flex flex-wrap gap-2 text-xs">
                            {payloadDirection ? <span className="rounded-full border px-2 py-0.5">{payloadDirection === "inflow" ? copy.inflow : copy.outflow}</span> : null}
                            {payloadLedgerScope ? <span className="rounded-full border px-2 py-0.5">{payloadLedgerScope}</span> : null}
                            {payloadAmount !== null ? <span className="rounded-full border px-2 py-0.5">{formatEurFromCents(payloadAmount)}</span> : null}
                          </div>
                        </div>
                        {payloadCounterparty ? (
                          <p className="text-muted-foreground">{copy.merchant}: {payloadCounterparty}</p>
                        ) : null}
                        {rawCells.length ? (
                          <div>
                            <p className="mb-2 text-xs font-medium uppercase text-muted-foreground">{copy.rawCells}</p>
                            <div className="flex flex-wrap gap-2">
                              {rawCells.slice(0, 16).map((cell, index) => (
                                <span key={`${proposal.id}-cell-${index}`} className="rounded border border-border/70 bg-background px-2 py-1 text-xs">
                                  {cell}
                                </span>
                              ))}
                            </div>
                          </div>
                        ) : null}
                        <p className="text-muted-foreground">{copy.suggestedDecision}: {stringValue(payload.reason) ?? proposal.explanation}</p>
                      </div>
                    ) : (
                      <p className="rounded-md bg-muted p-3 text-sm text-muted-foreground">{proposal.explanation ?? copy.unsupported}</p>
                    )}

                    {isCreateTransactionPayload(payload) ? (
                      <p className="mt-3 text-sm text-muted-foreground">
                        {copy.commitResult}: {payload.merchant_name} · {formatEurFromCents(payload.total_gross_cents)}
                      </p>
                    ) : null}
                    {cashflowPayload ? (
                      <p className="mt-3 text-sm text-muted-foreground">
                        {copy.commitResult}: {cashflowPayload.description ?? cashflowPayload.category} · {formatEurFromCents(cashflowPayload.amount_cents)}
                      </p>
                    ) : null}

                    {rawPayload?.input_kind === "document" || proposal.model_metadata_json.file_id ? (
                      <div className="mt-3 rounded-md border border-border/70 bg-muted/20 p-3 text-xs text-muted-foreground">
                        <p className="font-medium text-foreground">{copy.documentEvidence}</p>
                        <div className="mt-2 grid gap-2 sm:grid-cols-3">
                          <span>{copy.extraction}: {String(diagnostics?.ocr_provider ?? proposal.model_metadata_json.extraction_provider ?? "n/a")}</span>
                          <span>{copy.semantic}: {String(proposal.model_metadata_json.semantic_provider ?? diagnostics?.semantic_status ?? "fallback")}</span>
                          <span>{copy.confidence}: {proposal.confidence === null ? "n/a" : `${Math.round(proposal.confidence * 100)}%`}</span>
                        </div>
                        {rawPayload?.evidence ? (
                          <p className="mt-2">{copy.preview}: {String(rawPayload.evidence)}</p>
                        ) : null}
                      </div>
                    ) : null}

                    <div className="mt-4 flex flex-wrap gap-2">
                      {canEdit && displayStatus !== "committed" && displayStatus !== "rejected" ? (
                        <Button type="button" variant="outline" size="sm" className="gap-2" onClick={() => void saveProposal(proposal)}>
                          <Pencil className="h-4 w-4" />
                          {copy.save}
                        </Button>
                      ) : null}
                      {proposal.type === "create_transaction" && displayStatus === "pending_review" ? (
                        <Button type="button" variant="outline" size="sm" className="gap-2" onClick={() => void refreshMatches(proposal)}>
                          <RefreshCw className="h-4 w-4" />
                          {copy.refreshMatches}
                        </Button>
                      ) : null}
                      {proposal.type === "needs_review" && (displayStatus === "pending_review" || displayStatus === "draft") ? (
                        <>
                          <Button
                            type="button"
                            variant="outline"
                            size="sm"
                            className="gap-2"
                            onClick={() => void convertReviewProposal(proposal, stringValue(proposal.payload_json.direction) === "inflow" ? "inflow" : "outflow")}
                          >
                            <Pencil className="h-4 w-4" />
                            {stringValue(proposal.payload_json.direction) === "inflow" ? copy.convertToIncome : copy.convertToTransaction}
                          </Button>
                          <Button type="button" variant="outline" size="sm" className="gap-2" onClick={() => void ignoreReviewProposal(proposal)}>
                            <Check className="h-4 w-4" />
                            {copy.ignoreRow}
                          </Button>
                        </>
                      ) : null}
                      {(displayStatus === "pending_review" || displayStatus === "draft") && isCommittableProposal(proposal) ? (
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
                      ) : displayStatus === "pending_review" || displayStatus === "draft" ? (
                        <Button type="button" variant="ghost" size="sm" className="gap-2" onClick={() => void reject(proposal)}>
                          <X className="h-4 w-4" />
                          {copy.reject}
                        </Button>
                      ) : null}
                      {displayStatus === "approved" || displayStatus === "auto_approved" ? (
                        <Button type="button" size="sm" className="gap-2" onClick={() => void commit(proposal)}>
                          <ReceiptText className="h-4 w-4" />
                          {copy.commit}
                        </Button>
                      ) : null}
                      {displayStatus === "committed" && proposal.commit_result_json?.transaction_id ? (
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
