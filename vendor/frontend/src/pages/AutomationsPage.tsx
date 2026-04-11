import { zodResolver } from "@hookform/resolvers/zod";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { FormEvent, useState } from "react";
import { useForm } from "react-hook-form";
import { useSearchParams } from "react-router-dom";
import { z } from "zod";

import { automationRulesQueryOptions } from "@/app/queries";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { PageHeader } from "@/components/shared/PageHeader";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
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
import {
  AutomationRule,
  CreateAutomationRuleRequest,
  createAutomationRule,
  deleteAutomationRule,
  runAutomationRule,
  updateAutomationRule
} from "../api/automations";
import { useI18n } from "@/i18n";
import { formatDateTime } from "../utils/format";

type RuleType = "category_auto_tagging" | "budget_alert" | "weekly_summary";
type ConfirmationState =
  | { kind: "run"; rule: AutomationRule }
  | { kind: "toggle"; rule: AutomationRule; nextEnabled: boolean }
  | { kind: "delete"; rule: AutomationRule }
  | null;

type AutomationFormValues = {
  name: string;
  ruleType: RuleType;
  enabled: boolean;
  intervalSeconds: string;
  merchantContains: string;
  minTotalCents: string;
  pattern: string;
  category: string;
  budgetCents: string;
  budgetPeriod: "monthly" | "yearly";
  monthsBack: string;
};

const PAGE_SIZE = 25;

const EMPTY_FORM: AutomationFormValues = {
  name: "",
  ruleType: "category_auto_tagging",
  enabled: true,
  intervalSeconds: "3600",
  merchantContains: "",
  minTotalCents: "",
  pattern: "",
  category: "",
  budgetCents: "",
  budgetPeriod: "monthly",
  monthsBack: "3"
};

const ruleTypeSchema = z.enum(["category_auto_tagging", "budget_alert", "weekly_summary"]);

const automationEditorSchema = z.object({
  name: z.string().max(160, "Name must be 160 characters or less."),
  ruleType: ruleTypeSchema,
  enabled: z.boolean(),
  intervalSeconds: z.string(),
  merchantContains: z.string().max(160, "Merchant filter must be 160 characters or less."),
  minTotalCents: z.string(),
  pattern: z.string(),
  category: z.string(),
  budgetCents: z.string(),
  budgetPeriod: z.enum(["monthly", "yearly"]),
  monthsBack: z.string()
});

const requiredNameSchema = z.string().trim().min(1, "Rule name is required.").max(160, "Rule name is too long.");
const intervalSecondsSchema = z
  .string()
  .trim()
  .min(1, "Interval seconds is required.")
  .refine((value) => /^\d+$/.test(value), "Interval seconds must be a whole number.")
  .transform((value) => Number(value))
  .refine((value) => value >= 60, "Interval seconds must be at least 60.");
const optionalMinTotalSchema = z
  .string()
  .trim()
  .refine((value) => value.length === 0 || /^\d+$/.test(value), "Min total cents must be a whole number.")
  .transform((value) => (value.length === 0 ? undefined : Number(value)));
const budgetCentsSchema = z
  .string()
  .trim()
  .min(1, "Budget cents is required.")
  .refine((value) => /^\d+$/.test(value), "Budget cents must be a whole number.")
  .transform((value) => Number(value))
  .refine((value) => value >= 1, "Budget cents must be at least 1.");
const monthsBackSchema = z
  .string()
  .trim()
  .min(1, "Months back is required.")
  .refine((value) => /^\d+$/.test(value), "Months back must be a whole number.")
  .transform((value) => Number(value))
  .refine((value) => value >= 1 && value <= 24, "Months back must be between 1 and 24.");

