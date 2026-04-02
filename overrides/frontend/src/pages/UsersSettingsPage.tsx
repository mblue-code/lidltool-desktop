import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FormEvent, useMemo, useState } from "react";

import { PageHeader } from "@/components/shared/PageHeader";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
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
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { runSystemBackup, type SystemBackupResult } from "@/api/systemBackup";
import {
  AgentKey,
  createAgentKey,
  createUser,
  deleteUser,
  fetchAgentKeys,
  fetchCurrentUser,
  fetchUsers,
  revokeAgentKey,
  updateUser
} from "@/api/users";
import { useI18n } from "@/i18n";
import { resolveApiErrorMessage } from "@/lib/backend-messages";
import { formatDateTime } from "@/utils/format";

type UserEditorState = {
  open: boolean;
  userId: string | null;
  username: string;
  displayName: string;
  password: string;
  isAdmin: boolean;
};

const EMPTY_EDITOR: UserEditorState = {
  open: false,
  userId: null,
  username: "",
  displayName: "",
  password: "",
  isAdmin: false
};

type DesktopImportResult = {
  ok: boolean;
  command: string;
  args: string[];
  exitCode: number | null;
  stdout: string;
  stderr: string;
};

type DesktopApiBridge = {
  runImport: (payload: {
    backupDir: string;
    includeDocuments?: boolean;
    includeToken?: boolean;
    includeCredentialKey?: boolean;
    restartBackend?: boolean;
  }) => Promise<DesktopImportResult>;
} | null;

function getDesktopApiBridge(): DesktopApiBridge {
  const desktopApi = (window as unknown as { desktopApi?: DesktopApiBridge }).desktopApi;
  if (!desktopApi || typeof desktopApi.runImport !== "function") {
    return null;
  }
  return desktopApi;
}

function toIsoOrUndefined(raw: string): string | undefined {
  const trimmed = raw.trim();
  if (!trimmed) {
    return undefined;
  }
  const parsed = new Date(trimmed);
  if (Number.isNaN(parsed.valueOf())) {
    return undefined;
  }
  return parsed.toISOString();
}

