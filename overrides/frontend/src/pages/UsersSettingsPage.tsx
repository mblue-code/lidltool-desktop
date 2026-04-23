import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FormEvent, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";

import { logout } from "@/api/auth";
import {
  addSharedGroupMember,
  createSharedGroup,
  fetchSharedGroups,
  fetchSharedGroupUserDirectory,
  removeSharedGroupMember,
  updateSharedGroup,
  updateSharedGroupMember,
  type SharedGroup
} from "@/api/shared-groups";
import { runSystemBackup, type SystemBackupResult } from "@/api/systemBackup";
import {
  type AgentKey,
  createAgentKey,
  createUser,
  deleteUser,
  fetchAgentKeys,
  fetchAuthSessions,
  fetchCurrentUser,
  fetchUsers,
  revokeAgentKey,
  revokeAuthSession,
  updateUser
} from "@/api/users";
import { PageHeader } from "@/components/shared/PageHeader";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
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
import { useI18n } from "@/i18n";
import { resolveApiErrorMessage } from "@/lib/backend-messages";
import { formatDateTime } from "@/utils/format";

type UserEditorState = {
  open: boolean;
  userId: string | null;
  username: string;
  displayName: string;
  password: string;
};

type SharedGroupEditorState = {
  open: boolean;
  groupId: string | null;
  name: string;
  groupType: "household" | "community";
  status: "active" | "archived";
};

type PendingMemberState = {
  userId: string;
  role: "owner" | "manager" | "member";
};

const EMPTY_EDITOR: UserEditorState = {
  open: false,
  userId: null,
  username: "",
  displayName: "",
  password: ""
};

