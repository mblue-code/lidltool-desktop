import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { toast } from "sonner";

import { fetchAISettings } from "@/api/aiSettings";
import { fetchQualityRecategorizeStatus, startQualityRecategorize } from "@/api/quality";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useI18n } from "@/i18n";

type ItemRecategorizeControlProps = {
  showSettingsLink?: boolean;
  showStatusText?: boolean;
};

function recategorizeStatusLabel(locale: "en" | "de", status: string): string {
  switch (status) {
    case "queued":
      return locale === "de" ? "Ausstehend" : "Queued";
    case "running":
      return locale === "de" ? "Läuft" : "Running";
    case "completed":
      return locale === "de" ? "Abgeschlossen" : "Completed";
    case "error":
      return locale === "de" ? "Fehlgeschlagen" : "Failed";
    default:
      return status;
  }
}

export function ItemRecategorizeControl({
  showSettingsLink = false,
  showStatusText = false
}: ItemRecategorizeControlProps) {
  const queryClient = useQueryClient();
  const { locale } = useI18n();
  const [jobId, setJobId] = useState<string | null>(null);

  const aiSettingsQuery = useQuery({
    queryKey: ["ai-settings"],
    queryFn: fetchAISettings
  });
  const recategorizeStatusQuery = useQuery({
    queryKey: ["quality-recategorize-status", jobId],
    queryFn: () => fetchQualityRecategorizeStatus(jobId ?? ""),
    enabled: Boolean(jobId),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "queued" || status === "running" ? 1500 : false;
    }
  });

  const recategorizeMutation = useMutation({
    mutationFn: () =>
      startQualityRecategorize({
        only_fallback_other: true,
        include_suspect_model_items: false
      }),
    onSuccess: (job) => {
      setJobId(job.job_id);
      toast.success(locale === "de" ? "KI-Kategorisierung gestartet" : "AI recategorization started");
    },
    onError: (error) => {
      toast.error(
        error instanceof Error
          ? error.message
          : locale === "de"
            ? "Kategorisierung konnte nicht gestartet werden"
            : "Failed to start recategorization"
      );
    }
  });

  const aiEnabled = aiSettingsQuery.data?.enabled === true;
  const categorizationEnabled = aiSettingsQuery.data?.categorization_enabled === true;
  const categorizationReady = aiSettingsQuery.data?.categorization_runtime_ready === true;
  const categorizationStatus = aiSettingsQuery.data?.categorization_runtime_status || "not_configured";
  const recategorizeJob = recategorizeStatusQuery.data;
  const recategorizeRunning =
    recategorizeMutation.isPending ||
    recategorizeJob?.status === "queued" ||
    recategorizeJob?.status === "running";

  useEffect(() => {
    if (!recategorizeJob) {
      return;
    }
    if (recategorizeJob.status === "completed") {
      setJobId(null);
      void queryClient.invalidateQueries({ queryKey: ["products"] });
      toast.success(
        locale === "de"
          ? `${recategorizeJob.updated_item_count} Artikel neu kategorisiert`
          : `Recategorized ${recategorizeJob.updated_item_count} items`
      );
    } else if (recategorizeJob.status === "error") {
      setJobId(null);
      toast.error(
        recategorizeJob.error ||
          (locale === "de" ? "KI-Kategorisierung fehlgeschlagen" : "AI recategorization failed")
      );
    }
  }, [locale, queryClient, recategorizeJob]);

  const buttonTitle = useMemo(() => {
    if (!aiEnabled) {
      return locale === "de" ? "Zuerst KI in den Einstellungen aktivieren" : "Enable AI in settings first";
    }
    if (!categorizationEnabled) {
      return locale === "de"
        ? "Artikelkategorisierung zuerst in den KI-Einstellungen aktivieren"
        : "Enable item categorization in AI settings first";
    }
    if (!categorizationReady) {
      return locale === "de"
        ? `Kategorisierungslaufzeit noch nicht bereit: ${categorizationStatus}`
        : `Categorization runtime is not ready yet: ${categorizationStatus}`;
    }
    return locale === "de"
      ? "KI-Kategorisierung für Artikel in Sonstiges erneut ausführen"
      : "Re-run AI categorization for items still in other";
  }, [aiEnabled, categorizationEnabled, categorizationReady, categorizationStatus, locale]);

  if (!aiEnabled && !showSettingsLink) {
    return null;
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
      <Button
        type="button"
        variant="outline"
        onClick={() => void recategorizeMutation.mutateAsync()}
        disabled={!categorizationEnabled || !categorizationReady || recategorizeRunning}
        title={buttonTitle}
      >
        {recategorizeRunning
          ? (locale === "de" ? "Kategorien werden repariert..." : "Repairing categories...")
          : (locale === "de" ? "Sonstiges reparieren" : "Repair uncategorized items")}
      </Button>
      {showSettingsLink ? (
        <Button asChild variant="ghost" size="sm">
          <Link to="/settings/ai">{locale === "de" ? "KI-Einstellungen" : "AI settings"}</Link>
        </Button>
      ) : null}
      {showStatusText ? (
        <>
          <Badge variant={categorizationEnabled ? "secondary" : "outline"}>
            {categorizationEnabled
              ? (locale === "de" ? "Kategorisierung an" : "Categorization on")
              : (locale === "de" ? "Kategorisierung aus" : "Categorization off")}
          </Badge>
          {!categorizationReady ? (
            <span className="text-xs text-muted-foreground">
              {locale === "de" ? "Laufzeit: " : "Runtime: "}
              {recategorizeStatusLabel(locale, categorizationStatus)}
            </span>
          ) : null}
        </>
      ) : null}
    </div>
  );
}
