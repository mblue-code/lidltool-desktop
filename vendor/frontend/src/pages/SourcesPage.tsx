import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { fetchSources, patchSourceSharing } from "@/api/sources";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue
} from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useState } from "react";

export function SourcesPage(): JSX.Element {
  const queryClient = useQueryClient();
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
  const errorMessage = sourcesQuery.error instanceof Error ? sourcesQuery.error.message : null;

  async function updateSharing(sourceId: string, mode: "all" | "manual" | "none"): Promise<void> {
    setStatusMessage(null);
    try {
      await sharingMutation.mutateAsync({ sourceId, mode });
      await queryClient.invalidateQueries({ queryKey: ["sources"] });
      setStatusMessage("Source sharing updated.");
    } catch (error) {
      setStatusMessage(error instanceof Error ? error.message : "Failed to update source sharing.");
    }
  }

  return (
    <section className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>Sources</CardTitle>
        </CardHeader>
        <CardContent>
          {errorMessage ? (
            <Alert variant="destructive" className="mb-4">
              <AlertTitle>Failed to load sources</AlertTitle>
              <AlertDescription>{errorMessage}</AlertDescription>
            </Alert>
          ) : null}
          {statusMessage ? <p className="mb-4 text-sm text-muted-foreground">{statusMessage}</p> : null}
          {sources.length === 0 ? (
            <p className="text-sm text-muted-foreground">No sources available.</p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Display Name</TableHead>
                  <TableHead>Owner</TableHead>
                  <TableHead>Kind</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Enabled</TableHead>
                  <TableHead>Family sharing</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {sources.map((source) => (
                  <TableRow key={source.id}>
                    <TableCell>{source.display_name}</TableCell>
                    <TableCell>{source.owner_display_name || source.owner_username || "—"}</TableCell>
                    <TableCell>{source.kind}</TableCell>
                    <TableCell>
                      <Badge variant={source.status === "healthy" ? "default" : "secondary"}>
                        {source.status}
                      </Badge>
                    </TableCell>
                    <TableCell>{source.enabled ? "Yes" : "No"}</TableCell>
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
                          <SelectItem value="none">Off</SelectItem>
                          <SelectItem value="all">All receipts</SelectItem>
                          <SelectItem value="manual">Manual</SelectItem>
                        </SelectContent>
                      </Select>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </section>
  );
}
