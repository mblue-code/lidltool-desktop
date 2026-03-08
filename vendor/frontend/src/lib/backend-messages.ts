import type { TranslationKey } from "@/i18n";
import { ApiDomainError } from "@/lib/api-errors";
import type { ApiWarning } from "@/lib/api-messages";

const BACKEND_MESSAGE_KEYS = {
  admin_privileges_required: "backend.error.adminPrivilegesRequired",
  admin_user_required: "backend.error.adminUserRequired",
  api_auth_credential_missing_or_invalid: "backend.warning.apiAuthCredentialMissingOrInvalid",
  api_key_not_found: "backend.error.apiKeyNotFound",
  auth_invalid_credentials: "backend.error.authInvalidCredentials",
  auth_required: "backend.error.authRequired",
  cannot_delete_current_user: "backend.error.cannotDeleteCurrentUser",
  cannot_demote_current_user: "backend.error.cannotDemoteCurrentUser",
  chat_thread_already_generating: "backend.error.chatThreadAlreadyGenerating",
  chat_thread_conflict: "backend.error.chatThreadConflict",
  chat_thread_not_found: "backend.error.chatThreadNotFound",
  connector_preview_bootstrap_started: "backend.warning.connectorPreviewBootstrapStarted",
  connector_preview_sync_started: "backend.warning.connectorPreviewSyncStarted",
  connector_remote_browser_session_unavailable: "backend.warning.connectorRemoteBrowserSessionUnavailable",
  connector_retryable_sources_missing: "backend.error.connectorRetryableSourcesMissing",
  connector_unsupported_sources: "backend.error.connectorUnsupportedSources",
  data_integrity_conflict: "backend.error.dataIntegrityConflict",
  document_not_found: "backend.error.documentNotFound",
  internal_server_error: "backend.error.internalServerError",
  invalid_field_value: "backend.error.invalidFieldValue",
  invalid_json_payload: "backend.error.invalidJsonPayload",
  invalid_or_expired_session_token: "backend.error.invalidOrExpiredSessionToken",
  invalid_related_resource_reference: "backend.error.invalidRelatedResourceReference",
  invalid_request_payload: "backend.error.invalidRequestPayload",
  invalid_source_for_upload: "backend.error.invalidSourceForUpload",
  message_content_required: "backend.error.messageContentRequired",
  missing_required_field: "backend.error.missingRequiredField",
  missing_token_signing_secret: "backend.error.missingTokenSigningSecret",
  rate_limited: "backend.error.rateLimited",
  resource_conflict: "backend.error.resourceConflict",
  service_not_ready: "backend.error.serviceNotReady",
  session_user_not_found: "backend.error.sessionUserNotFound",
  setup_already_completed: "backend.error.setupAlreadyCompleted",
  source_not_found: "backend.error.sourceNotFound",
  transaction_item_not_found: "backend.error.transactionItemNotFound",
  transaction_not_found: "backend.error.transactionNotFound",
  unauthorized_request: "backend.error.unauthorizedRequest",
  user_not_found: "backend.error.userNotFound"
} satisfies Record<string, TranslationKey>;

type TranslateFn = (key: TranslationKey, variables?: Record<string, string | number>) => string;

export function resolveBackendMessage(
  input: { code?: string | null; message?: string | null },
  t: TranslateFn,
  fallback?: string | null
): string {
  const code = input.code ?? null;
  const translationKey = code
    ? BACKEND_MESSAGE_KEYS[code as keyof typeof BACKEND_MESSAGE_KEYS]
    : undefined;
  if (translationKey) {
    return t(translationKey);
  }
  const message = input.message?.trim();
  if (message) {
    return message;
  }
  return fallback?.trim() || "";
}

export function resolveApiWarningMessage(warning: ApiWarning, t: TranslateFn): string {
  return resolveBackendMessage(warning, t, warning.message);
}

export function resolveApiErrorMessage(
  error: unknown,
  t: TranslateFn,
  fallback?: string | null
): string {
  if (error instanceof ApiDomainError) {
    return resolveBackendMessage({ code: error.code, message: error.message }, t, fallback);
  }
  if (error instanceof Error) {
    return error.message || fallback || "";
  }
  return fallback || "";
}
