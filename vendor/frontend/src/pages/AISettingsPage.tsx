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

const OCR_PROVIDER_OPTIONS = [
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
  const { locale, t, tText } = useI18n();
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
  const [connectionTab, setConnectionTab] = useState<"api-key" | "oauth">("oauth");

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
        setCategorizationSaveStatus({
          ok: false,
          error: result.error || tText("Failed to save categorization settings")
        });
        return;
      }
      setCategorizationSaveStatus({ ok: true, error: null });
      setCategorizationApiKey("");
      toast.success(tText("Item categorization settings saved"));
      void queryClient.invalidateQueries({ queryKey: ["ai-settings"] });
    },
    onError: (error) => {
      setCategorizationSaveStatus({
        ok: false,
        error: resolveApiErrorMessage(error, t, tText("Failed to save categorization settings"))
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
        setOauthChatSaveStatus({ ok: false, error: result.error || tText("Failed to save chat model") });
        return;
      }
      setOauthChatSaveStatus({ ok: true, error: null });
      toast.success(tText("Chat model settings saved"));
      void queryClient.invalidateQueries({ queryKey: ["ai-settings"] });
      void queryClient.invalidateQueries({ queryKey: ["ai-agent-config"] });
    },
    onError: (error) => {
      setOauthChatSaveStatus({
        ok: false,
        error: resolveApiErrorMessage(error, t, tText("Failed to save chat model"))
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
    if (categorizationProvider === "api_compatible") {
      setCategorizationBaseUrl(preset.baseUrl);
      setCategorizationModel(inferApiCategorizationModel(preset.baseUrl, preset.model));
    }
  }

  const categorizationRuntimeReady = settings?.categorization_runtime_ready === true;
  const categorizationRuntimeStatus = settings?.categorization_runtime_status || "not_configured";
  const copy = {
    oauthHeroEyebrow: locale === "de" ? "Direkt ohne API-Schlüssel" : "Use it without an API key",
    oauthHeroTitle: locale === "de" ? "ChatGPT / Codex direkt verbinden" : "Connect ChatGPT / Codex directly",
    oauthHeroDescription:
      locale === "de"
        ? "Nutze dein bestehendes ChatGPT- oder Codex-Abo direkt in der Desktop-App. Die Anmeldung ist die empfohlene Standardoption."
        : "Use your existing ChatGPT or Codex subscription directly in the desktop app. This sign-in path is the recommended default.",
    defaultChatModel: locale === "de" ? "Standard-Chatmodell" : "Default chat model",
    defaultChatModelDescription:
      locale === "de"
        ? "Lege fest, welches ChatGPT/Codex-Modell standardmäßig für Chats und Assistenten verwendet wird. Später kannst du es pro Chat weiterhin ändern."
        : "Choose the default ChatGPT/Codex model for chats and assistant actions. You can still change it later per chat.",
    codexModel: locale === "de" ? "Codex-Modell" : "Codex model",
    saving: locale === "de" ? "Speichert..." : "Saving...",
    saveChatModel: locale === "de" ? "Chatmodell speichern" : "Save chat model",
    itemCategorization: locale === "de" ? "Artikelkategorisierung" : "Item categorization",
    itemCategorizationDescription:
      locale === "de"
        ? "Wähle zwischen deiner ChatGPT/Codex-Anmeldung ohne API-Schlüssel oder einem separaten API-kompatiblen Anbieter für günstige Kategorisierungsläufe."
        : "Choose between your ChatGPT/Codex sign-in with no API key or a separate API-compatible provider for cheaper categorization runs.",
    enable: locale === "de" ? "Aktivieren" : "Enable",
    disable: locale === "de" ? "Deaktivieren" : "Disable",
    categorizationStatus: locale === "de" ? "Kategorisierungsstatus" : "Categorization status",
    enabled: locale === "de" ? "Aktiviert" : "Enabled",
    disabled: locale === "de" ? "Deaktiviert" : "Disabled",
    connected: locale === "de" ? "Verbunden" : "Connected",
    categorizationHint:
      locale === "de"
        ? "Wähle `Aktivieren` und speichere die Einstellungen unten, damit zukünftige Reparaturläufe die Kategorisierung verwenden."
        : "Choose `Enable`, then save the settings below to activate categorization for future repair runs.",
    categorizationProvider: locale === "de" ? "Kategorisierungsanbieter" : "Categorization provider",
    codexModelDescription:
      locale === "de"
        ? "Diese Liste spiegelt die Modelle wider, die aktuell in deinem Codex-Abo sichtbar sind. GPT-5.4-Mini bleibt hier der Standard, damit Kategorisierung günstiger als Hauptchats bleibt."
        : "This list mirrors the models currently visible in your Codex subscription UI. GPT-5.4-Mini stays the default here because categorization should remain cheaper than main chat.",
    oauthStatus: locale === "de" ? "OAuth-Status" : "OAuth status",
    runtimeStatus: locale === "de" ? "Laufzeitstatus" : "Runtime status",
    notConnected: locale === "de" ? "nicht verbunden" : "not connected",
    providerSubscription:
      locale === "de" ? "ChatGPT-/Codex-Abo" : "ChatGPT/Codex subscription",
    providerSubscriptionDescription:
      locale === "de"
        ? "Verwendet deine ChatGPT-/Codex-Anmeldung. Kein API-Schlüssel erforderlich."
        : "Uses your ChatGPT/Codex sign-in. No API key required.",
    providerApiCompatible: locale === "de" ? "API-kompatibler Anbieter" : "API-compatible provider",
    providerApiCompatibleDescription:
      locale === "de"
        ? "Verwende ein gehostetes Open-Weight- oder API-Modell mit Basis-URL und API-Schlüssel."
        : "Use a hosted open-weight or API model with base URL and API key.",
    baseUrl: locale === "de" ? "Basis-URL" : "Base URL",
    model: locale === "de" ? "Modell" : "Model",
    apiKey: locale === "de" ? "API-Schlüssel" : "API key",
    categorizationApiKeyConfigured:
      locale === "de"
        ? "Gespeicherter API-Schlüssel für die Kategorisierung ist bereits konfiguriert"
        : "Stored categorization API key is already configured",
    pasteCategorizationApiKey:
      locale === "de" ? "API-Schlüssel für Kategorisierung einfügen" : "Paste categorization API key",
    enableAndSaveCategorization:
      locale === "de" ? "Kategorisierung aktivieren und speichern" : "Enable and save categorization",
    saveCategorizationDisabled:
      locale === "de" ? "Kategorisierung als deaktiviert speichern" : "Save categorization as disabled"
  } as const;

  return (
    <section className="space-y-4">
      <PageHeader title={t("nav.item.aiAssistant")} />
      <Card className="app-dashboard-surface border-border/60">
        <CardContent className="space-y-6 pt-6">
          <div className="app-section-divider mt-0 pt-0">
            <Tabs value={connectionTab} onValueChange={(value) => setConnectionTab(value as "api-key" | "oauth")} className="space-y-5">
              <TabsList className="h-auto w-full justify-start gap-2 rounded-[22px] border border-border/60 p-1.5 app-soft-surface">
                <TabsTrigger
                  value="oauth"
                  className="min-w-[11rem] rounded-[18px] px-4 py-2.5 text-sm text-foreground/75 data-[state=active]:bg-background data-[state=active]:text-foreground dark:data-[state=active]:bg-[var(--app-dashboard-surface-strong)]"
                >
                  {t("pages.aiSettings.tab.oauth")}
                </TabsTrigger>
                <TabsTrigger
                  value="api-key"
                  className="min-w-[11rem] rounded-[18px] px-4 py-2.5 text-sm text-foreground/75 data-[state=active]:bg-background data-[state=active]:text-foreground dark:data-[state=active]:bg-[var(--app-dashboard-surface-strong)]"
                >
                  {t("pages.aiSettings.tab.apiKey")}
                </TabsTrigger>
              </TabsList>

              <TabsContent value="oauth" className="space-y-4">
                <div className="app-dashboard-surface-strong rounded-[28px] border border-border/60 p-5">
                  <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
                    <div className="max-w-2xl space-y-2">
                      <p className="text-xs font-semibold uppercase tracking-[0.28em] text-emerald-600 dark:text-emerald-300">
                        {copy.oauthHeroEyebrow}
                      </p>
                      <h3 className="text-lg font-semibold text-foreground">{copy.oauthHeroTitle}</h3>
                      <p className="text-sm leading-6 text-foreground/80">{copy.oauthHeroDescription}</p>
                    </div>
                    <div className="flex min-w-[16rem] flex-col items-stretch gap-3">
                      <Button
                        onClick={() => void oauthMutation.mutateAsync("openai-codex")}
                        disabled={oauthMutation.isPending || oauthStatus === "pending"}
                      >
                        {t("pages.aiSettings.connect.chatgpt")}
                      </Button>
                      <div className="rounded-[20px] border border-border/60 bg-background/70 px-4 py-3 text-sm text-foreground/80">
                        <p className="font-medium text-foreground">{copy.oauthStatus}</p>
                        <p className={oauthStatus === "connected" ? "mt-1 text-emerald-600 dark:text-emerald-300" : "mt-1 text-foreground/75"}>
                          {oauthStatus === "connected"
                            ? t("pages.aiSettings.oauth.connected")
                            : oauthStatus === "pending"
                              ? t("pages.aiSettings.oauth.waiting")
                              : oauthStatus === "error"
                                ? oauthError || t("pages.aiSettings.oauth.failed")
                                : copy.notConnected}
                        </p>
                      </div>
                    </div>
                  </div>
                </div>

                <div className="app-soft-surface rounded-[24px] border border-border/60 p-5">
                  <div className="space-y-1">
                    <h3 className="text-sm font-semibold text-foreground">{copy.defaultChatModel}</h3>
                    <p className="text-sm leading-6 text-foreground/70">{copy.defaultChatModelDescription}</p>
                  </div>
                  <div className="mt-4 grid gap-4 md:grid-cols-[minmax(0,1fr)_auto] md:items-end">
                    <div className="space-y-2">
                      <Label htmlFor="oauth-chat-model">{copy.codexModel}</Label>
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
                      {saveChatModelMutation.isPending ? copy.saving : copy.saveChatModel}
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

              <TabsContent value="api-key" className="space-y-4">
                <div className="app-soft-surface rounded-[24px] border border-border/60 p-5 space-y-4">
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
                </div>
              </TabsContent>
            </Tabs>
          </div>

          <div className="app-section-divider mt-0 pt-4">
            <div className="app-soft-surface rounded-[24px] border border-border/60 p-5">
              <div className="flex items-start justify-between gap-4">
                <div className="space-y-1">
                  <h3 className="text-sm font-semibold text-foreground">{copy.itemCategorization}</h3>
                  <p className="text-sm leading-6 text-foreground/70">{copy.itemCategorizationDescription}</p>
                </div>
                <div className="flex items-center gap-2">
                  <Button
                    type="button"
                    variant={categorizationEnabled ? "secondary" : "default"}
                    onClick={() => setCategorizationEnabled(true)}
                  >
                    {copy.enable}
                  </Button>
                  <Button
                    type="button"
                    variant={categorizationEnabled ? "outline" : "secondary"}
                    onClick={() => setCategorizationEnabled(false)}
                  >
                    {copy.disable}
                  </Button>
                </div>
              </div>

              <div className="mt-4 space-y-4">
                <div className="flex items-center justify-between rounded-[18px] border border-border/60 bg-background/70 px-3 py-2.5 text-sm">
                  <span className="font-medium text-foreground">{copy.categorizationStatus}</span>
                  <span className={categorizationEnabled ? "text-green-600 dark:text-emerald-300" : "text-foreground/70"}>
                    {categorizationEnabled ? copy.enabled : copy.disabled}
                  </span>
                </div>
                <p className="text-sm text-foreground/70">{copy.categorizationHint}</p>
                <div className="space-y-2">
                  <Label htmlFor="categorization-provider">{copy.categorizationProvider}</Label>
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
                        {option.id === "oauth_codex" ? copy.providerSubscription : copy.providerApiCompatible}
                      </option>
                    ))}
                  </select>
                  <p className="text-sm text-foreground/70">
                    {categorizationProvider === "oauth_codex"
                      ? copy.providerSubscriptionDescription
                      : copy.providerApiCompatibleDescription}
                  </p>
                </div>

                {categorizationProvider === "oauth_codex" ? (
                  <div className="grid gap-4 md:grid-cols-2">
                    <div className="space-y-2">
                      <Label htmlFor="categorization-oauth-model">{copy.codexModel}</Label>
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
                      <p className="text-sm leading-6 text-foreground/70">{copy.codexModelDescription}</p>
                    </div>
                    <div className="space-y-2 rounded-[20px] border border-border/60 bg-background/70 p-4 text-sm">
                      <p>
                        <span className="font-medium text-foreground">{copy.oauthStatus}:</span>{" "}
                        <span className={settings?.oauth_connected ? "text-green-600 dark:text-emerald-300" : "text-foreground/70"}>
                          {settings?.oauth_connected ? copy.connected : copy.notConnected}
                        </span>
                      </p>
                      <p>
                        <span className="font-medium text-foreground">{copy.runtimeStatus}:</span>{" "}
                        <span className={categorizationRuntimeReady ? "text-green-600 dark:text-emerald-300" : "text-foreground/70"}>
                          {tText(categorizationRuntimeStatus.replace(/_/g, " "))}
                        </span>
                      </p>
                    </div>
                  </div>
                ) : (
                  <div className="grid gap-4 md:grid-cols-3">
                    <div className="space-y-2 md:col-span-1">
                      <Label htmlFor="categorization-api-base-url">{copy.baseUrl}</Label>
                      <Input
                        id="categorization-api-base-url"
                        value={categorizationBaseUrl}
                        onChange={(event) => setCategorizationBaseUrl(event.target.value)}
                        placeholder="https://api.openai.com/v1"
                      />
                    </div>
                    <div className="space-y-2 md:col-span-1">
                      <Label htmlFor="categorization-api-model">{copy.model}</Label>
                      <Input
                        id="categorization-api-model"
                        value={categorizationModel}
                        onChange={(event) => setCategorizationModel(event.target.value)}
                        placeholder={inferApiCategorizationModel(categorizationBaseUrl || baseUrl, model)}
                      />
                    </div>
                    <div className="space-y-2 md:col-span-1">
                      <Label htmlFor="categorization-api-key">{copy.apiKey}</Label>
                      <Input
                        id="categorization-api-key"
                        type="password"
                        value={categorizationApiKey}
                        onChange={(event) => setCategorizationApiKey(event.target.value)}
                        placeholder={
                          settings?.categorization_api_key_set
                            ? copy.categorizationApiKeyConfigured
                            : copy.pasteCategorizationApiKey
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
                      ? copy.saving
                      : categorizationEnabled
                        ? copy.enableAndSaveCategorization
                        : copy.saveCategorizationDisabled}
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

            <div className="app-soft-surface rounded-[24px] border border-border/60 p-5 space-y-4">
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

              <div className="flex items-center justify-between rounded-[18px] border border-border/60 bg-background/70 px-3 py-2.5">
                <div className="space-y-1">
                  <p className="text-sm font-medium text-foreground">{t("pages.aiSettings.ocr.enableFallback")}</p>
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
          </div>

          <div className="app-section-divider mt-0 flex items-center justify-between gap-3 rounded-[20px] border border-border/60 app-soft-surface px-4 py-4 text-sm text-muted-foreground">
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
