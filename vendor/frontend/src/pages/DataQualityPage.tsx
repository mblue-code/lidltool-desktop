import { useState } from "react";
import { useQuery } from "@tanstack/react-query";

import { fetchLowConfidenceOcr, fetchUnmatchedItems } from "@/api/quality";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { formatEurFromCents } from "@/utils/format";

export function DataQualityPage() {
  const [threshold, setThreshold] = useState("0.85");

  const unmatchedQuery = useQuery({
    queryKey: ["quality-unmatched"],
    queryFn: () => fetchUnmatchedItems(200)
  });
  const lowConfidenceQuery = useQuery({
    queryKey: ["quality-low-confidence", threshold],
    queryFn: () => fetchLowConfidenceOcr({ threshold: Number(threshold), limit: 200 })
  });

  return (
    <section className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>Data Quality</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-3 md:grid-cols-3">
          <div className="rounded-md border p-3">
            <p className="text-sm text-muted-foreground">Unmatched items</p>
            <p className="text-2xl font-semibold">{unmatchedQuery.data?.count ?? 0}</p>
          </div>
          <div className="rounded-md border p-3">
            <p className="text-sm text-muted-foreground">Low-confidence OCR docs</p>
            <p className="text-2xl font-semibold">{lowConfidenceQuery.data?.count ?? 0}</p>
          </div>
          <div className="space-y-1 rounded-md border p-3">
            <Label htmlFor="quality-threshold">OCR threshold</Label>
            <div className="flex gap-2">
              <Input
                id="quality-threshold"
                value={threshold}
                onChange={(event) => setThreshold(event.target.value)}
                type="number"
                min="0"
                max="1"
                step="0.01"
              />
              <Button variant="outline" onClick={() => lowConfidenceQuery.refetch()}>
                Refresh
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Unmatched Items</CardTitle>
        </CardHeader>
        <CardContent>
          {unmatchedQuery.data?.items.length ? (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Raw name</TableHead>
                  <TableHead>Source</TableHead>
                  <TableHead>Purchases</TableHead>
                  <TableHead>Total spend</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {unmatchedQuery.data.items.map((item) => (
                  <TableRow key={`${item.source_kind}-${item.raw_name}`}>
                    <TableCell>{item.raw_name}</TableCell>
                    <TableCell>{item.source_kind}</TableCell>
                    <TableCell>{item.purchase_count}</TableCell>
                    <TableCell>{formatEurFromCents(item.total_spend_cents)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          ) : (
            <p className="text-sm text-muted-foreground">No unmatched items.</p>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Low-confidence OCR</CardTitle>
        </CardHeader>
        <CardContent>
          {lowConfidenceQuery.data?.items.length ? (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Document</TableHead>
                  <TableHead>Source</TableHead>
                  <TableHead>Confidence</TableHead>
                  <TableHead>Review status</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {lowConfidenceQuery.data.items.map((item) => (
                  <TableRow key={item.document_id}>
                    <TableCell>{item.file_name ?? item.document_id}</TableCell>
                    <TableCell>{item.source_id ?? "-"}</TableCell>
                    <TableCell>{item.ocr_confidence ?? "-"}</TableCell>
                    <TableCell>{item.review_status ?? "-"}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          ) : (
            <p className="text-sm text-muted-foreground">No low-confidence OCR documents.</p>
          )}
        </CardContent>
      </Card>
    </section>
  );
}
