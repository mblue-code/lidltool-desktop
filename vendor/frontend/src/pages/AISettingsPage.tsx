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
import { fetchOCRSettings, saveOCRSettings } from "@/api/ocrSettings";
import { ConfirmDialog } from "@/components/shared/ConfirmDialog";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { PageHeader } from "@/components/shared/PageHeader";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
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
  {
    id: "local-openai-compatible",
    label: "Local OpenAI-compatible",
    baseUrl: "http://localhost:8000/v1",
    model: "Qwen/Qwen3.5-0.8B"
  },
  { id: "custom", label: "Custom", baseUrl: "", model: "" }
];

const SUPPORTED_OAUTH_PROVIDERS = new Set<"openai-codex" | "github-copilot" | "google-gemini-cli">([
  "openai-codex"
]);
const OCR_PROVIDER_OPTIONS = [
  { id: "glm_ocr_local", label: "GLM-OCR Local" },
  { id: "openai_compatible", label: "OpenAI-compatible API" }
] as const;
const GLM_LOCAL_API_MODE_OPTIONS = [
  { id: "openai_chat_completion", label: "OpenAI-compatible (recommended)" },
  { id: "ollama_generate", label: "Ollama compatibility" }
] as const;

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

export function AISettingsPage() {
  const queryClient = useQueryClient();
  const { t } = useI18n();
  const settingsQuery = useQuery({
    queryKey: ["ai-settings"],
    queryFn: fetchAISettings
  });
  const ocrSettingsQuery = useQuery({
    queryKey: ["ocr-settings"],
    queryFn: fetchOCRSettings
  });

  const [activePreset, setActivePreset] = useState<string>("xai");
  const [baseUrl, setBaseUrl] = useState<string>("");
  const [model, setModel] = useState<string>("grok-3-mini");
  const [apiKey, setApiKey] = useState<string>("");
  const [saveStatus, setSaveStatus] = useState<{ ok: boolean; error: string | null } | null>(null);
  const [oauthStatus, setOauthStatus] = useState<"idle" | "pending" | "connected" | "error">("idle");
  const [oauthError, setOauthError] = useState<string | null>(null);
  const [initialized, setInitialized] = useState(false);
  const [ocrInitialized, setOcrInitialized] = useState(false);
  const [disconnectOpen, setDisconnectOpen] = useState(false);
  const [ocrDefaultProvider, setOcrDefaultProvider] = useState<string>("glm_ocr_local");
  const [ocrFallbackEnabled, setOcrFallbackEnabled] = useState(false);
  const [ocrFallbackProvider, setOcrFallbackProvider] = useState<string>("openai_compatible");
  const [glmBaseUrl, setGlmBaseUrl] = useState("");
  const [glmApiMode, setGlmApiMode] = useState<"ollama_generate" | "openai_chat_completion">(
    "openai_chat_completion"
  );
  const [glmModel, setGlmModel] = useState("glm-ocr");
  const [ocrOpenaiBaseUrl, setOcrOpenaiBaseUrl] = useState("");
  const [ocrOpenaiModel, setOcrOpenaiModel] = useState("");
  const [ocrSaveStatus, setOcrSaveStatus] = useState<{ ok: boolean; error: string | null } | null>(null);

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
    if (!ocrSettingsQuery.data || ocrInitialized) {
      return;
    }
    setOcrDefaultProvider(ocrSettingsQuery.data.default_provider);
    setOcrFallbackEnabled(ocrSettingsQuery.data.fallback_enabled);
    setOcrFallbackProvider(ocrSettingsQuery.data.fallback_provider || "openai_compatible");
    setGlmBaseUrl(ocrSettingsQuery.data.glm_local_base_url || "");
    setGlmApiMode(ocrSettingsQuery.data.glm_local_api_mode);
    setGlmModel(ocrSettingsQuery.data.glm_local_model || "glm-ocr");
    setOcrOpenaiBaseUrl(ocrSettingsQuery.data.openai_base_url || "");
    setOcrOpenaiModel(ocrSettingsQuery.data.openai_model || "");
    setOcrInitialized(true);
  }, [ocrInitialized, ocrSettingsQuery.data]);

  useEffect(() => {
    if (ocrFallbackProvider !== ocrDefaultProvider) {
      return;
    }
    const nextFallback = OCR_PROVIDER_OPTIONS.find((option) => option.id !== ocrDefaultProvider);
    if (nextFallback) {
      setOcrFallbackProvider(nextFallback.id);
    }
  }, [ocrDefaultProvider, ocrFallbackProvider]);

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
  const saveOCRMutation = useMutation({
    mutationFn: () =>
      saveOCRSettings({
        default_provider: ocrDefaultProvider as "glm_ocr_local" | "openai_compatible",
        fallback_enabled: ocrFallbackEnabled,
        fallback_provider: ocrFallbackEnabled
          ? (ocrFallbackProvider as "glm_ocr_local" | "openai_compatible")
          : undefined,
        glm_local_base_url: glmBaseUrl.trim(),
        glm_local_api_mode: glmApiMode,
        glm_local_model: glmModel.trim(),
        openai_base_url: ocrOpenaiBaseUrl.trim() || undefined,
        openai_model: ocrOpenaiModel.trim() || undefined
      }),
    onSuccess: (result) => {
      if (!result.ok) {
        setOcrSaveStatus({ ok: false, error: result.error || t("pages.aiSettings.ocr.validationFailed") });
        return;
      }
      setOcrSaveStatus({ ok: true, error: null });
      toast.success(t("pages.aiSettings.ocr.toast.saved"));
      void queryClient.invalidateQueries({ queryKey: ["ocr-settings"] });
    },
    onError: (error) => {
      setOcrSaveStatus({
        ok: false,
        error: resolveApiErrorMessage(error, t, t("pages.aiSettings.ocr.error.save"))
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
      <PageHeader title={t("nav.item.aiAssistant")} />
      <Card>
        <CardContent className="space-y-4 pt-6">
          <div className="space-y-1">
            <h2 className="text-base font-semibold">{t("pages.aiSettings.ocr.title")}</h2>
            <p className="text-sm text-muted-foreground">{t("pages.aiSettings.ocr.description")}</p>
          </div>


          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="ocr-default-provider">{t("pages.aiSettings.ocr.primaryProvider")}</Label>
              <select
                id="ocr-default-provider"
                className="app-soft-surface h-10 w-full rounded-md border px-3 text-sm"
                value={ocrDefaultProvider}
                onChange={(event) => setOcrDefaultProvider(event.target.value)}
              >
                {OCR_PROVIDER_OPTIONS.map((option) => (
                  <option key={option.id} value={option.id}>
                    {option.label}
                  </option>
                ))}
              </select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="ocr-fallback-provider">{t("pages.aiSettings.ocr.fallbackProvider")}</Label>
              <select
                id="ocr-fallback-provider"
                className="app-soft-surface h-10 w-full rounded-md border px-3 text-sm"
                value={ocrFallbackProvider}
                onChange={(event) => setOcrFallbackProvider(event.target.value)}
                disabled={!ocrFallbackEnabled}
              >
                {OCR_PROVIDER_OPTIONS.filter((option) => option.id !== ocrDefaultProvider).map((option) => (
                  <option key={option.id} value={option.id}>
                    {option.label}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="flex items-center justify-between rounded-md border px-3 py-2">
            <div className="space-y-1">
              <p className="text-sm font-medium">{t("pages.aiSettings.ocr.enableFallback")}</p>
              <p className="text-xs text-muted-foreground">{t("pages.aiSettings.ocr.enableFallbackHint")}</p>
            </div>
            <Switch checked={ocrFallbackEnabled} onCheckedChange={setOcrFallbackEnabled} />
          </div>

          <div className="grid gap-4 md:grid-cols-3">
            <div className="space-y-2">
              <Label htmlFor="ocr-glm-base-url">{t("pages.aiSettings.ocr.glmBaseUrl")}</Label>
              <Input
                id="ocr-glm-base-url"
                value={glmBaseUrl}
                onChange={(event) => setGlmBaseUrl(event.target.value)}
                placeholder={
                  glmApiMode === "ollama_generate"
                    ? "http://localhost:11434"
                    : "http://glm-ocr:8080/v1"
                }
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="ocr-glm-api-mode">{t("pages.aiSettings.ocr.glmApiMode")}</Label>
              <select
                id="ocr-glm-api-mode"
                className="app-soft-surface h-10 w-full rounded-md border px-3 text-sm"
                value={glmApiMode}
                onChange={(event) =>
                  setGlmApiMode(event.target.value as "ollama_generate" | "openai_chat_completion")
                }
              >
                {GLM_LOCAL_API_MODE_OPTIONS.map((option) => (
                  <option key={option.id} value={option.id}>
                    {option.label}
                  </option>
                ))}
              </select>
              <p className="text-xs text-muted-foreground">{t("pages.aiSettings.ocr.glmApiModeHint")}</p>
            </div>
            <div className="space-y-2">
              <Label htmlFor="ocr-glm-model">{t("pages.aiSettings.ocr.glmModel")}</Label>
              <Input
                id="ocr-glm-model"
                value={glmModel}
                onChange={(event) => setGlmModel(event.target.value)}
                placeholder="glm-ocr"
              />
            </div>
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="ocr-api-base-url">{t("pages.aiSettings.ocr.apiBaseUrl")}</Label>
              <Input
                id="ocr-api-base-url"
                value={ocrOpenaiBaseUrl}
                onChange={(event) => setOcrOpenaiBaseUrl(event.target.value)}
                placeholder="https://api.openai.com/v1"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="ocr-api-model">{t("pages.aiSettings.ocr.apiModel")}</Label>
              <Input
                id="ocr-api-model"
                value={ocrOpenaiModel}
                onChange={(event) => setOcrOpenaiModel(event.target.value)}
                placeholder="gpt-4o-mini"
              />
            </div>
          </div>

          <p className="text-xs text-muted-foreground">
            {ocrSettingsQuery.data?.openai_credentials_ready
              ? t("pages.aiSettings.ocr.credentialsReady")
              : t("pages.aiSettings.ocr.credentialsMissing")}
          </p>

          <div className="flex items-center gap-3">
            <Button
              onClick={() => void saveOCRMutation.mutateAsync()}
              disabled={saveOCRMutation.isPending}
            >
              {saveOCRMutation.isPending ? t("pages.aiSettings.testing") : t("pages.aiSettings.ocr.save")}
            </Button>
            {ocrSaveStatus?.ok ? (
              <p className="text-sm text-green-600">{t("pages.aiSettings.savedSuccessfully")}</p>
            ) : null}
            {ocrSaveStatus && !ocrSaveStatus.ok ? (
              <p className="text-sm text-destructive">{ocrSaveStatus.error}</p>
            ) : null}
          </div>
          <div className="app-section-divider mt-4 flex items-center justify-between gap-3 pt-4 text-sm text-muted-foreground">
            <p>{connectionLabel}</p>
            <Button
              variant="destructive"
              onClick={() => setDisconnectOpen(true)}
              disabled={disconnectMutation.isPending}
            >
              {t("common.disconnect")}
            </Button>
            <ConfirmDialog
              open={disconnectOpen}
              onOpenChange={setDisconnectOpen}
              title={t("pages.aiSettings.disconnectConfirmTitle")}
              description={t("pages.aiSettings.disconnectConfirmDescription")}
              variant="destructive"
              confirmLabel={t("common.disconnect")}
              onConfirm={() => void disconnectMutation.mutateAsync()}
            />
          </div>

          <div className="app-section-divider mt-4 pt-4">
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
                    className="app-soft-surface h-10 w-full rounded-md border px-3 text-sm"
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
          </div>
        </CardContent>
      </Card>
    </section>
  );
}
