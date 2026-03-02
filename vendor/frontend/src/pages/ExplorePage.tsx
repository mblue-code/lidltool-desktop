import { FormEvent, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { createSavedQuery, deleteSavedQuery, fetchSavedQueries, runQuery, runQueryDsl } from "@/api/query";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

export function ExplorePage(): JSX.Element {
  const queryClient = useQueryClient();
  const [metrics, setMetrics] = useState("net_total,discount_total");
  const [dimensions, setDimensions] = useState("month,source_kind");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [saveName, setSaveName] = useState("");
  const [dsl, setDsl] = useState(
    'SPEND net BY month, source_kind\nWHERE date BETWEEN 2026-01-01..2026-12-31 AND category = "Dairy"\nLIMIT 12'
  );
  const [result, setResult] = useState<Awaited<ReturnType<typeof runQuery>> | null>(null);
  const [errorText, setErrorText] = useState<string | null>(null);

  const savedQuery = useQuery({
    queryKey: ["saved-queries"],
    queryFn: fetchSavedQueries
  });

  const runMutation = useMutation({
    mutationFn: runQuery,
    onSuccess: (data) => {
      setResult(data);
      setErrorText(null);
    },
    onError: (error) => {
      setErrorText(error instanceof Error ? error.message : "Failed to run query.");
    }
  });

  const saveMutation = useMutation({
    mutationFn: createSavedQuery,
    onSuccess: () => {
      setSaveName("");
      void queryClient.invalidateQueries({ queryKey: ["saved-queries"] });
    }
  });
  const dslMutation = useMutation({
    mutationFn: runQueryDsl,
    onSuccess: (data) => {
      setResult(data.result);
      setErrorText(null);
    },
    onError: (error) => {
      setErrorText(error instanceof Error ? error.message : "Failed to run DSL query.");
    }
  });

  const deleteMutation = useMutation({
    mutationFn: deleteSavedQuery,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["saved-queries"] });
    }
  });

  const parsedMetrics = useMemo(
    () =>
      metrics
        .split(",")
        .map((value) => value.trim())
        .filter(Boolean),
    [metrics]
  );
  const parsedDimensions = useMemo(
    () =>
      dimensions
        .split(",")
        .map((value) => value.trim())
        .filter(Boolean),
    [dimensions]
  );

  function submit(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    void runMutation.mutateAsync({
      metrics: parsedMetrics,
      dimensions: parsedDimensions,
      filters: {
        date_from: dateFrom || undefined,
        date_to: dateTo || undefined
      },
      sort_by: parsedMetrics[0] ?? "net_total",
      sort_dir: "desc"
    });
  }

  function saveCurrentQuery(): void {
    if (!saveName.trim()) {
      return;
    }
    void saveMutation.mutateAsync({
      name: saveName.trim(),
      query_json: {
        metrics: parsedMetrics,
        dimensions: parsedDimensions,
        filters: {
          date_from: dateFrom || undefined,
          date_to: dateTo || undefined
        }
      }
    });
  }

  function runDslQuery(): void {
    void dslMutation.mutateAsync(dsl);
  }

  return (
    <section className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>Explore Workbench</CardTitle>
        </CardHeader>
        <CardContent>
          <form className="grid gap-3 md:grid-cols-4" onSubmit={submit}>
            <div className="space-y-1">
              <Label htmlFor="explore-metrics">Metrics (comma separated)</Label>
              <Input id="explore-metrics" value={metrics} onChange={(event) => setMetrics(event.target.value)} />
            </div>
            <div className="space-y-1">
              <Label htmlFor="explore-dimensions">Dimensions (comma separated)</Label>
              <Input
                id="explore-dimensions"
                value={dimensions}
                onChange={(event) => setDimensions(event.target.value)}
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="explore-date-from">From</Label>
              <Input id="explore-date-from" type="date" value={dateFrom} onChange={(event) => setDateFrom(event.target.value)} />
            </div>
            <div className="space-y-1">
              <Label htmlFor="explore-date-to">To</Label>
              <Input id="explore-date-to" type="date" value={dateTo} onChange={(event) => setDateTo(event.target.value)} />
            </div>
            <div className="flex gap-2 md:col-span-4">
              <Button type="submit" disabled={runMutation.isPending}>
                Run query
              </Button>
              <Input
                placeholder="Saved query name"
                value={saveName}
                onChange={(event) => setSaveName(event.target.value)}
              />
              <Button type="button" variant="outline" onClick={saveCurrentQuery} disabled={saveMutation.isPending}>
                Save query
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>DSL Mode</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          <Label htmlFor="explore-dsl">Query DSL</Label>
          <Textarea id="explore-dsl" value={dsl} onChange={(event) => setDsl(event.target.value)} rows={5} />
          <Button type="button" variant="outline" onClick={runDslQuery} disabled={dslMutation.isPending}>
            Run DSL
          </Button>
        </CardContent>
      </Card>

      {errorText ? (
        <Alert variant="destructive">
          <AlertTitle>Query error</AlertTitle>
          <AlertDescription>{errorText}</AlertDescription>
        </Alert>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle>Result</CardTitle>
        </CardHeader>
        <CardContent>
          {result === null ? (
            <p className="text-sm text-muted-foreground">Run a query to see results.</p>
          ) : (
            <div className="space-y-3">
              <p className="text-xs text-muted-foreground">Drilldown token: {result.drilldown_token}</p>
              <Table>
                <TableHeader>
                  <TableRow>
                    {result.columns.map((column) => (
                      <TableHead key={column}>{column}</TableHead>
                    ))}
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {result.rows.map((row, index) => (
                    <TableRow key={`${index}-${row.join("-")}`}>
                      {row.map((value, valueIndex) => (
                        <TableCell key={`${index}-${valueIndex}`}>{String(value)}</TableCell>
                      ))}
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Saved Queries</CardTitle>
        </CardHeader>
        <CardContent>
          {savedQuery.data?.items.length ? (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Name</TableHead>
                  <TableHead>Preset</TableHead>
                  <TableHead>Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {savedQuery.data.items.map((queryItem) => (
                  <TableRow key={queryItem.query_id}>
                    <TableCell>{queryItem.name}</TableCell>
                    <TableCell>{queryItem.is_preset ? "Yes" : "No"}</TableCell>
                    <TableCell>
                      {!queryItem.is_preset ? (
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => void deleteMutation.mutateAsync(queryItem.query_id)}
                        >
                          Delete
                        </Button>
                      ) : (
                        "-"
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          ) : (
            <p className="text-sm text-muted-foreground">No saved queries yet.</p>
          )}
        </CardContent>
      </Card>
    </section>
  );
}