export function UsersSettingsPage() {
  const queryClient = useQueryClient();
  const { t } = useI18n();
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [editor, setEditor] = useState<UserEditorState>(EMPTY_EDITOR);
  const [newKeyLabel, setNewKeyLabel] = useState<string>(() => t("pages.usersSettings.placeholder.keyLabel"));
  const [newKeyExpiresAt, setNewKeyExpiresAt] = useState<string>("");
  const [revealedKey, setRevealedKey] = useState<string | null>(null);
  const [backupOutputDir, setBackupOutputDir] = useState<string>("");
  const [backupIncludeDocuments, setBackupIncludeDocuments] = useState<boolean>(true);
  const [backupIncludeExport, setBackupIncludeExport] = useState<boolean>(true);
  const [backupResult, setBackupResult] = useState<SystemBackupResult | null>(null);
  const desktopApi = useMemo(() => getDesktopApiBridge(), []);
  const [restoreBackupDir, setRestoreBackupDir] = useState<string>("");
  const [restoreIncludeDocuments, setRestoreIncludeDocuments] = useState<boolean>(true);
  const [restoreIncludeToken, setRestoreIncludeToken] = useState<boolean>(true);
  const [restoreIncludeCredentialKey, setRestoreIncludeCredentialKey] = useState<boolean>(true);
  const [restoreRestartBackend, setRestoreRestartBackend] = useState<boolean>(true);
  const [restoreResult, setRestoreResult] = useState<DesktopImportResult | null>(null);

  const meQuery = useQuery({
    queryKey: ["auth-me"],
    queryFn: fetchCurrentUser
  });
  const usersQuery = useQuery({
    queryKey: ["users"],
    queryFn: fetchUsers,
    enabled: meQuery.data?.is_admin === true
  });
  const keysQuery = useQuery({
    queryKey: ["agent-keys"],
    queryFn: fetchAgentKeys,
    enabled: Boolean(meQuery.data)
  });

  const usersMutation = useMutation({
    mutationFn: async () => {
      if (editor.userId) {
        const payload: { display_name?: string | null; password?: string; is_admin?: boolean } = {};
        payload.display_name = editor.displayName.trim() || null;
        payload.is_admin = editor.isAdmin;
        if (editor.password.trim()) {
          payload.password = editor.password.trim();
        }
        return updateUser(editor.userId, payload);
      }
      if (!editor.username.trim() || !editor.password.trim()) {
        throw new Error(t("pages.usersSettings.status.requiresUsernamePassword"));
      }
      return createUser({
        username: editor.username.trim(),
        display_name: editor.displayName.trim() || null,
        password: editor.password.trim(),
        is_admin: editor.isAdmin
      });
    }
  });

  const deleteUserMutation = useMutation({
    mutationFn: (userId: string) => deleteUser(userId)
  });
  const createKeyMutation = useMutation({
    mutationFn: (payload: { label: string; expires_at?: string }) => createAgentKey(payload)
  });
  const revokeKeyMutation = useMutation({
    mutationFn: (keyId: string) => revokeAgentKey(keyId)
  });
  const backupMutation = useMutation({
    mutationFn: async () =>
      runSystemBackup({
        output_dir: backupOutputDir.trim() || undefined,
        include_documents: backupIncludeDocuments,
        include_export_json: backupIncludeExport
      })
  });
  const restoreMutation = useMutation({
    mutationFn: async () => {
      if (!desktopApi) {
        throw new Error(t("pages.usersSettings.restoreRuntimeOnly"));
      }
      return await desktopApi.runImport({
        backupDir: restoreBackupDir.trim(),
        includeDocuments: restoreIncludeDocuments,
        includeToken: restoreIncludeToken,
        includeCredentialKey: restoreIncludeCredentialKey,
        restartBackend: restoreRestartBackend
      });
    }
  });

  const me = meQuery.data ?? null;
  const users = usersQuery.data?.users ?? [];
  const keys = keysQuery.data?.keys ?? [];
  const loading = meQuery.isPending || usersQuery.isPending || keysQuery.isPending;
  const isAdmin = me?.is_admin === true;
  const firstError =
    (meQuery.error && resolveApiErrorMessage(meQuery.error, t, t("pages.usersSettings.loadErrorTitle"))) ||
    (usersQuery.error && resolveApiErrorMessage(usersQuery.error, t, t("pages.usersSettings.loadErrorTitle"))) ||
    (keysQuery.error && resolveApiErrorMessage(keysQuery.error, t, t("pages.usersSettings.loadErrorTitle"))) ||
    null;

  const sortedKeys = useMemo(
    () =>
      [...keys].sort((a, b) => {
        const aTime = Date.parse(a.created_at);
        const bTime = Date.parse(b.created_at);
        return bTime - aTime;
      }),
    [keys]
  );

  function openCreateUser(): void {
    setEditor({
      open: true,
      userId: null,
      username: "",
      displayName: "",
      password: "",
      isAdmin: false
    });
  }

  function openEditUser(user: {
    user_id: string;
    username: string;
    display_name: string | null;
    is_admin: boolean;
  }): void {
    setEditor({
      open: true,
      userId: user.user_id,
      username: user.username,
      displayName: user.display_name || "",
      password: "",
      isAdmin: user.is_admin
    });
  }

  async function submitUserEditor(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    setStatusMessage(null);
    try {
      await usersMutation.mutateAsync();
      setEditor(EMPTY_EDITOR);
      await queryClient.invalidateQueries({ queryKey: ["users"] });
      setStatusMessage(
        editor.userId ? t("pages.usersSettings.status.userUpdated") : t("pages.usersSettings.status.userCreated")
      );
    } catch (error) {
      setStatusMessage(resolveApiErrorMessage(error, t, t("pages.usersSettings.status.saveFailed")));
    }
  }

  async function removeUser(userId: string): Promise<void> {
    if (!window.confirm(t("pages.usersSettings.confirm.deleteUser"))) {
      return;
    }
    setStatusMessage(null);
    try {
      await deleteUserMutation.mutateAsync(userId);
      await queryClient.invalidateQueries({ queryKey: ["users"] });
      setStatusMessage(t("pages.usersSettings.status.userDeleted"));
    } catch (error) {
      setStatusMessage(resolveApiErrorMessage(error, t, t("pages.usersSettings.status.deleteFailed")));
    }
  }

  async function submitCreateKey(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    setStatusMessage(null);
    setRevealedKey(null);
    try {
      const created = await createKeyMutation.mutateAsync({
        label: newKeyLabel.trim(),
        expires_at: toIsoOrUndefined(newKeyExpiresAt)
      });
      setRevealedKey(created.api_key);
      setNewKeyExpiresAt("");
      await queryClient.invalidateQueries({ queryKey: ["agent-keys"] });
      setStatusMessage(t("pages.usersSettings.status.keyCreated"));
    } catch (error) {
      setStatusMessage(resolveApiErrorMessage(error, t, t("pages.usersSettings.status.keyCreateFailed")));
    }
  }

  async function revokeKey(key: AgentKey): Promise<void> {
    if (!window.confirm(t("pages.usersSettings.confirm.revokeKey", { label: key.label }))) {
      return;
    }
    setStatusMessage(null);
    try {
      await revokeKeyMutation.mutateAsync(key.key_id);
      await queryClient.invalidateQueries({ queryKey: ["agent-keys"] });
      setStatusMessage(t("pages.usersSettings.status.keyRevoked"));
    } catch (error) {
      setStatusMessage(resolveApiErrorMessage(error, t, t("pages.usersSettings.status.keyRevokeFailed")));
    }
  }

  async function submitBackup(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    if (!isAdmin) {
      setStatusMessage(t("pages.usersSettings.backupAdminOnly"));
      return;
    }
    setStatusMessage(null);
    setBackupResult(null);
    try {
      const result = await backupMutation.mutateAsync();
      setBackupResult(result);
      setStatusMessage(t("pages.usersSettings.backupSuccess", { path: result.output_dir }));
    } catch (error) {
      setStatusMessage(resolveApiErrorMessage(error, t, t("pages.usersSettings.backupFailed")));
    }
  }

  async function submitRestore(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    if (!isAdmin) {
      setStatusMessage(t("pages.usersSettings.restoreAdminOnly"));
      return;
    }
    if (!desktopApi) {
      setStatusMessage(t("pages.usersSettings.restoreRuntimeOnly"));
      return;
    }
    if (!restoreBackupDir.trim()) {
      setStatusMessage(t("pages.usersSettings.restoreDirectoryRequired"));
      return;
    }

    setStatusMessage(null);
    setRestoreResult(null);
    try {
      const result = await restoreMutation.mutateAsync();
      setRestoreResult(result);
      setStatusMessage(t("pages.usersSettings.restoreSuccess"));
      await queryClient.invalidateQueries();
    } catch (error) {
      setStatusMessage(resolveApiErrorMessage(error, t, t("pages.usersSettings.restoreFailed")));
    }
  }

  return (
    <section className="space-y-4">
      <PageHeader title={t("pages.usersSettings.title")} />
      <Card>
        <CardContent className="space-y-0 pt-6">
          <div className="space-y-4">
            {loading ? <p className="text-sm text-muted-foreground">{t("common.loadingSettings")}</p> : null}
            {firstError ? (
              <Alert variant="destructive">
                <AlertTitle>{t("pages.usersSettings.loadErrorTitle")}</AlertTitle>
                <AlertDescription>{firstError}</AlertDescription>
              </Alert>
            ) : null}
            {statusMessage ? <p className="text-sm text-muted-foreground">{statusMessage}</p> : null}
            {revealedKey ? (
              <Alert>
                <AlertTitle>{t("pages.usersSettings.newApiKeyTitle")}</AlertTitle>
                <AlertDescription>
                  <code className="font-mono text-xs">{revealedKey}</code>
                </AlertDescription>
              </Alert>
            ) : null}
          </div>

          <div className="app-section-divider">
            {isAdmin ? (
              <>
                <div className="mb-4 flex flex-row flex-wrap items-center justify-between gap-3">
                  <h2 className="font-semibold leading-none tracking-tight">{t("pages.usersSettings.usersTitle")}</h2>
                  <Button type="button" onClick={openCreateUser}>
                    {t("pages.usersSettings.addUser")}
                  </Button>
                </div>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>{t("common.username")}</TableHead>
                      <TableHead>{t("common.displayName")}</TableHead>
                      <TableHead>{t("pages.usersSettings.table.admin")}</TableHead>
                      <TableHead>{t("common.created")}</TableHead>
                      <TableHead>{t("common.actions")}</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {users.map((user) => (
                      <TableRow key={user.user_id}>
                        <TableCell>{user.username}</TableCell>
                        <TableCell>{user.display_name || t("pages.usersSettings.noDisplayName")}</TableCell>
                        <TableCell>{user.is_admin ? t("common.yes") : t("common.no")}</TableCell>
                        <TableCell>{formatDateTime(user.created_at)}</TableCell>
                        <TableCell className="space-x-2">
                          <Button type="button" size="sm" variant="outline" onClick={() => openEditUser(user)}>
                            {t("common.edit")}
                          </Button>
                          <Button type="button" size="sm" variant="destructive" onClick={() => void removeUser(user.user_id)}>
                            {t("common.delete")}
                          </Button>
                        </TableCell>
                      </TableRow>
                    ))}
                    {users.length === 0 ? (
                      <TableRow>
                        <TableCell colSpan={5}>{t("pages.usersSettings.noUsers")}</TableCell>
                      </TableRow>
                    ) : null}
                  </TableBody>
                </Table>
              </>
            ) : (
              <>
                <h2 className="font-semibold leading-none tracking-tight">{t("pages.usersSettings.usersTitle")}</h2>
                <p className="mt-2 text-sm text-muted-foreground">{t("pages.usersSettings.adminOnly")}</p>
              </>
            )}
          </div>

          <div className="app-section-divider space-y-4">
            <h2 className="font-semibold leading-none tracking-tight">{t("pages.usersSettings.keysTitle")}</h2>
            <form className="grid gap-3 md:grid-cols-3" onSubmit={(event) => void submitCreateKey(event)}>
              <div className="space-y-2">
                <Label htmlFor="key-label">{t("common.label")}</Label>
                <Input
                  id="key-label"
                  value={newKeyLabel}
                  onChange={(event) => setNewKeyLabel(event.target.value)}
                  placeholder={t("pages.usersSettings.placeholder.keyLabel")}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="key-expiry">{t("pages.usersSettings.field.expiresAtOptional")}</Label>
                <Input
                  id="key-expiry"
                  type="datetime-local"
                  value={newKeyExpiresAt}
                  onChange={(event) => setNewKeyExpiresAt(event.target.value)}
                />
              </div>
              <Button type="submit" className="self-end" disabled={createKeyMutation.isPending}>
                {createKeyMutation.isPending ? t("pages.usersSettings.creatingKey") : t("pages.usersSettings.createKey")}
              </Button>
            </form>

            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{t("common.label")}</TableHead>
                  <TableHead>{t("common.prefix")}</TableHead>
                  <TableHead>{t("pages.usersSettings.table.status")}</TableHead>
                  <TableHead>{t("pages.usersSettings.table.lastUsed")}</TableHead>
                  <TableHead>{t("pages.usersSettings.table.expires")}</TableHead>
                  <TableHead>{t("common.actions")}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {sortedKeys.map((key) => (
                  <TableRow key={key.key_id}>
                    <TableCell>{key.label}</TableCell>
                    <TableCell>
                      <code className="font-mono text-xs">{key.key_prefix}</code>
                    </TableCell>
                    <TableCell>
                      <Badge variant={key.is_active ? "default" : "secondary"}>
                        {key.is_active ? t("pages.usersSettings.keyStatus.active") : t("pages.usersSettings.keyStatus.revoked")}
                      </Badge>
                    </TableCell>
                    <TableCell>{key.last_used_at ? formatDateTime(key.last_used_at) : t("common.never")}</TableCell>
                    <TableCell>{key.expires_at ? formatDateTime(key.expires_at) : t("common.never")}</TableCell>
                    <TableCell>
                      <Button
                        type="button"
                        size="sm"
                        variant="destructive"
                        disabled={!key.is_active || revokeKeyMutation.isPending}
                        onClick={() => void revokeKey(key)}
                      >
                        {t("pages.usersSettings.revoke")}
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
                {sortedKeys.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={6}>{t("pages.usersSettings.noKeys")}</TableCell>
                  </TableRow>
                ) : null}
              </TableBody>
            </Table>
          </div>

          <div className="app-section-divider space-y-4">
            <h2 className="font-semibold leading-none tracking-tight">{t("pages.usersSettings.backupTitle")}</h2>
            <p className="text-sm text-muted-foreground">{t("pages.usersSettings.backupDescription")}</p>
            <form className="space-y-3" onSubmit={(event) => void submitBackup(event)}>
              <div className="space-y-2">
                <Label htmlFor="backup-output-dir">{t("pages.usersSettings.backupOutputDir")}</Label>
                <Input
                  id="backup-output-dir"
                  value={backupOutputDir}
                  onChange={(event) => setBackupOutputDir(event.target.value)}
                  placeholder={t("pages.usersSettings.backupOutputPlaceholder")}
                />
              </div>
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={backupIncludeDocuments}
                  onChange={(event) => setBackupIncludeDocuments(event.target.checked)}
                />
                {t("pages.usersSettings.backupIncludeDocuments")}
              </label>
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={backupIncludeExport}
                  onChange={(event) => setBackupIncludeExport(event.target.checked)}
                />
                {t("pages.usersSettings.backupIncludeExport")}
              </label>
              <Button type="submit" disabled={backupMutation.isPending}>
                {backupMutation.isPending ? t("pages.usersSettings.backupSubmitting") : t("pages.usersSettings.backupSubmit")}
              </Button>
            </form>
            {backupResult ? (
              <pre className="overflow-x-auto rounded-md bg-muted p-3 text-xs">{JSON.stringify(backupResult, null, 2)}</pre>
            ) : null}
          </div>

          <div className="app-section-divider space-y-4">
            <h2 className="font-semibold leading-none tracking-tight">{t("pages.usersSettings.restoreTitle")}</h2>
            <p className="text-sm text-muted-foreground">{t("pages.usersSettings.restoreDescription")}</p>
            <form className="space-y-3" onSubmit={(event) => void submitRestore(event)}>
              <div className="space-y-2">
                <Label htmlFor="restore-backup-dir">{t("pages.usersSettings.restoreDirectory")}</Label>
                <Input
                  id="restore-backup-dir"
                  value={restoreBackupDir}
                  onChange={(event) => setRestoreBackupDir(event.target.value)}
                  disabled={!desktopApi}
                />
              </div>
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={restoreIncludeDocuments}
                  onChange={(event) => setRestoreIncludeDocuments(event.target.checked)}
                  disabled={!desktopApi}
                />
                {t("pages.usersSettings.restoreIncludeDocuments")}
              </label>
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={restoreIncludeToken}
                  onChange={(event) => setRestoreIncludeToken(event.target.checked)}
                  disabled={!desktopApi}
                />
                {t("pages.usersSettings.restoreIncludeToken")}
              </label>
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={restoreIncludeCredentialKey}
                  onChange={(event) => setRestoreIncludeCredentialKey(event.target.checked)}
                  disabled={!desktopApi}
                />
                {t("pages.usersSettings.restoreIncludeCredentialKey")}
              </label>
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={restoreRestartBackend}
                  onChange={(event) => setRestoreRestartBackend(event.target.checked)}
                  disabled={!desktopApi}
                />
                {t("pages.usersSettings.restoreRestartBackend")}
              </label>
              <Button type="submit" disabled={restoreMutation.isPending || !desktopApi}>
                {restoreMutation.isPending
                  ? t("pages.usersSettings.restoreSubmitting")
                  : t("pages.usersSettings.restoreSubmit")}
              </Button>
            </form>
            {!desktopApi ? (
              <p className="text-sm text-muted-foreground">{t("pages.usersSettings.restoreRuntimeOnly")}</p>
            ) : null}
            {restoreResult ? (
              <pre className="overflow-x-auto rounded-md bg-muted p-3 text-xs">{JSON.stringify(restoreResult, null, 2)}</pre>
            ) : null}
          </div>
        </CardContent>
      </Card>

      <Dialog open={editor.open} onOpenChange={(open) => setEditor((previous) => ({ ...previous, open }))}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {editor.userId ? t("pages.usersSettings.dialog.editTitle") : t("pages.usersSettings.dialog.createTitle")}
            </DialogTitle>
            <DialogDescription>
              {editor.userId
                ? t("pages.usersSettings.dialog.editDescription")
                : t("pages.usersSettings.dialog.createDescription")}
            </DialogDescription>
          </DialogHeader>

          <form className="space-y-3" onSubmit={(event) => void submitUserEditor(event)}>
            <div className="space-y-2">
              <Label htmlFor="editor-username">{t("common.username")}</Label>
              <Input
                id="editor-username"
                value={editor.username}
                onChange={(event) => setEditor((previous) => ({ ...previous, username: event.target.value }))}
                disabled={Boolean(editor.userId)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="editor-display-name">{t("common.displayName")}</Label>
              <Input
                id="editor-display-name"
                value={editor.displayName}
                onChange={(event) => setEditor((previous) => ({ ...previous, displayName: event.target.value }))}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="editor-password">
                {editor.userId ? t("pages.usersSettings.field.newPasswordOptional") : t("common.password")}
              </Label>
              <Input
                id="editor-password"
                type="password"
                value={editor.password}
                onChange={(event) => setEditor((previous) => ({ ...previous, password: event.target.value }))}
              />
            </div>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={editor.isAdmin}
                onChange={(event) => setEditor((previous) => ({ ...previous, isAdmin: event.target.checked }))}
              />
              {t("pages.usersSettings.adminUser")}
            </label>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setEditor(EMPTY_EDITOR)}>
                {t("common.cancel")}
              </Button>
              <Button type="submit" disabled={usersMutation.isPending}>
                {usersMutation.isPending ? t("pages.usersSettings.saving") : t("common.save")}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </section>
  );
}
