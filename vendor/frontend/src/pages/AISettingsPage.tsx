import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import {
  disconnectAISettings,
  fetchAISettings,
  fetchAIOAuthStatus,
  saveAIChatSettings,
  saveAICategorizationSettings,
  saveAISettings,
  startAIOAuth
} from "@/api/aiSettings";
import { fetchOCRSettings, saveOCRSettings } from "@/api/ocrSettings";
import { ConfirmDialog } from "@/components/shared/ConfirmDialog";
import { PageHeader } from "@/components/shared/PageHeader";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
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
  { id: "custom", label: "Custom", baseUrl: "", model: "" }
];

const SUPPORTED_OAUTH_PROVIDERS = new Set<"openai-codex" | "github-copilot" | "google-gemini-cli">([
  "openai-codex"
]);

const OCR_PROVIDER_OPTIONS = [
  { id: "desktop_local", label: "Desktop bundled OCR" },
  { id: "glm_ocr_local", label: "GLM-OCR Local" },
  { id: "openai_compatible", label: "OpenAI-compatible API" }
] as const;

const GLM_LOCAL_API_MODE_OPTIONS = [
  { id: "openai_chat_completion", label: "OpenAI-compatible (recommended)" },
  { id: "ollama_generate", label: "Ollama compatibility" }
] as const;

const CATEGORIZATION_PROVIDER_OPTIONS = [
  {
    id: "oauth_codex",
    label: "ChatGPT Codex subscription",
    description: "Uses your ChatGPT/Codex sign-in. No API key required."
  },
  {
    id: "api_compatible",
    label: "API-compatible provider",
    description: "Use a hosted open-weight or API model with base URL and API key."
  }
] as const;

