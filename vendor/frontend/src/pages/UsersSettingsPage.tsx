import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FormEvent, useMemo, useState } from "react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
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

export function UsersSettingsPage(): JSX.Element {
  const queryClient = useQueryClient();
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [editor, setEditor] = useState<UserEditorState>(EMPTY_EDITOR);
  const [newKeyLabel, setNewKeyLabel] = useState<string>("OpenClaw Agent");
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
        throw new Error("Username and password are required for new users.");
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
        throw new Error("Desktop restore is only available inside the desktop app runtime.");
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
    (meQuery.error instanceof Error && meQuery.error.message) ||
    (usersQuery.error instanceof Error && usersQuery.error.message) ||
    (keysQuery.error instanceof Error && keysQuery.error.message) ||
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
      setStatusMessage(editor.userId ? "User updated." : "User created.");
    } catch (error) {
      setStatusMessage(error instanceof Error ? error.message : "Failed to save user.");
    }
  }

  async function removeUser(userId: string): Promise<void> {
    if (!window.confirm("Delete this user?")) {
      return;
    }
    setStatusMessage(null);
    try {
      await deleteUserMutation.mutateAsync(userId);
      await queryClient.invalidateQueries({ queryKey: ["users"] });
      setStatusMessage("User deleted.");
    } catch (error) {
      setStatusMessage(error instanceof Error ? error.message : "Failed to delete user.");
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
      setStatusMessage("Agent key created. Copy it now; it is shown only once.");
    } catch (error) {
      setStatusMessage(error instanceof Error ? error.message : "Failed to create key.");
    }
  }

  async function revokeKey(key: AgentKey): Promise<void> {
    if (!window.confirm(`Revoke API key '${key.label}'?`)) {
      return;
    }
    setStatusMessage(null);
    try {
      await revokeKeyMutation.mutateAsync(key.key_id);
      await queryClient.invalidateQueries({ queryKey: ["agent-keys"] });
      setStatusMessage("Agent key revoked.");
    } catch (error) {
      setStatusMessage(error instanceof Error ? error.message : "Failed to revoke key.");
    }
  }

  async function submitBackup(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    if (!isAdmin) {
      setStatusMessage("Only admins can create system backups.");
      return;
    }
    setStatusMessage(null);
    setBackupResult(null);
    try {
      const result = await backupMutation.mutateAsync();
      setBackupResult(result);
      setStatusMessage(`Backup created at ${result.output_dir}`);
    } catch (error) {
      setStatusMessage(error instanceof Error ? error.message : "Failed to create backup.");
    }
  }

  async function submitRestore(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    if (!isAdmin) {
      setStatusMessage("Only admins can restore desktop backups.");
      return;
    }
    if (!desktopApi) {
      setStatusMessage("Desktop restore is only available inside the desktop app runtime.");
      return;
    }
    if (!restoreBackupDir.trim()) {
      setStatusMessage("Backup directory is required for restore.");
      return;
    }

    setStatusMessage(null);
    setRestoreResult(null);
    try {
      const result = await restoreMutation.mutateAsync();
      setRestoreResult(result);
      setStatusMessage("Backup restored. Refresh the app if data does not update immediately.");
      await queryClient.invalidateQueries();
    } catch (error) {
      setStatusMessage(error instanceof Error ? error.message : "Failed to restore backup.");
    }
  }

  return (
    <section className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>Users & Agent Keys</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          {loading ? <p className="text-sm text-muted-foreground">Loading settings...</p> : null}
          {firstError ? (
            <Alert variant="destructive">
              <AlertTitle>Failed to load settings</AlertTitle>
              <AlertDescription>{firstError}</AlertDescription>
            </Alert>
          ) : null}
          {statusMessage ? <p className="text-sm text-muted-foreground">{statusMessage}</p> : null}
          {revealedKey ? (
            <Alert>
              <AlertTitle>New API key</AlertTitle>
              <AlertDescription>
                <code className="font-mono text-xs">{revealedKey}</code>
              </AlertDescription>
            </Alert>
          ) : null}
        </CardContent>
      </Card>

      {isAdmin ? (
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <CardTitle>Users</CardTitle>
            <Button type="button" onClick={openCreateUser}>
              Add user
            </Button>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Username</TableHead>
                  <TableHead>Display Name</TableHead>
                  <TableHead>Admin</TableHead>
                  <TableHead>Created</TableHead>
                  <TableHead>Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {users.map((user) => (
                  <TableRow key={user.user_id}>
                    <TableCell>{user.username}</TableCell>
                    <TableCell>{user.display_name || "—"}</TableCell>
                    <TableCell>{user.is_admin ? "Yes" : "No"}</TableCell>
                    <TableCell>{formatDateTime(user.created_at)}</TableCell>
                    <TableCell className="space-x-2">
                      <Button type="button" size="sm" variant="outline" onClick={() => openEditUser(user)}>
                        Edit
                      </Button>
                      <Button type="button" size="sm" variant="destructive" onClick={() => void removeUser(user.user_id)}>
                        Delete
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
                {users.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={5}>No users found.</TableCell>
                  </TableRow>
                ) : null}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardHeader>
            <CardTitle>Users</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">Only admins can manage users.</p>
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Agent API Keys</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <form className="grid gap-3 md:grid-cols-3" onSubmit={(event) => void submitCreateKey(event)}>
            <div className="space-y-2">
              <Label htmlFor="key-label">Label</Label>
              <Input
                id="key-label"
                value={newKeyLabel}
                onChange={(event) => setNewKeyLabel(event.target.value)}
                placeholder="OpenClaw Agent"
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="key-expiry">Expires at (optional)</Label>
              <Input
                id="key-expiry"
                type="datetime-local"
                value={newKeyExpiresAt}
                onChange={(event) => setNewKeyExpiresAt(event.target.value)}
              />
            </div>
            <Button type="submit" className="self-end" disabled={createKeyMutation.isPending}>
              {createKeyMutation.isPending ? "Creating..." : "Create key"}
            </Button>
          </form>

          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Label</TableHead>
                <TableHead>Prefix</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Last used</TableHead>
                <TableHead>Expires</TableHead>
                <TableHead>Actions</TableHead>
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
                      {key.is_active ? "Active" : "Revoked"}
                    </Badge>
                  </TableCell>
                  <TableCell>{key.last_used_at ? formatDateTime(key.last_used_at) : "Never"}</TableCell>
                  <TableCell>{key.expires_at ? formatDateTime(key.expires_at) : "Never"}</TableCell>
                  <TableCell>
                    <Button
                      type="button"
                      size="sm"
                      variant="destructive"
                      disabled={!key.is_active || revokeKeyMutation.isPending}
                      onClick={() => void revokeKey(key)}
                    >
                      Revoke
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
              {sortedKeys.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={6}>No agent keys yet.</TableCell>
                </TableRow>
              ) : null}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Desktop Backup</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <form className="space-y-3" onSubmit={(event) => void submitBackup(event)}>
            <div className="space-y-2">
              <Label htmlFor="backup-output-dir">Output directory (optional)</Label>
              <Input
                id="backup-output-dir"
                value={backupOutputDir}
                onChange={(event) => setBackupOutputDir(event.target.value)}
                placeholder="Defaults to ~/.config/lidltool/desktop-backups/backup-<timestamp>"
              />
              <p className="text-xs text-muted-foreground">
                Uses an auto-generated backup folder if left empty.
              </p>
            </div>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={backupIncludeDocuments}
                onChange={(event) => setBackupIncludeDocuments(event.target.checked)}
              />
              Include document storage
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={backupIncludeExport}
                onChange={(event) => setBackupIncludeExport(event.target.checked)}
              />
              Include receipts JSON export
            </label>
            <Button type="submit" disabled={backupMutation.isPending || !isAdmin}>
              {backupMutation.isPending ? "Creating backup..." : "Create backup bundle"}
            </Button>
          </form>

          {!isAdmin ? (
            <p className="text-sm text-muted-foreground">Only admins can create system backups.</p>
          ) : null}

          {backupResult ? (
            <pre className="overflow-x-auto rounded border bg-muted/30 p-3 text-xs">
              {JSON.stringify(backupResult, null, 2)}
            </pre>
          ) : null}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Desktop Restore</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <form className="space-y-3" onSubmit={(event) => void submitRestore(event)}>
            <div className="space-y-2">
              <Label htmlFor="restore-backup-dir">Backup directory</Label>
              <Input
                id="restore-backup-dir"
                value={restoreBackupDir}
                onChange={(event) => setRestoreBackupDir(event.target.value)}
                placeholder="/path/to/backup-folder"
              />
            </div>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={restoreIncludeCredentialKey}
                onChange={(event) => setRestoreIncludeCredentialKey(event.target.checked)}
              />
              Restore credential key
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={restoreIncludeToken}
                onChange={(event) => setRestoreIncludeToken(event.target.checked)}
              />
              Restore token file
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={restoreIncludeDocuments}
                onChange={(event) => setRestoreIncludeDocuments(event.target.checked)}
              />
              Restore document storage
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={restoreRestartBackend}
                onChange={(event) => setRestoreRestartBackend(event.target.checked)}
              />
              Restart backend after restore
            </label>
            <Button type="submit" disabled={restoreMutation.isPending || !isAdmin || !desktopApi}>
              {restoreMutation.isPending ? "Restoring..." : "Restore backup bundle"}
            </Button>
          </form>

          {!desktopApi ? (
            <p className="text-sm text-muted-foreground">
              Restore actions are available only in the packaged desktop app.
            </p>
          ) : null}

          {!isAdmin ? (
            <p className="text-sm text-muted-foreground">Only admins can restore desktop backups.</p>
          ) : null}

          {restoreResult ? (
            <pre className="overflow-x-auto rounded border bg-muted/30 p-3 text-xs">
              {JSON.stringify(restoreResult, null, 2)}
            </pre>
          ) : null}
        </CardContent>
      </Card>

      <Dialog open={editor.open} onOpenChange={(open) => setEditor((previous) => ({ ...previous, open }))}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{editor.userId ? "Edit user" : "Add user"}</DialogTitle>
            <DialogDescription>
              {editor.userId
                ? "Update user profile, password, and admin role."
                : "Create a new user account."}
            </DialogDescription>
          </DialogHeader>

          <form className="space-y-3" onSubmit={(event) => void submitUserEditor(event)}>
            <div className="space-y-2">
              <Label htmlFor="editor-username">Username</Label>
              <Input
                id="editor-username"
                value={editor.username}
                onChange={(event) => setEditor((previous) => ({ ...previous, username: event.target.value }))}
                disabled={Boolean(editor.userId)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="editor-display-name">Display name</Label>
              <Input
                id="editor-display-name"
                value={editor.displayName}
                onChange={(event) => setEditor((previous) => ({ ...previous, displayName: event.target.value }))}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="editor-password">
                {editor.userId ? "New password (optional)" : "Password"}
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
              Admin user
            </label>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setEditor(EMPTY_EDITOR)}>
                Cancel
              </Button>
              <Button type="submit" disabled={usersMutation.isPending}>
                {usersMutation.isPending ? "Saving..." : "Save"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </section>
  );
}