const EMPTY_GROUP_EDITOR: SharedGroupEditorState = {
  open: false,
  groupId: null,
  name: "",
  groupType: "household",
  status: "active"
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

function labelForRole(locale: "en" | "de", role: "owner" | "manager" | "member"): string {
  if (role === "owner") {
    return locale === "de" ? "Besitzer" : "Owner";
  }
  if (role === "manager") {
    return locale === "de" ? "Manager" : "Manager";
  }
  return locale === "de" ? "Mitglied" : "Member";
}

function labelForGroupType(locale: "en" | "de", groupType: "household" | "community"): string {
  return groupType === "household"
    ? locale === "de"
      ? "Haushalt"
      : "Household"
    : locale === "de"
      ? "Community"
      : "Community";
}

function labelForMembershipStatus(locale: "en" | "de", status: "active" | "removed"): string {
  return status === "active" ? (locale === "de" ? "Aktiv" : "Active") : locale === "de" ? "Entfernt" : "Removed";
}

function labelForSessionTransport(locale: "en" | "de", transport: string): string {
  if (transport === "cookie_session") {
    return locale === "de" ? "Desktop-Sitzung" : "Desktop session";
  }
  if (transport === "bearer_session") {
    return locale === "de" ? "Bearer-Sitzung" : "Bearer session";
  }
  if (transport === "api_key") {
    return locale === "de" ? "API-Schlüssel" : "API key";
  }
  return transport;
}

export function UsersSettingsPage() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const { locale, t } = useI18n();
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [editor, setEditor] = useState<UserEditorState>(EMPTY_EDITOR);
  const [groupEditor, setGroupEditor] = useState<SharedGroupEditorState>(EMPTY_GROUP_EDITOR);
  const [pendingMembers, setPendingMembers] = useState<Record<string, PendingMemberState>>({});
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
  const sessionsQuery = useQuery({
    queryKey: ["auth-sessions"],
    queryFn: fetchAuthSessions,
    enabled: Boolean(meQuery.data)
  });
  const groupsQuery = useQuery({
    queryKey: ["shared-groups"],
    queryFn: fetchSharedGroups,
    enabled: Boolean(meQuery.data)
  });
  const groupUserDirectoryQuery = useQuery({
    queryKey: ["shared-group-user-directory"],
    queryFn: fetchSharedGroupUserDirectory,
    enabled: Boolean(meQuery.data)
  });
  const keysQuery = useQuery({
    queryKey: ["agent-keys"],
    queryFn: fetchAgentKeys,
    enabled: Boolean(meQuery.data)
  });

  const usersMutation = useMutation({
    mutationFn: async () => {
      if (editor.userId) {
        const payload: { display_name?: string | null; password?: string } = {};
        payload.display_name = editor.displayName.trim() || null;
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
        is_admin: false
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
  const revokeSessionMutation = useMutation({
    mutationFn: (sessionId: string) => revokeAuthSession(sessionId)
  });
  const createGroupMutation = useMutation({
    mutationFn: (payload: { name: string; group_type: "household" | "community" }) =>
      createSharedGroup(payload)
  });
  const updateGroupMutation = useMutation({
    mutationFn: (payload: {
      groupId: string;
      name?: string;
      group_type?: "household" | "community";
      status?: "active" | "archived";
    }) => updateSharedGroup(payload.groupId, payload)
  });
  const addGroupMemberMutation = useMutation({
    mutationFn: (payload: { groupId: string; userId: string; role: "owner" | "manager" | "member" }) =>
      addSharedGroupMember(payload.groupId, { user_id: payload.userId, role: payload.role })
  });
  const updateGroupMemberMutation = useMutation({
    mutationFn: (payload: {
      groupId: string;
      userId: string;
      role?: "owner" | "manager" | "member";
      membership_status?: "active" | "removed";
    }) => updateSharedGroupMember(payload.groupId, payload.userId, payload)
  });
  const removeGroupMemberMutation = useMutation({
    mutationFn: (payload: { groupId: string; userId: string }) =>
      removeSharedGroupMember(payload.groupId, payload.userId)
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
  const sessions = sessionsQuery.data?.sessions ?? [];
  const groups = groupsQuery.data?.groups ?? [];
  const groupDirectory = groupUserDirectoryQuery.data?.users ?? [];
  const keys = keysQuery.data?.keys ?? [];
  const loading =
    meQuery.isPending ||
    usersQuery.isPending ||
    sessionsQuery.isPending ||
    groupsQuery.isPending ||
    groupUserDirectoryQuery.isPending ||
    keysQuery.isPending;
  const isAdmin = me?.is_admin === true;
  const firstError =
    (meQuery.error && resolveApiErrorMessage(meQuery.error, t, t("pages.usersSettings.loadErrorTitle"))) ||
    (usersQuery.error && resolveApiErrorMessage(usersQuery.error, t, t("pages.usersSettings.loadErrorTitle"))) ||
    (sessionsQuery.error && resolveApiErrorMessage(sessionsQuery.error, t, t("pages.usersSettings.loadErrorTitle"))) ||
    (groupsQuery.error && resolveApiErrorMessage(groupsQuery.error, t, t("pages.usersSettings.loadErrorTitle"))) ||
    (groupUserDirectoryQuery.error &&
      resolveApiErrorMessage(groupUserDirectoryQuery.error, t, t("pages.usersSettings.loadErrorTitle"))) ||
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
      password: ""
    });
  }

  function openEditUser(user: { user_id: string; username: string; display_name: string | null }): void {
    setEditor({
      open: true,
      userId: user.user_id,
      username: user.username,
      displayName: user.display_name || "",
      password: ""
    });
  }

  function openCreateGroup(): void {
    setGroupEditor(EMPTY_GROUP_EDITOR);
  }

  function openEditGroup(group: SharedGroup): void {
    setGroupEditor({
      open: true,
      groupId: group.group_id,
      name: group.name,
      groupType: group.group_type,
      status: group.status
    });
  }

  async function signOutCurrentAccount(): Promise<void> {
    try {
      await logout();
    } finally {
      navigate("/login", { replace: true });
    }
  }

  async function revokeSession(sessionId: string, current: boolean): Promise<void> {
    const confirmMessage =
      locale === "de"
        ? "Diese Sitzung widerrufen?"
        : "Revoke this session?";
    if (!window.confirm(confirmMessage)) {
      return;
    }
    setStatusMessage(null);
    try {
      await revokeSessionMutation.mutateAsync(sessionId);
      await queryClient.invalidateQueries({ queryKey: ["auth-sessions"] });
      if (current) {
        await signOutCurrentAccount();
        return;
      }
      setStatusMessage(locale === "de" ? "Sitzung widerrufen." : "Session revoked.");
    } catch (error) {
      setStatusMessage(
        resolveApiErrorMessage(error, t, locale === "de" ? "Sitzung konnte nicht widerrufen werden." : "Failed to revoke session.")
      );
    }
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

  async function submitGroupEditor(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    setStatusMessage(null);
    try {
      if (groupEditor.groupId) {
        await updateGroupMutation.mutateAsync({
          groupId: groupEditor.groupId,
          name: groupEditor.name.trim(),
          group_type: groupEditor.groupType,
          status: groupEditor.status
        });
        setStatusMessage(locale === "de" ? "Geteilte Gruppe aktualisiert." : "Shared group updated.");
      } else {
        await createGroupMutation.mutateAsync({
          name: groupEditor.name.trim(),
          group_type: groupEditor.groupType
        });
        setStatusMessage(locale === "de" ? "Geteilte Gruppe erstellt." : "Shared group created.");
      }
      setGroupEditor(EMPTY_GROUP_EDITOR);
      await queryClient.invalidateQueries({ queryKey: ["shared-groups"] });
    } catch (error) {
      setStatusMessage(
        resolveApiErrorMessage(error, t, locale === "de" ? "Geteilte Gruppe konnte nicht gespeichert werden." : "Failed to save shared group.")
      );
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

  async function addMember(group: SharedGroup): Promise<void> {
    const pending = pendingMembers[group.group_id];
    if (!pending?.userId) {
      setStatusMessage(locale === "de" ? "Bitte zuerst einen Benutzer auswählen." : "Select a user first.");
      return;
    }
    setStatusMessage(null);
    try {
      await addGroupMemberMutation.mutateAsync({
        groupId: group.group_id,
        userId: pending.userId,
        role: pending.role
      });
      setPendingMembers((current) => ({ ...current, [group.group_id]: { userId: "", role: "member" } }));
      await queryClient.invalidateQueries({ queryKey: ["shared-groups"] });
      setStatusMessage(locale === "de" ? "Mitglied hinzugefügt." : "Member added.");
    } catch (error) {
      setStatusMessage(
        resolveApiErrorMessage(error, t, locale === "de" ? "Mitglied konnte nicht hinzugefügt werden." : "Failed to add member.")
      );
    }
  }

  async function changeMemberRole(
    groupId: string,
    userId: string,
    role: "owner" | "manager" | "member"
  ): Promise<void> {
    setStatusMessage(null);
    try {
      await updateGroupMemberMutation.mutateAsync({ groupId, userId, role });
      await queryClient.invalidateQueries({ queryKey: ["shared-groups"] });
      setStatusMessage(locale === "de" ? "Mitglied aktualisiert." : "Member updated.");
    } catch (error) {
      setStatusMessage(
        resolveApiErrorMessage(error, t, locale === "de" ? "Mitglied konnte nicht aktualisiert werden." : "Failed to update member.")
      );
    }
  }

  async function removeMember(groupId: string, userId: string): Promise<void> {
    if (!window.confirm(locale === "de" ? "Mitglied aus Gruppe entfernen?" : "Remove member from group?")) {
      return;
    }
    setStatusMessage(null);
    try {
      await removeGroupMemberMutation.mutateAsync({ groupId, userId });
      await queryClient.invalidateQueries({ queryKey: ["shared-groups"] });
      setStatusMessage(locale === "de" ? "Mitglied entfernt." : "Member removed.");
    } catch (error) {
      setStatusMessage(
        resolveApiErrorMessage(error, t, locale === "de" ? "Mitglied konnte nicht entfernt werden." : "Failed to remove member.")
      );
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
      if (!result.ok) {
        throw new Error(result.stderr || result.stdout || t("pages.usersSettings.restoreFailed"));
      }
      setRestoreResult(result);
      setStatusMessage(t("pages.usersSettings.restoreSuccess"));
      queryClient.clear();
      window.location.assign("/login?restored=1");
    } catch (error) {
      setStatusMessage(resolveApiErrorMessage(error, t, t("pages.usersSettings.restoreFailed")));
    }
  }

  return (
    <section className="space-y-4">
      <PageHeader
        title={t("pages.usersSettings.title")}
        description={
          locale === "de"
            ? "Verwalten Sie desktop-lokale Konten, aktive Sitzungen, geteilte Gruppen und Wiederherstellungsfunktionen."
            : "Manage desktop-local accounts, active sessions, shared groups, and restore tooling."
        }
      />

      <Card>
        <CardContent className="space-y-4 pt-6">
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
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <CardTitle>{locale === "de" ? "Konto" : "Account"}</CardTitle>
              <CardDescription>
                {locale === "de"
                  ? "Melden Sie sich klar sichtbar ab, wechseln Sie Konten und prüfen Sie die aktuelle Desktop-Sitzung."
                  : "Sign out explicitly, switch accounts, and inspect the current desktop session."}
              </CardDescription>
            </div>
            <div className="flex gap-2">
              <Button variant="outline" onClick={() => void signOutCurrentAccount()}>
                {locale === "de" ? "Konto wechseln" : "Switch account"}
              </Button>
              <Button onClick={() => void signOutCurrentAccount()}>{t("action.signOut")}</Button>
            </div>
          </div>
        </CardHeader>
        <CardContent className="grid gap-4 md:grid-cols-2">
          <div className="rounded-lg border p-4">
            <p className="text-xs uppercase tracking-wide text-muted-foreground">{locale === "de" ? "Benutzer" : "User"}</p>
            <p className="mt-2 font-medium">{me?.display_name ?? me?.username ?? "—"}</p>
            <p className="text-sm text-muted-foreground">{me?.username ?? "—"}</p>
          </div>
          <div className="rounded-lg border p-4">
            <p className="text-xs uppercase tracking-wide text-muted-foreground">{locale === "de" ? "Aktuelle Sitzung" : "Current session"}</p>
            <p className="mt-2 font-medium">
              {me?.session?.device_label || me?.session?.client_name || (locale === "de" ? "Dieser Desktop" : "This desktop")}
            </p>
            <p className="text-sm text-muted-foreground">
              {me?.session ? labelForSessionTransport(locale, me.session.auth_transport) : "—"}
            </p>
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{locale === "de" ? "Aktive Sitzungen" : "Active sessions"}</CardTitle>
          <CardDescription>
            {locale === "de"
              ? "Widerrufen Sie Geräte- und Browser-Sitzungen direkt aus der Desktop-App."
              : "Revoke browser and device sessions directly from the desktop app."}
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{locale === "de" ? "Gerät" : "Device"}</TableHead>
                <TableHead>{locale === "de" ? "Transport" : "Transport"}</TableHead>
                <TableHead>{locale === "de" ? "Zuletzt gesehen" : "Last seen"}</TableHead>
                <TableHead>{locale === "de" ? "Läuft ab" : "Expires"}</TableHead>
                <TableHead>{t("common.actions")}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {sessions.map((session) => (
                <TableRow key={session.session_id}>
                  <TableCell>
                    <div className="space-y-1">
                      <p>{session.device_label || session.client_name || (locale === "de" ? "Desktop" : "Desktop")}</p>
                      <p className="text-xs text-muted-foreground">
                        {session.current ? (locale === "de" ? "Aktuelle Sitzung" : "Current session") : session.client_platform || "—"}
                      </p>
                    </div>
                  </TableCell>
                  <TableCell>{labelForSessionTransport(locale, session.auth_transport)}</TableCell>
                  <TableCell>{formatDateTime(session.last_seen_at)}</TableCell>
                  <TableCell>{formatDateTime(session.expires_at)}</TableCell>
                  <TableCell>
                    <Button
                      type="button"
                      size="sm"
                      variant={session.current ? "destructive" : "outline"}
                      onClick={() => void revokeSession(session.session_id, session.current)}
                    >
                      {session.current
                        ? locale === "de"
                          ? "Abmelden"
                          : "Sign out"
                        : locale === "de"
                          ? "Widerrufen"
                          : "Revoke"}
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
              {sessions.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={5}>{locale === "de" ? "Noch keine aktiven Sitzungen." : "No active sessions yet."}</TableCell>
                </TableRow>
              ) : null}
            </TableBody>
          </Table>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <CardTitle>{locale === "de" ? "Geteilte Gruppen" : "Shared groups"}</CardTitle>
              <CardDescription>
                {locale === "de"
                  ? "Erstellen und verwalten Sie Haushalts- oder Community-Arbeitsbereiche mit Rollen und Mitgliedern."
                  : "Create and manage household or community workspaces with roles and members."}
              </CardDescription>
            </div>
            <Button onClick={openCreateGroup}>{locale === "de" ? "Gruppe erstellen" : "Create group"}</Button>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          {groups.map((group) => (
            <div key={group.group_id} className="rounded-lg border p-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="space-y-1">
                  <div className="flex items-center gap-2">
                    <h3 className="font-semibold">{group.name}</h3>
                    <Badge variant="secondary">{labelForGroupType(locale, group.group_type)}</Badge>
                    <Badge variant={group.status === "active" ? "default" : "secondary"}>
                      {group.status === "active"
                        ? locale === "de"
                          ? "Aktiv"
                          : "Active"
                        : locale === "de"
                          ? "Archiviert"
                          : "Archived"}
                    </Badge>
                  </div>
                  <p className="text-sm text-muted-foreground">
                    {locale === "de" ? "Ihre Rolle" : "Your role"}: {group.viewer_role ? labelForRole(locale, group.viewer_role) : "—"}
                  </p>
                </div>
                {group.can_manage ? (
                  <Button variant="outline" size="sm" onClick={() => openEditGroup(group)}>
                    {t("common.edit")}
                  </Button>
                ) : null}
              </div>

              <div className="mt-4 space-y-3">
                <div className="text-sm font-medium">{locale === "de" ? "Mitglieder" : "Members"}</div>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>{locale === "de" ? "Benutzer" : "User"}</TableHead>
                      <TableHead>{locale === "de" ? "Rolle" : "Role"}</TableHead>
                      <TableHead>{locale === "de" ? "Status" : "Status"}</TableHead>
                      <TableHead>{t("common.actions")}</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {group.members.map((member) => (
                      <TableRow key={`${member.group_id}:${member.user_id}`}>
                        <TableCell>{member.user.display_name || member.user.username}</TableCell>
                        <TableCell>
                          {group.can_manage ? (
                            <select
                              className="h-9 rounded-md border bg-background px-3 text-sm"
                              value={member.role}
                              onChange={(event) =>
                                void changeMemberRole(
                                  group.group_id,
                                  member.user_id,
                                  event.target.value as "owner" | "manager" | "member"
                                )
                              }
                            >
                              <option value="owner">{labelForRole(locale, "owner")}</option>
                              <option value="manager">{labelForRole(locale, "manager")}</option>
                              <option value="member">{labelForRole(locale, "member")}</option>
                            </select>
                          ) : (
                            labelForRole(locale, member.role)
                          )}
                        </TableCell>
                        <TableCell>{labelForMembershipStatus(locale, member.membership_status)}</TableCell>
                        <TableCell>
                          {group.can_manage ? (
                            <Button
                              type="button"
                              size="sm"
                              variant="outline"
                              onClick={() => void removeMember(group.group_id, member.user_id)}
                            >
                              {locale === "de" ? "Entfernen" : "Remove"}
                            </Button>
                          ) : null}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>

                {group.can_manage ? (
                  <div className="grid gap-3 md:grid-cols-[1.5fr,1fr,auto]">
                    <select
                      className="h-9 rounded-md border bg-background px-3 text-sm"
                      value={pendingMembers[group.group_id]?.userId ?? ""}
                      onChange={(event) =>
                        setPendingMembers((current) => ({
                          ...current,
                          [group.group_id]: {
                            userId: event.target.value,
                            role: current[group.group_id]?.role ?? "member"
                          }
                        }))
                      }
                    >
                      <option value="">{locale === "de" ? "Benutzer auswählen" : "Select user"}</option>
                      {groupDirectory
                        .filter((user) => !group.members.some((member) => member.user_id === user.user_id))
                        .map((user) => (
                          <option key={user.user_id} value={user.user_id}>
                            {user.display_name || user.username}
                          </option>
                        ))}
                    </select>
                    <select
                      className="h-9 rounded-md border bg-background px-3 text-sm"
                      value={pendingMembers[group.group_id]?.role ?? "member"}
                      onChange={(event) =>
                        setPendingMembers((current) => ({
                          ...current,
                          [group.group_id]: {
                            userId: current[group.group_id]?.userId ?? "",
                            role: event.target.value as "owner" | "manager" | "member"
                          }
                        }))
                      }
                    >
                      <option value="owner">{labelForRole(locale, "owner")}</option>
                      <option value="manager">{labelForRole(locale, "manager")}</option>
                      <option value="member">{labelForRole(locale, "member")}</option>
                    </select>
                    <Button type="button" onClick={() => void addMember(group)}>
                      {locale === "de" ? "Mitglied hinzufügen" : "Add member"}
                    </Button>
                  </div>
                ) : null}
              </div>
            </div>
          ))}

          {groups.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              {locale === "de"
                ? "Noch keine geteilten Gruppen. Persönliche Nutzung bleibt vollständig unterstützt."
                : "No shared groups yet. Personal mode remains fully supported."}
            </p>
          ) : null}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{t("pages.usersSettings.usersTitle")}</CardTitle>
          <CardDescription>
            {locale === "de"
              ? "Desktop-lokale Benutzerkonten bleiben von geteilten Gruppen getrennt."
              : "Desktop-local user accounts remain separate from shared groups."}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {isAdmin ? (
            <>
              <div className="mb-4 flex flex-row flex-wrap items-center justify-between gap-3">
                <div className="text-sm text-muted-foreground">
                  {locale === "de" ? "Administratoren verwalten lokale Anmeldekonten." : "Admins manage local sign-in accounts."}
                </div>
                <Button type="button" onClick={openCreateUser}>
                  {t("pages.usersSettings.addUser")}
                </Button>
              </div>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>{t("common.username")}</TableHead>
                    <TableHead>{t("common.displayName")}</TableHead>
                    <TableHead>{t("common.created")}</TableHead>
                    <TableHead>{t("common.actions")}</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {users.map((user) => (
                    <TableRow key={user.user_id}>
                      <TableCell>{user.username}</TableCell>
                      <TableCell>{user.display_name || t("pages.usersSettings.noDisplayName")}</TableCell>
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
                      <TableCell colSpan={4}>{t("pages.usersSettings.noUsers")}</TableCell>
                    </TableRow>
                  ) : null}
                </TableBody>
              </Table>
            </>
          ) : (
            <p className="text-sm text-muted-foreground">{t("pages.usersSettings.adminOnly")}</p>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{t("pages.usersSettings.keysTitle")}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
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
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{t("pages.usersSettings.backupTitle")}</CardTitle>
          <CardDescription>{t("pages.usersSettings.backupDescription")}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
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
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>{t("pages.usersSettings.restoreTitle")}</CardTitle>
          <CardDescription>{t("pages.usersSettings.restoreDescription")}</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
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

      <Dialog open={groupEditor.open} onOpenChange={(open) => setGroupEditor((previous) => ({ ...previous, open }))}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>
              {groupEditor.groupId
                ? locale === "de"
                  ? "Geteilte Gruppe bearbeiten"
                  : "Edit shared group"
                : locale === "de"
                  ? "Geteilte Gruppe erstellen"
                  : "Create shared group"}
            </DialogTitle>
            <DialogDescription>
              {locale === "de"
                ? "Richten Sie einen Haushalts- oder Community-Arbeitsbereich für gemeinsame Finanzen ein."
                : "Set up a household or community workspace for shared finances."}
            </DialogDescription>
          </DialogHeader>

          <form className="space-y-3" onSubmit={(event) => void submitGroupEditor(event)}>
            <div className="space-y-2">
              <Label htmlFor="group-name">{locale === "de" ? "Name" : "Name"}</Label>
              <Input
                id="group-name"
                value={groupEditor.name}
                onChange={(event) => setGroupEditor((previous) => ({ ...previous, name: event.target.value }))}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="group-type">{locale === "de" ? "Typ" : "Type"}</Label>
              <select
                id="group-type"
                className="h-9 w-full rounded-md border bg-background px-3 text-sm"
                value={groupEditor.groupType}
                onChange={(event) =>
                  setGroupEditor((previous) => ({
                    ...previous,
                    groupType: event.target.value as "household" | "community"
                  }))
                }
              >
                <option value="household">{labelForGroupType(locale, "household")}</option>
                <option value="community">{labelForGroupType(locale, "community")}</option>
              </select>
            </div>
            {groupEditor.groupId ? (
              <div className="space-y-2">
                <Label htmlFor="group-status">{locale === "de" ? "Status" : "Status"}</Label>
                <select
                  id="group-status"
                  className="h-9 w-full rounded-md border bg-background px-3 text-sm"
                  value={groupEditor.status}
                  onChange={(event) =>
                    setGroupEditor((previous) => ({
                      ...previous,
                      status: event.target.value as "active" | "archived"
                    }))
                  }
                >
                  <option value="active">{locale === "de" ? "Aktiv" : "Active"}</option>
                  <option value="archived">{locale === "de" ? "Archiviert" : "Archived"}</option>
                </select>
              </div>
            ) : null}
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => setGroupEditor(EMPTY_GROUP_EDITOR)}>
                {t("common.cancel")}
              </Button>
              <Button
                type="submit"
                disabled={createGroupMutation.isPending || updateGroupMutation.isPending}
              >
                {t("common.save")}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </section>
  );
}
