import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import {
  disconnectAISettings,
  fetchAISettings,
  fetchAIOAuthStatus,
  saveAISettings,
  startAIOAuth
} from "@/api/aiSettings";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useI18n } from "@/i18n";
import { resolveApiErrorMessage } from "@/lib/backend-messages";

type ProviderPreset = {
  id: string;
  label: string;
  baseUrl: string;
  model: string;
};

const PROVIDER_PRESETS: ProviderPreset[] = [
  { id: "xai", label: "xAI", baseUrl: "https://api.x.ai/v1", model: "grok-3-mini" },
  {
    id: "together",
    label: "Together",
    baseUrl: "https://api.together.xyz/v1",
    model: "meta-llama/Llama-3.3-70B-Instruct-Turbo"
  },
  {
    id: "nebius",
    label: "Nebius",
    baseUrl: "https://api.studio.nebius.com/v1",
    model: "meta-llama/Meta-Llama-3.1-70B-Instruct"
  },
  { id: "openai", label: "OpenAI", baseUrl: "https://api.openai.com/v1", model: "gpt-4o-mini" },
  { id: "groq", label: "Groq", baseUrl: "https://api.groq.com/openai/v1", model: "llama-3.3-70b-versatile" },
  { id: "ollama", label: "Ollama (local)", baseUrl: "http://localhost:11434/v1", model: "llama3.2" },
  { id: "custom", label: "Custom", baseUrl: "", model: "" }
];

const SUPPORTED_OAUTH_PROVIDERS = new Set<"openai-codex" | "github-copilot" | "google-gemini-cli">([
  "openai-codex"
]);

function inferPreset(baseUrl: string | null, model: string): string {
  const normalizedBase = (baseUrl || "").trim().toLowerCase();
  const normalizedModel = model.trim().toLowerCase();
  const found = PROVIDER_PRESETS.find(
    (preset) =>
      preset.id !== "custom" &&
      preset.baseUrl.toLowerCase() === normalizedBase &&
      preset.model.toLowerCase() === normalizedModel
  );
  return found?.id ?? "custom";
}

