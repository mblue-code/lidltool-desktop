import { useQuery } from "@tanstack/react-query";
import { Download, FileBarChart2, FileJson, ReceiptText } from "lucide-react";

import { fetchReportTemplates } from "@/api/reports";
import { useDateRangeContext } from "@/app/date-range-context";
import { PageHeader } from "@/components/shared/PageHeader";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

function downloadFile(filename: string, contentType: string, content: string) {
  const blob = new Blob([content], { type: contentType });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

export function ReportsPage() {
  const { fromDate, toDate } = useDateRangeContext();
  const templatesQuery = useQuery({
    queryKey: ["reports-page", fromDate, toDate],
    queryFn: () => fetchReportTemplates(fromDate, toDate)
  });
  const templates = templatesQuery.data?.templates ?? [];

  return (
    <div className="space-y-6">
      <PageHeader
        title="Reports"
        description="Export the current finance picture as structured report payloads and keep ready-made templates close to the working surfaces."
      />

      <div className="grid gap-4 xl:grid-cols-3">
        {templates.map((template, index) => (
          <Card key={template.slug} className="app-dashboard-surface border-border/60">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                {index === 0 ? <FileBarChart2 className="h-4 w-4" /> : index === 1 ? <ReceiptText className="h-4 w-4" /> : <FileJson className="h-4 w-4" />}
                {template.title}
              </CardTitle>
              <CardDescription>{template.description}</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              <p className="text-sm text-muted-foreground">
                Template slug: <span className="font-medium text-foreground">{template.slug}</span>
              </p>
              <Button
                type="button"
                onClick={() =>
                  downloadFile(
                    `${template.slug}.json`,
                    "application/json",
                    JSON.stringify(template.payload, null, 2)
                  )
                }
              >
                <Download className="mr-2 h-4 w-4" />
                Export JSON
              </Button>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