const CODEX_SUBSCRIPTION_MODELS = [
  { id: "gpt-5.4", label: "GPT-5.4" },
  { id: "gpt-5.4-mini", label: "GPT-5.4-Mini" },
  { id: "gpt-5.3-codex", label: "GPT-5.3-Codex" },
  { id: "gpt-5.3-codex-spark", label: "GPT-5.3-Codex-Spark" },
  { id: "gpt-5.2", label: "GPT-5.2" }
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

function inferApiCategorizationModel(baseUrl: string | null, model: string): string {
  const normalizedBase = (baseUrl || "").trim().toLowerCase();
  if (normalizedBase.includes("api.openai.com")) {
    return "gpt-4o-mini";
  }
  return model.trim() || "gpt-4o-mini";
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

  const [categorizationEnabled, setCategorizationEnabled] = useState(false);
  const [categorizationProvider, setCategorizationProvider] = useState<"oauth_codex" | "api_compatible">(
    "oauth_codex"
  );
  const [categorizationModel, setCategorizationModel] = useState("gpt-5.4-mini");
  const [categorizationBaseUrl, setCategorizationBaseUrl] = useState("");
  const [categorizationApiKey, setCategorizationApiKey] = useState("");
  const [categorizationSaveStatus, setCategorizationSaveStatus] = useState<{
    ok: boolean;
    error: string | null;
  } | null>(null);

  const [oauthStatus, setOauthStatus] = useState<"idle" | "pending" | "connected" | "error">("idle");
  const [oauthError, setOauthError] = useState<string | null>(null);
  const [oauthChatModel, setOauthChatModel] = useState("gpt-5.4");
  const [oauthChatSaveStatus, setOauthChatSaveStatus] = useState<{ ok: boolean; error: string | null } | null>(
    null
  );
  const [initialized, setInitialized] = useState(false);
  const [ocrInitialized, setOcrInitialized] = useState(false);
  const [disconnectOpen, setDisconnectOpen] = useState(false);
  const [ocrDefaultProvider, setOcrDefaultProvider] = useState<string>("desktop_local");
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
    const settings = settingsQuery.data;
    setBaseUrl(settings.base_url || "");
    setModel(settings.model || "grok-3-mini");
    setActivePreset(inferPreset(settings.base_url, settings.model));
    setCategorizationEnabled(settings.categorization_enabled ?? false);
    setCategorizationProvider(settings.categorization_provider ?? "oauth_codex");
    setCategorizationBaseUrl(settings.categorization_base_url || settings.base_url || "");
    setCategorizationModel(
      settings.categorization_model ||
        (settings.categorization_provider === "oauth_codex"
          ? "gpt-5.4-mini"
          : inferApiCategorizationModel(settings.categorization_base_url || settings.base_url, settings.model))
    );
    setOauthChatModel(settings.oauth_model || "gpt-5.4");
    setOauthStatus(settings.oauth_connected ? "connected" : "idle");
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
    if (typeof window === "undefined" || typeof document === "undefined") {
      return;
    }

    let cancelled = false;
    let timeoutId: number | null = null;
    let polling = false;

    const scheduleNextPoll = () => {
      if (cancelled || document.visibilityState !== "visible") {
        return;
      }
      timeoutId = window.setTimeout(() => {
        timeoutId = null;
        void pollStatus();
      }, 1000);
    };

    const pollStatus = async () => {
      if (cancelled || polling || document.visibilityState !== "visible") {
        return;
      }
      polling = true;
      let shouldPollAgain = false;
      try {
        const status = await fetchAIOAuthStatus();
        if (cancelled) {
          return;
        }
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
          return;
        }
        shouldPollAgain = true;
      } catch (error: unknown) {
        if (!cancelled) {
          setOauthStatus("error");
          setOauthError(resolveApiErrorMessage(error, t, t("pages.aiSettings.error.oauthStatus")));
        }
      } finally {
        polling = false;
        if (!cancelled && shouldPollAgain && oauthStatus === "pending" && document.visibilityState === "visible") {
          scheduleNextPoll();
        }
      }
    };

    const handleVisibilityChange = () => {
      if (cancelled) {
        return;
      }
      if (document.visibilityState !== "visible") {
        if (timeoutId !== null) {
          window.clearTimeout(timeoutId);
          timeoutId = null;
        }
        return;
      }
      if (timeoutId === null) {
        void pollStatus();
      }
    };

    document.addEventListener("visibilitychange", handleVisibilityChange);
    void pollStatus();

    return () => {
      cancelled = true;
      document.removeEventListener("visibilitychange", handleVisibilityChange);
      if (timeoutId !== null) {
        window.clearTimeout(timeoutId);
      }
    };
  }, [oauthStatus, queryClient, t]);

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

  const saveCategorizationMutation = useMutation({
    mutationFn: () =>
      saveAICategorizationSettings({
        enabled: categorizationEnabled,
        provider: categorizationProvider,
        model: categorizationModel.trim() || undefined,
        base_url: categorizationProvider === "api_compatible" ? categorizationBaseUrl.trim() || undefined : undefined,
        api_key: categorizationProvider === "api_compatible" ? categorizationApiKey.trim() || undefined : undefined
      }),
    onSuccess: (result) => {
      if (!result.ok) {
        setCategorizationSaveStatus({ ok: false, error: result.error || "Failed to save categorization settings" });
        return;
      }
      setCategorizationSaveStatus({ ok: true, error: null });
      setCategorizationApiKey("");
      toast.success("Item categorization settings saved");
      void queryClient.invalidateQueries({ queryKey: ["ai-settings"] });
    },
    onError: (error) => {
      setCategorizationSaveStatus({
        ok: false,
        error: resolveApiErrorMessage(error, t, "Failed to save categorization settings")
      });
    }
  });

  const saveChatModelMutation = useMutation({
    mutationFn: () =>
      saveAIChatSettings({
        oauth_model: oauthChatModel.trim() || undefined
      }),
    onSuccess: (result) => {
      if (!result.ok) {
        setOauthChatSaveStatus({ ok: false, error: result.error || "Failed to save chat model" });
        return;
      }
      setOauthChatSaveStatus({ ok: true, error: null });
      toast.success("Chat model settings saved");
      void queryClient.invalidateQueries({ queryKey: ["ai-settings"] });
      void queryClient.invalidateQueries({ queryKey: ["ai-agent-config"] });
    },
    onError: (error) => {
      setOauthChatSaveStatus({
        ok: false,
        error: resolveApiErrorMessage(error, t, "Failed to save chat model")
      });
    }
  });

  const saveOCRMutation = useMutation({
    mutationFn: () =>
      saveOCRSettings({
        default_provider: ocrDefaultProvider as "desktop_local" | "glm_ocr_local" | "openai_compatible" | "external_api",
        fallback_enabled: ocrFallbackEnabled,
        fallback_provider: ocrFallbackEnabled
          ? (ocrFallbackProvider as "desktop_local" | "glm_ocr_local" | "openai_compatible" | "external_api")
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
    if (categorizationProvider === "api_compatible") {
      setCategorizationBaseUrl(preset.baseUrl);
      setCategorizationModel(inferApiCategorizationModel(preset.baseUrl, preset.model));
    }
  }

  const categorizationRuntimeReady = settings?.categorization_runtime_ready === true;
  const categorizationRuntimeStatus = settings?.categorization_runtime_status || "not_configured";

  return (
    <section className="space-y-4">
      <PageHeader title={t("nav.item.aiAssistant")} />
      <Card>
        <CardContent className="space-y-6 pt-6">
          <div className="app-section-divider mt-0 pt-0">
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
                  <Button onClick={() => void saveMutation.mutateAsync()} disabled={saveMutation.isPending}>
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
                  <Button variant="outline" disabled title={t("pages.aiSettings.connect.unsupportedTitle")}>
                    {t("pages.aiSettings.connect.githubComingSoon")}
                  </Button>
                  <Button variant="outline" disabled title={t("pages.aiSettings.connect.unsupportedTitle")}>
                    {t("pages.aiSettings.connect.googleComingSoon")}
                  </Button>
                </div>
                {SUPPORTED_OAUTH_PROVIDERS.size < 3 ? (
                  <p className="text-xs text-muted-foreground">{t("pages.aiSettings.additionalProviders")}</p>
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

                <div className="rounded-md border p-4">
                  <div className="space-y-1">
                    <h3 className="text-sm font-medium">Pi agent chat model</h3>
                    <p className="text-xs text-muted-foreground">
                      This is the default ChatGPT/Codex model for chat. The options below mirror the models
                      currently available in your Codex subscription UI. Users can still switch models per
                      chat thread and in the chat side panel.
                    </p>
                  </div>
                  <div className="mt-4 grid gap-4 md:grid-cols-[minmax(0,1fr)_auto] md:items-end">
                    <div className="space-y-2">
                      <Label htmlFor="oauth-chat-model">Codex model</Label>
                      <select
                        id="oauth-chat-model"
                        className="app-soft-surface h-10 w-full rounded-md border px-3 text-sm"
                        value={oauthChatModel}
                        onChange={(event) => setOauthChatModel(event.target.value)}
                      >
                        {CODEX_SUBSCRIPTION_MODELS.map((model) => (
                          <option key={model.id} value={model.id}>
                            {model.label}
                          </option>
                        ))}
                      </select>
                    </div>
                    <Button onClick={() => void saveChatModelMutation.mutateAsync()} disabled={saveChatModelMutation.isPending}>
                      {saveChatModelMutation.isPending ? "Saving..." : "Save chat model"}
                    </Button>
                  </div>
                  {oauthChatSaveStatus?.ok ? (
                    <p className="mt-3 text-sm text-green-600">{t("pages.aiSettings.savedSuccessfully")}</p>
                  ) : null}
                  {oauthChatSaveStatus && !oauthChatSaveStatus.ok ? (
                    <p className="mt-3 text-sm text-destructive">{oauthChatSaveStatus.error}</p>
                  ) : null}
                </div>
              </TabsContent>
            </Tabs>
          </div>

          <div className="app-section-divider mt-0 pt-4">
            <div className="rounded-md border p-4">
              <div className="flex items-start justify-between gap-4">
                <div className="space-y-1">
                  <h3 className="text-sm font-medium">Item categorization</h3>
                  <p className="text-xs text-muted-foreground">
                    Choose one of two modes: use your ChatGPT/Codex subscription with no API key, or
                    use a separate API-compatible provider with its own cheap model.
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <Button
                    type="button"
                    variant={categorizationEnabled ? "secondary" : "default"}
                    onClick={() => setCategorizationEnabled(true)}
                  >
                    Enable
                  </Button>
                  <Button
                    type="button"
                    variant={categorizationEnabled ? "outline" : "secondary"}
                    onClick={() => setCategorizationEnabled(false)}
                  >
                    Disable
                  </Button>
                </div>
              </div>

              <div className="mt-4 space-y-4">
                <div className="flex items-center justify-between rounded-md bg-muted/30 px-3 py-2 text-sm">
                  <span className="font-medium">Categorization status</span>
                  <span className={categorizationEnabled ? "text-green-600" : "text-muted-foreground"}>
                    {categorizationEnabled ? "Enabled" : "Disabled"}
                  </span>
                </div>
                <p className="text-xs text-muted-foreground">
                  Choose `Enable`, then save the settings below to activate categorization for future repair runs.
                </p>
                <div className="space-y-2">
                  <Label htmlFor="categorization-provider">Categorization provider</Label>
                  <select
                    id="categorization-provider"
                    className="app-soft-surface h-10 w-full rounded-md border px-3 text-sm"
                    value={categorizationProvider}
                    onChange={(event) =>
                      setCategorizationProvider(event.target.value as "oauth_codex" | "api_compatible")
                    }
                  >
                    {CATEGORIZATION_PROVIDER_OPTIONS.map((option) => (
                      <option key={option.id} value={option.id}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                  <p className="text-xs text-muted-foreground">
                    {
                      CATEGORIZATION_PROVIDER_OPTIONS.find((option) => option.id === categorizationProvider)
                        ?.description
                    }
                  </p>
                </div>

                {categorizationProvider === "oauth_codex" ? (
                  <div className="grid gap-4 md:grid-cols-2">
                    <div className="space-y-2">
                      <Label htmlFor="categorization-oauth-model">Codex model</Label>
                      <select
                        id="categorization-oauth-model"
                        className="app-soft-surface h-10 w-full rounded-md border px-3 text-sm"
                        value={categorizationModel}
                        onChange={(event) => setCategorizationModel(event.target.value)}
                      >
                        {CODEX_SUBSCRIPTION_MODELS.map((model) => (
                          <option key={model.id} value={model.id}>
                            {model.label}
                          </option>
                        ))}
                      </select>
                      <p className="text-xs text-muted-foreground">
                        This list mirrors the current models visible in your Codex subscription UI. GPT-5.4-Mini
                        is the default here because categorization work should stay cheaper than main chat.
                      </p>
                    </div>
                    <div className="space-y-2 rounded-md bg-muted/40 p-3 text-sm">
                      <p>
                        OAuth status:{" "}
                        <span className={settings?.oauth_connected ? "text-green-600" : "text-muted-foreground"}>
                          {settings?.oauth_connected ? "connected" : "not connected"}
                        </span>
                      </p>
                      <p>
                        Runtime status:{" "}
                        <span className={categorizationRuntimeReady ? "text-green-600" : "text-muted-foreground"}>
                          {categorizationRuntimeStatus}
                        </span>
                      </p>
                    </div>
                  </div>
                ) : (
                  <div className="grid gap-4 md:grid-cols-3">
                    <div className="space-y-2 md:col-span-1">
                      <Label htmlFor="categorization-api-base-url">Base URL</Label>
                      <Input
                        id="categorization-api-base-url"
                        value={categorizationBaseUrl}
                        onChange={(event) => setCategorizationBaseUrl(event.target.value)}
                        placeholder="https://api.openai.com/v1"
                      />
                    </div>
                    <div className="space-y-2 md:col-span-1">
                      <Label htmlFor="categorization-api-model">Model</Label>
                      <Input
                        id="categorization-api-model"
                        value={categorizationModel}
                        onChange={(event) => setCategorizationModel(event.target.value)}
                        placeholder={inferApiCategorizationModel(categorizationBaseUrl || baseUrl, model)}
                      />
                    </div>
                    <div className="space-y-2 md:col-span-1">
                      <Label htmlFor="categorization-api-key">API key</Label>
                      <Input
                        id="categorization-api-key"
                        type="password"
                        value={categorizationApiKey}
                        onChange={(event) => setCategorizationApiKey(event.target.value)}
                        placeholder={
                          settings?.categorization_api_key_set
                            ? "Stored categorization API key is already configured"
                            : "Paste categorization API key"
                        }
                      />
                    </div>
                  </div>
                )}

                <div className="flex items-center gap-3">
                  <Button
                    onClick={() => void saveCategorizationMutation.mutateAsync()}
                    disabled={saveCategorizationMutation.isPending}
                  >
                    {saveCategorizationMutation.isPending
                      ? "Saving..."
                      : categorizationEnabled
                        ? "Enable and save categorization"
                        : "Save categorization as disabled"}
                  </Button>
                  {categorizationSaveStatus?.ok ? (
                    <p className="text-sm text-green-600">{t("pages.aiSettings.savedSuccessfully")}</p>
                  ) : null}
                  {categorizationSaveStatus && !categorizationSaveStatus.ok ? (
                    <p className="text-sm text-destructive">{categorizationSaveStatus.error}</p>
                  ) : null}
                </div>
              </div>
            </div>
          </div>

          <div className="app-section-divider mt-0 pt-4">
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
                  placeholder={glmApiMode === "ollama_generate" ? "http://localhost:11434" : "http://glm-ocr:8080/v1"}
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
              <Button onClick={() => void saveOCRMutation.mutateAsync()} disabled={saveOCRMutation.isPending}>
                {saveOCRMutation.isPending ? t("pages.aiSettings.testing") : t("pages.aiSettings.ocr.save")}
              </Button>
              {ocrSaveStatus?.ok ? (
                <p className="text-sm text-green-600">{t("pages.aiSettings.savedSuccessfully")}</p>
              ) : null}
              {ocrSaveStatus && !ocrSaveStatus.ok ? (
                <p className="text-sm text-destructive">{ocrSaveStatus.error}</p>
              ) : null}
            </div>
          </div>

          <div className="app-section-divider mt-0 flex items-center justify-between gap-3 pt-4 text-sm text-muted-foreground">
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
        </CardContent>
      </Card>
    </section>
  );
}