const automationSubmitSchema = z.discriminatedUnion("ruleType", [
  z.object({
    name: requiredNameSchema,
    ruleType: z.literal("category_auto_tagging"),
    enabled: z.boolean(),
    intervalSeconds: intervalSecondsSchema,
    merchantContains: z.string().trim().max(160),
    minTotalCents: optionalMinTotalSchema,
    pattern: z.string().trim().min(1, "Pattern is required."),
    category: z.string().trim().min(1, "Category is required.")
  }),
  z.object({
    name: requiredNameSchema,
    ruleType: z.literal("budget_alert"),
    enabled: z.boolean(),
    intervalSeconds: intervalSecondsSchema,
    merchantContains: z.string().trim().max(160),
    minTotalCents: optionalMinTotalSchema,
    budgetCents: budgetCentsSchema,
    budgetPeriod: z.enum(["monthly", "yearly"])
  }),
  z.object({
    name: requiredNameSchema,
    ruleType: z.literal("weekly_summary"),
    enabled: z.boolean(),
    intervalSeconds: intervalSecondsSchema,
    merchantContains: z.string().trim().max(160),
    minTotalCents: optionalMinTotalSchema,
    monthsBack: monthsBackSchema
  })
]);

type AutomationSubmitValues = z.infer<typeof automationSubmitSchema>;

function isEditableRuleType(value: string): value is RuleType {
  return value === "category_auto_tagging" || value === "budget_alert" || value === "weekly_summary";
}

function parseOffset(raw: string | null): number {
  const value = Number(raw ?? "0");
  if (!Number.isFinite(value)) {
    return 0;
  }
  return Math.max(0, Math.floor(value));
}

function toPayload(values: AutomationSubmitValues): CreateAutomationRuleRequest {
  const triggerConfig: Record<string, unknown> = {
    schedule: {
      interval_seconds: values.intervalSeconds
    }
  };
  if (values.merchantContains) {
    triggerConfig.merchant_contains = values.merchantContains;
  }
  if (values.minTotalCents !== undefined) {
    triggerConfig.min_total_cents = values.minTotalCents;
  }

  if (values.ruleType === "category_auto_tagging") {
    return {
      name: values.name,
      rule_type: values.ruleType,
      enabled: values.enabled,
      trigger_config: triggerConfig,
      action_config: {
        pattern: values.pattern,
        category: values.category,
        lookback_days: 7
      }
    };
  }

  if (values.ruleType === "budget_alert") {
    return {
      name: values.name,
      rule_type: values.ruleType,
      enabled: values.enabled,
      trigger_config: triggerConfig,
      action_config: {
        budget_cents: values.budgetCents,
        period: values.budgetPeriod
      }
    };
  }

  return {
    name: values.name,
    rule_type: values.ruleType,
    enabled: values.enabled,
    trigger_config: triggerConfig,
    action_config: {
      months_back: values.monthsBack,
      include_breakdown: true
    }
  };
}

function toFormState(rule: AutomationRule): AutomationFormValues {
  const trigger = rule.trigger_config || {};
  const action = rule.action_config || {};
  const schedule = trigger.schedule as Record<string, unknown> | undefined;
  const editableRuleType: RuleType = isEditableRuleType(rule.rule_type)
    ? rule.rule_type
    : "weekly_summary";
  return {
    name: rule.name,
    ruleType: editableRuleType,
    enabled: rule.enabled,
    intervalSeconds: String((schedule?.interval_seconds as number | undefined) ?? 3600),
    merchantContains: String((trigger.merchant_contains as string | undefined) ?? ""),
    minTotalCents: String((trigger.min_total_cents as number | undefined) ?? ""),
    pattern: String((action.pattern as string | undefined) ?? ""),
    category: String((action.category as string | undefined) ?? ""),
    budgetCents: String((action.budget_cents as number | undefined) ?? ""),
    budgetPeriod: ((action.period as "monthly" | "yearly" | undefined) ?? "monthly"),
    monthsBack: String((action.months_back as number | undefined) ?? 3)
  };
}

