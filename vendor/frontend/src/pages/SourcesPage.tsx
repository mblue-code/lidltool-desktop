import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { fetchSources, patchSourceWorkspace } from "@/api/sources";
import { useAccessScope } from "@/app/scope-provider";
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
import {
  STICKY_TABLE_COLUMN_CLASS,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow
} from "@/components/ui/table";
import { useI18n } from "@/i18n";
import { resolveApiErrorMessage } from "@/lib/backend-messages";
import { useState } from "react";

function sourceWorkspaceLabel(source: {
  shared_group_id?: string | null;
  workspace_kind?: string;
  owner_display_name?: string | null;
  owner_username?: string | null;
}): string {
  if (source.shared_group_id) {
    return `Shared group (${source.shared_group_id})`;
  }
  if (source.workspace_kind === "shared_group") {
    return "Shared group";
  }
  return `Personal (${source.owner_display_name || source.owner_username || "unassigned"})`;
}

export function SourcesPage() {
  const queryClient = useQueryClient();
  const { t } = useI18n();
  const { workspace } = useAccessScope();
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const sourcesQuery = useQuery({
    queryKey: ["sources"],
    queryFn: fetchSources
  });
  const sharingMutation = useMutation({
    mutationFn: ({
      sourceId,
      workspaceKind,
      sharedGroupId
    }: {
      sourceId: string;
      workspaceKind: "personal" | "shared_group";
      sharedGroupId?: string;
    }) =>
      patchSourceWorkspace(sourceId, {
        workspace_kind: workspaceKind,
        shared_group_id: sharedGroupId
      })
  });

  const sources = sourcesQuery.data?.sources ?? [];
  const errorMessage = sourcesQuery.error
    ? resolveApiErrorMessage(sourcesQuery.error, t, t("pages.sources.loadErrorTitle"))
    : null;

  async function updateWorkspace(sourceId: string, workspaceKind: "personal" | "shared_group"): Promise<void> {
    setStatusMessage(null);
    try {
      await sharingMutation.mutateAsync({
        sourceId,
        workspaceKind,
        sharedGroupId: workspace.kind === "shared-group" ? workspace.groupId : undefined
      });
      await queryClient.invalidateQueries({ queryKey: ["sources"] });
      setStatusMessage(t("pages.sources.workspaceUpdated"));
    } catch (error) {
      setStatusMessage(resolveApiErrorMessage(error, t, t("pages.sources.workspaceUpdateFailed")));
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
                  <TableHead className={STICKY_TABLE_COLUMN_CLASS}>{t("pages.sources.displayName")}</TableHead>
                  <TableHead>{t("pages.sources.owner")}</TableHead>
                  <TableHead>Workspace</TableHead>
                  <TableHead>{t("pages.sources.kind")}</TableHead>
                  <TableHead>{t("common.status")}</TableHead>
                  <TableHead>{t("pages.sources.enabled")}</TableHead>
                  <TableHead>{t("pages.sources.workspaceDestination")}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {sources.map((source) => (
                  <TableRow key={source.id}>
                    <TableCell className={STICKY_TABLE_COLUMN_CLASS}>{source.display_name}</TableCell>
                    <TableCell>{source.owner_display_name || source.owner_username || "—"}</TableCell>
                    <TableCell>{sourceWorkspaceLabel(source)}</TableCell>
                    <TableCell>{source.kind}</TableCell>
                    <TableCell>
                      <Badge variant={source.status === "healthy" ? "default" : "secondary"}>
                        {source.status}
                      </Badge>
                    </TableCell>
                    <TableCell>{source.enabled ? t("common.yes") : t("common.no")}</TableCell>
                    <TableCell>
                      <Select
                        value={source.shared_group_id ? "shared_group" : "personal"}
                        onValueChange={(value) =>
                          void updateWorkspace(source.id, value as "personal" | "shared_group")
                        }
                        disabled={
                          sharingMutation.isPending ||
                          (workspace.kind !== "shared-group" && !source.shared_group_id)
                        }
                      >
                        <SelectTrigger className="w-[170px]">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value="personal">{t("pages.sources.workspace.personal")}</SelectItem>
                          {workspace.kind === "shared-group" ? (
                            <SelectItem value="shared_group">{t("pages.sources.workspace.sharedCurrent")}</SelectItem>
                          ) : null}
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