export function AISettingsPage(): JSX.Element {
  const queryClient = useQueryClient();
  const { t } = useI18n();
  const settingsQuery = useQuery({
    queryKey: ["ai-settings"],
    queryFn: fetchAISettings
  });

  const [activePreset, setActivePreset] = useState<string>("xai");
  const [baseUrl, setBaseUrl] = useState<string>("");
  const [model, setModel] = useState<string>("grok-3-mini");
  const [apiKey, setApiKey] = useState<string>("");
  const [saveStatus, setSaveStatus] = useState<{ ok: boolean; error: string | null } | null>(null);
  const [oauthStatus, setOauthStatus] = useState<"idle" | "pending" | "connected" | "error">("idle");
  const [oauthError, setOauthError] = useState<string | null>(null);
  const [initialized, setInitialized] = useState(false);

  useEffect(() => {
    if (!settingsQuery.data || initialized) {
      return;
    }
    setBaseUrl(settingsQuery.data.base_url || "");
    setModel(settingsQuery.data.model || "grok-3-mini");
    setActivePreset(inferPreset(settingsQuery.data.base_url, settingsQuery.data.model));
    setOauthStatus(settingsQuery.data.oauth_connected ? "connected" : "idle");
    setInitialized(true);
  }, [initialized, settingsQuery.data]);

  useEffect(() => {
    if (oauthStatus !== "pending") {
      return;
    }
    const interval = window.setInterval(() => {
      void fetchAIOAuthStatus()
        .then((status) => {
          if (status.status === "connected") {
            setOauthStatus("connected");
            setOauthError(null);
            toast.success(t("pages.aiSettings.toast.oauthConnected"));
            void queryClient.invalidateQueries({ queryKey: ["ai-settings"] });
            return;
          }
          if (status.status === "error") {
            setOauthStatus("error");
            setOauthError(status.error || t("pages.aiSettings.oauth.failed"));
          }
        })
        .catch((error: unknown) => {
          setOauthStatus("error");
          setOauthError(resolveApiErrorMessage(error, t, t("pages.aiSettings.error.oauthStatus")));
        });
    }, 1000);
    return () => {
      window.clearInterval(interval);
    };
  }, [oauthStatus, queryClient]);

  const saveMutation = useMutation({
    mutationFn: () =>
      saveAISettings({
        base_url: baseUrl.trim(),
        api_key: apiKey.trim() || undefined,
        model: model.trim()
      }),
    onSuccess: (result) => {
      if (!result.ok) {
        setSaveStatus({ ok: false, error: result.error || t("pages.aiSettings.validationFailed") });
        return;
      }
      setSaveStatus({ ok: true, error: null });
      setApiKey("");
      toast.success(t("pages.aiSettings.toast.saved"));
      void queryClient.invalidateQueries({ queryKey: ["ai-settings"] });
    },
    onError: (error) => {
      setSaveStatus({
        ok: false,
        error: resolveApiErrorMessage(error, t, t("pages.aiSettings.error.save"))
      });
    }
  });

  const oauthMutation = useMutation({
    mutationFn: (provider: "openai-codex" | "github-copilot" | "google-gemini-cli") =>
      startAIOAuth({ provider }),
    onSuccess: (result) => {
      window.open(result.auth_url, "_blank", "noopener,noreferrer");
      setOauthStatus("pending");
      setOauthError(null);
    },
    onError: (error) => {
      setOauthStatus("error");
      setOauthError(resolveApiErrorMessage(error, t, t("pages.aiSettings.error.startOauth")));
    }
  });
  const disconnectMutation = useMutation({
    mutationFn: disconnectAISettings,
    onSuccess: () => {
      setApiKey("");
      setSaveStatus(null);
      setOauthStatus("idle");
      setOauthError(null);
      toast.success(t("pages.aiSettings.toast.disconnected"));
      void queryClient.invalidateQueries({ queryKey: ["ai-settings"] });
    },
    onError: (error) => {
      toast.error(resolveApiErrorMessage(error, t, t("pages.aiSettings.error.disconnect")));
    }
  });

  const settings = settingsQuery.data;
  const connectionLabel = useMemo(() => {
    if (!settings) {
      return t("pages.aiSettings.connection.loading");
    }
    if (settings.oauth_connected && settings.oauth_provider) {
      return t("pages.aiSettings.connection.connectedVia", { provider: settings.oauth_provider });
    }
    if (settings.api_key_set) {
      return t("pages.aiSettings.connection.apiKeyConfigured");
    }
    return t("pages.aiSettings.connection.notConfigured");
  }, [settings, t]);

  function applyPreset(presetId: string): void {
    setActivePreset(presetId);
    const preset = PROVIDER_PRESETS.find((item) => item.id === presetId);
    if (!preset || preset.id === "custom") {
      return;
    }
    setBaseUrl(preset.baseUrl);
    setModel(preset.model);
  }

  return (
    <section className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>{t("pages.aiSettings.title")}</CardTitle>
        </CardHeader>
        <CardContent className="flex items-center justify-between gap-3 text-sm text-muted-foreground">
          <p>{connectionLabel}</p>
          <Button
            variant="destructive"
            onClick={() => void disconnectMutation.mutateAsync()}
            disabled={disconnectMutation.isPending}
          >
            {t("common.disconnect")}
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="pt-6">
          <Tabs defaultValue="api-key" className="space-y-4">
            <TabsList>
              <TabsTrigger value="api-key">{t("pages.aiSettings.tab.apiKey")}</TabsTrigger>
              <TabsTrigger value="oauth">{t("pages.aiSettings.tab.oauth")}</TabsTrigger>
            </TabsList>

            <TabsContent value="api-key" className="space-y-4">
              <div className="grid gap-4 md:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="ai-provider-preset">{t("common.provider")}</Label>
                  <select
                    id="ai-provider-preset"
                    className="h-10 w-full rounded-md border bg-background px-3 text-sm"
                    value={activePreset}
                    onChange={(event) => applyPreset(event.target.value)}
                  >
                    {PROVIDER_PRESETS.map((preset) => (
                      <option key={preset.id} value={preset.id}>
                        {preset.label}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="ai-model">{t("common.model")}</Label>
                  <Input
                    id="ai-model"
                    value={model}
                    onChange={(event) => {
                      setModel(event.target.value);
                      setActivePreset("custom");
                    }}
                  />
                </div>
              </div>

              <div className="space-y-2">
                <Label htmlFor="ai-base-url">{t("common.baseUrl")}</Label>
                <Input
                  id="ai-base-url"
                  value={baseUrl}
                  onChange={(event) => {
                    setBaseUrl(event.target.value);
                    setActivePreset("custom");
                  }}
                  placeholder={t("pages.aiSettings.placeholder.baseUrl")}
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="ai-api-key">{t("pages.aiSettings.field.apiKey")}</Label>
                <Input
                  id="ai-api-key"
                  type="password"
                  value={apiKey}
                  onChange={(event) => setApiKey(event.target.value)}
                  placeholder={
                    settings?.api_key_set
                      ? t("pages.aiSettings.placeholder.apiKeyConfigured")
                      : t("pages.aiSettings.placeholder.apiKey")
                  }
                />
              </div>

              <div className="flex items-center gap-3">
                <Button
                  onClick={() => void saveMutation.mutateAsync()}
                  disabled={saveMutation.isPending}
                >
                  {saveMutation.isPending ? t("pages.aiSettings.testing") : t("pages.aiSettings.testAndSave")}
                </Button>
                {saveStatus?.ok ? (
                  <p className="text-sm text-green-600">{t("pages.aiSettings.savedSuccessfully")}</p>
                ) : null}
                {saveStatus && !saveStatus.ok ? (
                  <p className="text-sm text-destructive">{saveStatus.error}</p>
                ) : null}
              </div>
            </TabsContent>

            <TabsContent value="oauth" className="space-y-4">
              <div className="flex flex-wrap gap-2">
                <Button
                  variant="outline"
                  onClick={() => void oauthMutation.mutateAsync("openai-codex")}
                  disabled={oauthMutation.isPending || oauthStatus === "pending"}
                >
                  {t("pages.aiSettings.connect.chatgpt")}
                </Button>
                <Button
                  variant="outline"
                  disabled
                  title={t("pages.aiSettings.connect.unsupportedTitle")}
                >
                  {t("pages.aiSettings.connect.githubComingSoon")}
                </Button>
                <Button
                  variant="outline"
                  disabled
                  title={t("pages.aiSettings.connect.unsupportedTitle")}
                >
                  {t("pages.aiSettings.connect.googleComingSoon")}
                </Button>
              </div>
              {SUPPORTED_OAUTH_PROVIDERS.size < 3 ? (
                <p className="text-xs text-muted-foreground">
                  {t("pages.aiSettings.additionalProviders")}
                </p>
              ) : null}

              {oauthStatus === "pending" ? (
                <p className="text-sm text-muted-foreground">{t("pages.aiSettings.oauth.waiting")}</p>
              ) : null}
              {oauthStatus === "connected" ? (
                <p className="text-sm text-green-600">{t("pages.aiSettings.oauth.connected")}</p>
              ) : null}
              {oauthStatus === "error" ? (
                <p className="text-sm text-destructive">{oauthError || t("pages.aiSettings.oauth.failed")}</p>
              ) : null}
            </TabsContent>
          </Tabs>
        </CardContent>
      </Card>
    </section>
  );
}