export function AutomationsPage() {
  const queryClient = useQueryClient();
  const { t } = useI18n();
  const [searchParams, setSearchParams] = useSearchParams();
  const offset = parseOffset(searchParams.get("offset"));

  const [status, setStatus] = useState<string | null>(null);
  const [mutationError, setMutationError] = useState<string | null>(null);
  const [editingRuleId, setEditingRuleId] = useState<string | null>(null);
  const [editorOpen, setEditorOpen] = useState(false);
  const [confirmation, setConfirmation] = useState<ConfirmationState>(null);
  const [savingForm, setSavingForm] = useState(false);
  const [runningAction, setRunningAction] = useState(false);

  const form = useForm<AutomationFormValues>({
    resolver: zodResolver(automationEditorSchema),
    defaultValues: EMPTY_FORM
  });

  const { data, error, isPending, isFetching } = useQuery(automationRulesQueryOptions(PAGE_SIZE, offset));
  const rules = data?.items ?? [];
  const total = data?.total ?? 0;
  const loading = isPending || isFetching;
  const loadErrorMessage = error instanceof Error ? error.message : null;
  const submitLabel = editingRuleId ? "Save changes" : "Create rule";
  const canGoPrevious = offset > 0;
  const canGoNext = offset + PAGE_SIZE < total;

  const activeRuleType = form.watch("ruleType");
  const activeEnabled = form.watch("enabled");
  const activeBudgetPeriod = form.watch("budgetPeriod");

  function applyValidationIssues(issues: z.ZodIssue[]): void {
    for (const issue of issues) {
      const field = issue.path[0];
      if (
        field === "name" ||
        field === "ruleType" ||
        field === "enabled" ||
        field === "intervalSeconds" ||
        field === "merchantContains" ||
        field === "minTotalCents" ||
        field === "pattern" ||
        field === "category" ||
        field === "budgetCents" ||
        field === "budgetPeriod" ||
        field === "monthsBack"
      ) {
        form.setError(field, { message: issue.message });
      }
    }
  }

  async function submitForm(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();

    form.clearErrors();
    const parsed = automationSubmitSchema.safeParse(form.getValues());
    if (!parsed.success) {
      applyValidationIssues(parsed.error.issues);
      return;
    }

    const payload = toPayload(parsed.data);
    setStatus(null);
    setMutationError(null);
    setSavingForm(true);
    try {
      if (editingRuleId) {
        await updateAutomationRule(editingRuleId, payload);
        setStatus("Rule updated.");
      } else {
        await createAutomationRule(payload);
        setStatus("Rule created.");
      }
      await queryClient.invalidateQueries({ queryKey: ["automation-rules"] });
      setEditorOpen(false);
      setEditingRuleId(null);
      form.reset(EMPTY_FORM);
    } catch (err) {
      setMutationError(err instanceof Error ? err.message : "Failed to save rule");
    } finally {
      setSavingForm(false);
    }
  }

  function beginCreate(): void {
    setEditingRuleId(null);
    form.reset(EMPTY_FORM);
    setMutationError(null);
    setEditorOpen(true);
  }

  function beginEdit(rule: AutomationRule): void {
    if (!isEditableRuleType(rule.rule_type)) {
      setMutationError("This automation template is currently managed from its owning page.");
      return;
    }
    setEditingRuleId(rule.id);
    form.reset(toFormState(rule));
    setMutationError(null);
    setEditorOpen(true);
  }

  function setOffset(nextOffset: number): void {
    const next = new URLSearchParams(searchParams);
    next.set("offset", String(Math.max(0, nextOffset)));
    setSearchParams(next);
  }

  function confirmationTitle(value: ConfirmationState): string {
    if (!value) {
      return "";
    }
    if (value.kind === "delete") {
      return "Delete automation rule";
    }
    if (value.kind === "run") {
      return "Run automation rule";
    }
    return value.nextEnabled ? "Enable automation rule" : "Disable automation rule";
  }

  function confirmationDescription(value: ConfirmationState): string {
    if (!value) {
      return "";
    }
    if (value.kind === "delete") {
      return `Delete '${value.rule.name}' permanently? This action cannot be undone.`;
    }
    if (value.kind === "run") {
      return `Run '${value.rule.name}' now? This creates a new automation execution immediately.`;
    }
    return value.nextEnabled
      ? `Enable '${value.rule.name}' so the scheduler can run it automatically.`
      : `Disable '${value.rule.name}' and stop future scheduled runs.`;
  }

  async function confirmAction(): Promise<void> {
    if (!confirmation) {
      return;
    }
    setStatus(null);
    setMutationError(null);
    setRunningAction(true);
    try {
      if (confirmation.kind === "toggle") {
        await updateAutomationRule(confirmation.rule.id, { enabled: confirmation.nextEnabled });
        setStatus(`Rule ${confirmation.nextEnabled ? "enabled" : "disabled"}.`);
      } else if (confirmation.kind === "run") {
        const run = await runAutomationRule(confirmation.rule.id);
        setStatus(`Rule run queued: ${run.status}.`);
        await queryClient.invalidateQueries({ queryKey: ["automation-executions"] });
      } else {
        await deleteAutomationRule(confirmation.rule.id);
        setStatus("Rule deleted.");
        if (offset > 0 && rules.length === 1) {
          setOffset(offset - PAGE_SIZE);
        }
      }
      await queryClient.invalidateQueries({ queryKey: ["automation-rules"] });
      setConfirmation(null);
    } catch (err) {
      setMutationError(err instanceof Error ? err.message : "Failed to run action");
    } finally {
      setRunningAction(false);
    }
  }

  function closeEditor(nextOpen: boolean): void {
    setEditorOpen(nextOpen);
    if (!nextOpen) {
      setEditingRuleId(null);
      form.reset(EMPTY_FORM);
      setMutationError(null);
    }
  }

  function confirmButtonLabel(value: ConfirmationState): string {
    if (!value) {
      return "Confirm";
    }
    if (value.kind === "delete") {
      return "Delete";
    }
    if (value.kind === "run") {
      return "Run now";
    }
    return value.nextEnabled ? "Enable" : "Disable";
  }

  return (
    <section className="space-y-4">
      <PageHeader title={t("nav.item.automations")} description={t("pages.automations.description")}>
        <Button type="button" onClick={beginCreate}>
          Create rule
        </Button>
      </PageHeader>

      {status ? (
        <Alert>
          <AlertTitle>Status</AlertTitle>
          <AlertDescription>{status}</AlertDescription>
        </Alert>
      ) : null}
      {loadErrorMessage ? (
        <Alert variant="destructive">
          <AlertTitle>Failed to load automations</AlertTitle>
          <AlertDescription>{loadErrorMessage}</AlertDescription>
        </Alert>
      ) : null}
      {mutationError ? (
        <Alert variant="destructive">
          <AlertTitle>Automation error</AlertTitle>
          <AlertDescription>{mutationError}</AlertDescription>
        </Alert>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle>Rule list</CardTitle>
        </CardHeader>
        <CardContent>
          {loading ? <p className="text-sm text-muted-foreground">Loading automations...</p> : null}
          <div className="overflow-x-auto">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className={STICKY_TABLE_COLUMN_CLASS}>Name</TableHead>
                <TableHead>Template</TableHead>
                <TableHead>Enabled</TableHead>
                <TableHead>Interval</TableHead>
                <TableHead>Next run</TableHead>
                <TableHead>Last run</TableHead>
                <TableHead>Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rules.map((rule) => {
                const schedule = rule.trigger_config.schedule as Record<string, unknown> | undefined;
                const intervalSeconds = (schedule?.interval_seconds as number | undefined) ?? 3600;
                return (
                  <TableRow key={rule.id}>
                    <TableCell className={STICKY_TABLE_COLUMN_CLASS}>{rule.name}</TableCell>
                    <TableCell>{rule.rule_type.replace(/_/g, " ")}</TableCell>
                    <TableCell>
                      <Badge variant={rule.enabled ? "default" : "secondary"}>
                        {rule.enabled ? "enabled" : "disabled"}
                      </Badge>
                    </TableCell>
                    <TableCell>{intervalSeconds}s</TableCell>
                    <TableCell>{rule.next_run_at ? formatDateTime(rule.next_run_at) : "-"}</TableCell>
                    <TableCell>{rule.last_run_at ? formatDateTime(rule.last_run_at) : "-"}</TableCell>
                    <TableCell>
                      <div className="flex flex-wrap gap-2">
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          onClick={() => beginEdit(rule)}
                          disabled={!isEditableRuleType(rule.rule_type)}
                        >
                          Edit
                        </Button>
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          onClick={() =>
                            setConfirmation({
                              kind: "toggle",
                              rule,
                              nextEnabled: !rule.enabled
                            })
                          }
                        >
                          {rule.enabled ? "Disable" : "Enable"}
                        </Button>
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          onClick={() => setConfirmation({ kind: "run", rule })}
                        >
                          Run
                        </Button>
                        <Button
                          type="button"
                          variant="destructive"
                          size="sm"
                          onClick={() => setConfirmation({ kind: "delete", rule })}
                        >
                          Delete
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                );
              })}
              {rules.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={7}>No automation rules yet.</TableCell>
                </TableRow>
              ) : null}
            </TableBody>
          </Table>
          </div>

          <div className="mt-4 flex flex-wrap items-center justify-between gap-2">
            <p className="text-sm text-muted-foreground">
              Showing {total === 0 ? 0 : offset + 1}-{Math.min(offset + PAGE_SIZE, total)} of {total}
            </p>
            <div className="flex gap-2">
              <Button type="button" variant="outline" disabled={!canGoPrevious} onClick={() => setOffset(offset - PAGE_SIZE)}>
                Previous
              </Button>
              <Button type="button" variant="outline" disabled={!canGoNext} onClick={() => setOffset(offset + PAGE_SIZE)}>
                Next
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      <Dialog open={editorOpen} onOpenChange={closeEditor}>
        <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-3xl">
          <DialogHeader>
            <DialogTitle>{editingRuleId ? "Edit automation rule" : "Create automation rule"}</DialogTitle>
            <DialogDescription>
              Configure the template and trigger details. Fields update automatically for each template.
            </DialogDescription>
          </DialogHeader>

          <form className="grid gap-3 md:grid-cols-2" onSubmit={(event) => void submitForm(event)}>
            <div className="space-y-2 md:col-span-2">
              <Label htmlFor="name">Name</Label>
              <Input id="name" {...form.register("name")} />
              {form.formState.errors.name ? (
                <p className="text-xs text-destructive">{form.formState.errors.name.message}</p>
              ) : null}
            </div>
            <div className="space-y-2">
              <Label htmlFor="automation-rule-type">Template</Label>
              <Select
                value={activeRuleType}
                onValueChange={(value) =>
                  form.setValue("ruleType", value as RuleType, {
                    shouldDirty: true,
                    shouldValidate: true
                  })
                }
              >
                <SelectTrigger id="automation-rule-type">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="category_auto_tagging">Category auto-tagging</SelectItem>
                  <SelectItem value="budget_alert">Budget alert</SelectItem>
                  <SelectItem value="weekly_summary">Weekly summary</SelectItem>
                </SelectContent>
              </Select>
              {form.formState.errors.ruleType ? (
                <p className="text-xs text-destructive">{form.formState.errors.ruleType.message}</p>
              ) : null}
            </div>
            <div className="space-y-2">
              <Label htmlFor="automation-enabled">Enabled</Label>
              <Select
                value={activeEnabled ? "true" : "false"}
                onValueChange={(value) =>
                  form.setValue("enabled", value === "true", {
                    shouldDirty: true,
                    shouldValidate: true
                  })
                }
              >
                <SelectTrigger id="automation-enabled">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="true">Enabled</SelectItem>
                  <SelectItem value="false">Disabled</SelectItem>
                </SelectContent>
              </Select>
              {form.formState.errors.enabled ? (
                <p className="text-xs text-destructive">{form.formState.errors.enabled.message}</p>
              ) : null}
            </div>
            <div className="space-y-2">
              <Label htmlFor="interval-seconds">Interval seconds</Label>
              <Input id="interval-seconds" type="number" {...form.register("intervalSeconds")} />
              {form.formState.errors.intervalSeconds ? (
                <p className="text-xs text-destructive">{form.formState.errors.intervalSeconds.message}</p>
              ) : null}
            </div>
            <div className="space-y-2">
              <Label htmlFor="merchant-contains">Merchant contains</Label>
              <Input id="merchant-contains" {...form.register("merchantContains")} />
              {form.formState.errors.merchantContains ? (
                <p className="text-xs text-destructive">{form.formState.errors.merchantContains.message}</p>
              ) : null}
            </div>
            <div className="space-y-2">
              <Label htmlFor="min-total-cents">Min total cents</Label>
              <Input id="min-total-cents" type="number" {...form.register("minTotalCents")} />
              {form.formState.errors.minTotalCents ? (
                <p className="text-xs text-destructive">{form.formState.errors.minTotalCents.message}</p>
              ) : null}
            </div>

            {activeRuleType === "category_auto_tagging" ? (
              <>
                <div className="space-y-2">
                  <Label htmlFor="pattern">Pattern</Label>
                  <Input id="pattern" {...form.register("pattern")} />
                  {form.formState.errors.pattern ? (
                    <p className="text-xs text-destructive">{form.formState.errors.pattern.message}</p>
                  ) : null}
                </div>
                <div className="space-y-2">
                  <Label htmlFor="category">Category</Label>
                  <Input id="category" {...form.register("category")} />
                  {form.formState.errors.category ? (
                    <p className="text-xs text-destructive">{form.formState.errors.category.message}</p>
                  ) : null}
                </div>
              </>
            ) : null}

            {activeRuleType === "budget_alert" ? (
              <>
                <div className="space-y-2">
                  <Label htmlFor="budget-cents">Budget cents</Label>
                  <Input id="budget-cents" type="number" {...form.register("budgetCents")} />
                  {form.formState.errors.budgetCents ? (
                    <p className="text-xs text-destructive">{form.formState.errors.budgetCents.message}</p>
                  ) : null}
                </div>
                <div className="space-y-2">
                  <Label htmlFor="automation-budget-period">Budget period</Label>
                  <Select
                    value={activeBudgetPeriod}
                    onValueChange={(value) =>
                      form.setValue("budgetPeriod", value as "monthly" | "yearly", {
                        shouldDirty: true,
                        shouldValidate: true
                      })
                    }
                  >
                    <SelectTrigger id="automation-budget-period">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="monthly">Monthly</SelectItem>
                      <SelectItem value="yearly">Yearly</SelectItem>
                    </SelectContent>
                  </Select>
                  {form.formState.errors.budgetPeriod ? (
                    <p className="text-xs text-destructive">{form.formState.errors.budgetPeriod.message}</p>
                  ) : null}
                </div>
              </>
            ) : null}

            {activeRuleType === "weekly_summary" ? (
              <div className="space-y-2">
                <Label htmlFor="months-back">Months back</Label>
                <Input id="months-back" type="number" {...form.register("monthsBack")} />
                {form.formState.errors.monthsBack ? (
                  <p className="text-xs text-destructive">{form.formState.errors.monthsBack.message}</p>
                ) : null}
              </div>
            ) : null}

            <DialogFooter className="md:col-span-2">
              <Button type="button" variant="outline" onClick={() => closeEditor(false)} disabled={savingForm}>
                Cancel
              </Button>
              <Button type="submit" disabled={savingForm}>
                {savingForm ? "Saving..." : submitLabel}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      <Dialog open={confirmation !== null} onOpenChange={(open) => !open && setConfirmation(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{confirmationTitle(confirmation)}</DialogTitle>
            <DialogDescription>{confirmationDescription(confirmation)}</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => setConfirmation(null)}
              disabled={runningAction}
            >
              Cancel
            </Button>
            <Button
              type="button"
              variant={confirmation?.kind === "delete" ? "destructive" : "default"}
              onClick={() => void confirmAction()}
              disabled={runningAction}
            >
              {runningAction ? "Working..." : confirmButtonLabel(confirmation)}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </section>
  );
}
