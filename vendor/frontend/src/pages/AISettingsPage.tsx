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
            toast.success("AI OAuth connected");
            void queryClient.invalidateQueries({ queryKey: ["ai-settings"] });
            return;
          }
          if (status.status === "error") {
            setOauthStatus("error");
            setOauthError(status.error || "OAuth connection failed");
          }
        })
        .catch((error: unknown) => {
          setOauthStatus("error");
          setOauthError(error instanceof Error ? error.message : "Failed to check OAuth status");
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
        setSaveStatus({ ok: false, error: result.error || "Validation failed" });
        return;
      }
      setSaveStatus({ ok: true, error: null });
      setApiKey("");
      toast.success("AI settings saved");
      void queryClient.invalidateQueries({ queryKey: ["ai-settings"] });
    },
    onError: (error) => {
      setSaveStatus({
        ok: false,
        error: error instanceof Error ? error.message : "Failed to save AI settings"
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
      setOauthError(error instanceof Error ? error.message : "Failed to start OAuth flow");
    }
  });
  const disconnectMutation = useMutation({
    mutationFn: disconnectAISettings,
    onSuccess: () => {
      setApiKey("");
      setSaveStatus(null);
      setOauthStatus("idle");
      setOauthError(null);
      toast.success("AI settings disconnected");
      void queryClient.invalidateQueries({ queryKey: ["ai-settings"] });
    },
    onError: (error) => {
      toast.error(error instanceof Error ? error.message : "Failed to disconnect AI settings");
    }
  });

  const settings = settingsQuery.data;
  const connectionLabel = useMemo(() => {
    if (!settings) {
      return "Loading…";
    }
    if (settings.oauth_connected && settings.oauth_provider) {
      return `Connected via ${settings.oauth_provider}`;
    }
    if (settings.api_key_set) {
      return "API key configured";
    }
    return "Not configured";
  }, [settings]);

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
          <CardTitle>AI Assistant</CardTitle>
        </CardHeader>
        <CardContent className="flex items-center justify-between gap-3 text-sm text-muted-foreground">
          <p>{connectionLabel}</p>
          <Button
            variant="destructive"
            onClick={() => void disconnectMutation.mutateAsync()}
            disabled={disconnectMutation.isPending}
          >
            Disconnect
          </Button>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="pt-6">
          <Tabs defaultValue="api-key" className="space-y-4">
            <TabsList>
              <TabsTrigger value="api-key">API Key</TabsTrigger>
              <TabsTrigger value="oauth">Sign in with...</TabsTrigger>
            </TabsList>

            <TabsContent value="api-key" className="space-y-4">
              <div className="grid gap-4 md:grid-cols-2">
                <div className="space-y-2">
                  <Label htmlFor="ai-provider-preset">Provider</Label>
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
                  <Label htmlFor="ai-model">Model</Label>
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
                <Label htmlFor="ai-base-url">Base URL</Label>
                <Input
                  id="ai-base-url"
                  value={baseUrl}
                  onChange={(event) => {
                    setBaseUrl(event.target.value);
                    setActivePreset("custom");
                  }}
                  placeholder="https://api.x.ai/v1"
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="ai-api-key">API Key</Label>
                <Input
                  id="ai-api-key"
                  type="password"
                  value={apiKey}
                  onChange={(event) => setApiKey(event.target.value)}
                  placeholder={settings?.api_key_set ? "●●●●●● configured" : "sk-..."}
                />
              </div>

              <div className="flex items-center gap-3">
                <Button
                  onClick={() => void saveMutation.mutateAsync()}
                  disabled={saveMutation.isPending}
                >
                  {saveMutation.isPending ? "Testing..." : "Test & Save"}
                </Button>
                {saveStatus?.ok ? <p className="text-sm text-green-600">Saved successfully</p> : null}
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
                  Connect with ChatGPT
                </Button>
                <Button
                  variant="outline"
                  disabled
                  title="Not supported yet in this backend build."
                >
                  Connect with GitHub Copilot (coming soon)
                </Button>
                <Button
                  variant="outline"
                  disabled
                  title="Not supported yet in this backend build."
                >
                  Connect with Google (coming soon)
                </Button>
              </div>
              {SUPPORTED_OAUTH_PROVIDERS.size < 3 ? (
                <p className="text-xs text-muted-foreground">
                  Additional OAuth providers will be enabled once backend support lands.
                </p>
              ) : null}

              {oauthStatus === "pending" ? (
                <p className="text-sm text-muted-foreground">Waiting for OAuth callback...</p>
              ) : null}
              {oauthStatus === "connected" ? (
                <p className="text-sm text-green-600">Connected successfully</p>
              ) : null}
              {oauthStatus === "error" ? (
                <p className="text-sm text-destructive">{oauthError || "OAuth failed"}</p>
              ) : null}
            </TabsContent>
          </Tabs>
        </CardContent>
      </Card>
    </section>
  );
}
