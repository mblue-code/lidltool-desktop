import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { fetchSources, patchSourceSharing } from "@/api/sources";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent } from "@/components/ui/card";
import { EmptyState } from "@/components/shared/EmptyState";
import { PageHeader } from "@/components/shared/PageHeader";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue
} from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useI18n } from "@/i18n";
import { resolveApiErrorMessage } from "@/lib/backend-messages";
import { useState } from "react";

export function SourcesPage() {
  const queryClient = useQueryClient();
  const { t } = useI18n();
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const sourcesQuery = useQuery({
    queryKey: ["sources"],
    queryFn: fetchSources
  });
  const sharingMutation = useMutation({
    mutationFn: ({
      sourceId,
      mode
    }: {
      sourceId: string;
      mode: "all" | "manual" | "none";
    }) => patchSourceSharing(sourceId, mode)
  });

  const sources = sourcesQuery.data?.sources ?? [];
  const errorMessage = sourcesQuery.error
    ? resolveApiErrorMessage(sourcesQuery.error, t, t("pages.sources.loadErrorTitle"))
    : null;

  async function updateSharing(sourceId: string, mode: "all" | "manual" | "none"): Promise<void> {
    setStatusMessage(null);
    try {
      await sharingMutation.mutateAsync({ sourceId, mode });
      await queryClient.invalidateQueries({ queryKey: ["sources"] });
      setStatusMessage(t("pages.sources.sharingUpdated"));
    } catch (error) {
      setStatusMessage(resolveApiErrorMessage(error, t, t("pages.sources.sharingUpdateFailed")));
    }
  }

  return (
    <section className="space-y-4">
      <PageHeader title={t("nav.item.sources")} />
      <Card>
        <CardContent className="pt-6">
          {errorMessage ? (
            <Alert variant="destructive" className="mb-4">
              <AlertTitle>{t("pages.sources.loadErrorTitle")}</AlertTitle>
              <AlertDescription>{errorMessage}</AlertDescription>
            </Alert>
          ) : null}
          {statusMessage ? <p className="mb-4 text-sm text-muted-foreground">{statusMessage}</p> : null}
          {sources.length === 0 ? (
            <EmptyState
              title={t("pages.sources.emptyTitle")}
              description={t("pages.sources.emptyDescription")}
              action={{ label: t("pages.sources.emptyAction"), href: "/connectors" }}
            />
          ) : (
            <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="sticky left-0 z-10 bg-background">{t("pages.sources.displayName")}</TableHead>
                  <TableHead>{t("pages.sources.owner")}</TableHead>
                  <TableHead>{t("pages.sources.kind")}</TableHead>
                  <TableHead>{t("common.status")}</TableHead>
                  <TableHead>{t("pages.sources.enabled")}</TableHead>
                  <TableHead>{t("pages.sources.familySharing")}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {sources.map((source) => (
                  <TableRow key={source.id}>
                    <TableCell className="sticky left-0 z-10 bg-background">{source.display_name}</TableCell>
                    <TableCell>{source.owner_display_name || source.owner_username || "—"}</TableCell>
                    <TableCell>{source.kind}</TableCell>
                    <TableCell>
                      <Badge variant={source.status === "healthy" ? "default" : "secondary"}>
                        {source.status}
                      </Badge>
                    </TableCell>
                    <TableCell>{source.enabled ? t("common.yes") : t("common.no")}</TableCell>
                    <TableCell>
                      <Select
                        value={source.family_share_mode || "none"}
                        onValueChange={(value) =>
                          void updateSharing(source.id, value as "all" | "manual" | "none")
                        }
                        disabled={sharingMutation.isPending}
                      >
                        <SelectTrigger className="w-[170px]">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="none">{t("pages.sources.sharing.off")}</SelectItem>
                          <SelectItem value="all">{t("pages.sources.sharing.all")}</SelectItem>
                          <SelectItem value="manual">{t("pages.sources.sharing.manual")}</SelectItem>
                        </SelectContent>
                      </Select>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            </div>
          )}
        </CardContent>
      </Card>
    </section>
  );
}
