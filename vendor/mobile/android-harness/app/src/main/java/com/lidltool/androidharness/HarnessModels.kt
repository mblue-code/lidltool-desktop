package com.lidltool.androidharness

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive

@Serializable
data class ApiEnvelope<T>(
    val ok: Boolean,
    val result: T? = null,
    val warnings: List<String> = emptyList(),
    val error: String? = null,
    @SerialName("error_code") val errorCode: String? = null,
)

@Serializable
data class HealthStatus(
    val status: String,
    val ready: Boolean,
)

@Serializable
data class PairingQrPayload(
    @SerialName("protocol_version") val protocolVersion: Int,
    @SerialName("desktop_id") val desktopId: String,
    @SerialName("desktop_name") val desktopName: String,
    @SerialName("endpoint_url") val endpointUrl: String,
    @SerialName("pairing_token") val pairingToken: String,
    @SerialName("public_key_fingerprint") val publicKeyFingerprint: String,
    @SerialName("expires_at") val expiresAt: String,
)

@Serializable
data class PairingHandshakeRequest(
    @SerialName("device_id") val deviceId: String,
    @SerialName("device_name") val deviceName: String,
    val platform: String,
    @SerialName("pairing_token") val pairingToken: String,
    @SerialName("public_key_fingerprint") val publicKeyFingerprint: String,
)

@Serializable
data class PairingHandshakeResponse(
    @SerialName("paired_device_id") val pairedDeviceId: String,
    @SerialName("desktop_id") val desktopId: String,
    @SerialName("desktop_name") val desktopName: String,
    @SerialName("endpoint_url") val endpointUrl: String,
    @SerialName("sync_token") val syncToken: String,
    @SerialName("issued_at") val issuedAt: String,
    @SerialName("expires_at") val expiresAt: String,
)

@Serializable
data class MobileManualTransactionRequest(
    @SerialName("merchant_name") val merchantName: String,
    @SerialName("total_cents") val totalCents: Int,
    val currency: String = "EUR",
    val note: String? = null,
    @SerialName("idempotency_key") val idempotencyKey: String,
)

@Serializable
data class MobileManualTransactionResponse(
    @SerialName("transaction_id") val transactionId: String? = null,
    val reused: Boolean = false,
)

data class StoredPairing(
    val desktopId: String,
    val desktopName: String,
    val endpointUrl: String,
    val publicKeyFingerprint: String,
    val pairedDeviceId: String,
    val syncToken: String,
    val issuedAt: String,
    val expiresAt: String,
)

data class SyncMetadata(
    val cursor: String? = null,
    val serverTime: String? = null,
    val lastSuccessAt: String? = null,
    val pendingCaptureCount: Int = 0,
)

enum class CaptureStatus {
    @SerialName("local_only")
    LOCAL_ONLY,
    @SerialName("queued_for_upload")
    QUEUED_FOR_UPLOAD,
    @SerialName("uploaded")
    UPLOADED,
    @SerialName("processing_on_desktop")
    PROCESSING_ON_DESKTOP,
    @SerialName("needs_review")
    NEEDS_REVIEW,
    @SerialName("completed")
    COMPLETED,
    @SerialName("failed")
    FAILED,
}

data class CaptureQueueEntry(
    val id: String,
    val fileName: String,
    val mimeType: String,
    val filePath: String,
    val fileSizeBytes: Long,
    val sha256: String?,
    val status: CaptureStatus,
    val note: String? = null,
    val desktopCaptureId: String? = null,
    val transactionId: String? = null,
    val error: String? = null,
    val createdAt: String,
    val updatedAt: String,
)

@Serializable
data class CaptureUploadMetadata(
    @SerialName("mobile_capture_id") val mobileCaptureId: String,
    @SerialName("file_name") val fileName: String,
    @SerialName("mime_type") val mimeType: String,
    @SerialName("file_size_bytes") val fileSizeBytes: Long,
    val sha256: String? = null,
    val note: String? = null,
    @SerialName("created_at") val createdAt: String,
)

@Serializable
data class CaptureUploadResponse(
    @SerialName("mobile_capture_id") val mobileCaptureId: String,
    @SerialName("desktop_capture_id") val desktopCaptureId: String? = null,
    val status: String,
)

@Serializable
data class MobileSyncChangesResponse(
    val cursor: String,
    @SerialName("server_time") val serverTime: String,
    val transactions: List<MobileTransaction> = emptyList(),
    @SerialName("transaction_items") val transactionItems: List<MobileTransactionItem> = emptyList(),
    @SerialName("budget_summary") val budgetSummary: MobileBudgetSummary? = null,
    @SerialName("capture_statuses") val captureStatuses: List<MobileCaptureStatus> = emptyList(),
)

@Serializable
data class MobileTransaction(
    val id: String,
    @SerialName("purchased_at") val purchasedAt: String,
    @SerialName("merchant_name") val merchantName: String? = null,
    @SerialName("total_gross_cents") val totalGrossCents: Int,
    val currency: String = "EUR",
    val category: String? = null,
    @SerialName("needs_review") val needsReview: Boolean = false,
    @SerialName("updated_at") val updatedAt: String? = null,
)

@Serializable
data class MobileTransactionItem(
    val id: String,
    @SerialName("transaction_id") val transactionId: String,
    val name: String,
    val quantity: Double? = null,
    @SerialName("line_total_cents") val lineTotalCents: Int,
    val category: String? = null,
)

@Serializable
data class MobileBudgetSummary(
    @SerialName("period_label") val periodLabel: String,
    @SerialName("spent_cents") val spentCents: Int,
    @SerialName("budget_cents") val budgetCents: Int,
    val currency: String = "EUR",
    @SerialName("updated_at") val updatedAt: String? = null,
)

@Serializable
data class MobileCaptureStatus(
    @SerialName("mobile_capture_id") val mobileCaptureId: String,
    @SerialName("desktop_capture_id") val desktopCaptureId: String? = null,
    val status: CaptureStatus,
    @SerialName("transaction_id") val transactionId: String? = null,
    val error: String? = null,
)

@Serializable
data class AuthSetupStatus(
    val required: Boolean,
    @SerialName("bootstrap_token_required") val bootstrapTokenRequired: Boolean = false,
)

@Serializable
data class SessionToken(
    @SerialName("access_token") val accessToken: String,
    @SerialName("token_type") val tokenType: String,
    @SerialName("expires_at") val expiresAt: String,
    @SerialName("expires_in_seconds") val expiresInSeconds: Int,
)

@Serializable
data class SessionRecord(
    @SerialName("session_id") val sessionId: String,
    @SerialName("device_label") val deviceLabel: String? = null,
    @SerialName("client_name") val clientName: String? = null,
    @SerialName("client_platform") val clientPlatform: String? = null,
    @SerialName("expires_at") val expiresAt: String,
)

@Serializable
data class CurrentUser(
    @SerialName("user_id") val userId: String,
    val username: String,
    @SerialName("display_name") val displayName: String? = null,
    @SerialName("is_admin") val isAdmin: Boolean,
    val token: SessionToken? = null,
    val session: SessionRecord? = null,
)

@Serializable
data class DashboardSummary(
    val period: DashboardPeriod,
    val totals: DashboardTotals,
    @SerialName("recent_transactions") val recentTransactions: List<TransactionListItem> = emptyList(),
    @SerialName("recent_transactions_pagination") val recentTransactionsPagination: Pagination = Pagination(),
    val offers: OfferCounts = OfferCounts(),
    val sources: DashboardSourceCounts = DashboardSourceCounts(),
    @SerialName("generated_at") val generatedAt: String,
)

@Serializable
data class DashboardPeriod(
    val year: Int,
    val month: Int? = null,
)

@Serializable
data class DashboardTotals(
    @SerialName("receipt_count") val receiptCount: Int = 0,
    @SerialName("gross_cents") val grossCents: Int = 0,
    @SerialName("gross_currency") val grossCurrency: String = "EUR",
    @SerialName("paid_cents") val paidCents: Int = 0,
    @SerialName("paid_currency") val paidCurrency: String = "EUR",
    @SerialName("saved_cents") val savedCents: Int = 0,
    @SerialName("saved_currency") val savedCurrency: String = "EUR",
    @SerialName("discount_total_cents") val discountTotalCents: Int? = null,
    @SerialName("discount_total_currency") val discountTotalCurrency: String? = null,
    @SerialName("savings_rate") val savingsRate: Double = 0.0,
)

@Serializable
data class DashboardSourceCounts(
    val count: Int = 0,
    @SerialName("needs_attention") val needsAttention: Int = 0,
    val healthy: Int = 0,
    val syncing: Int = 0,
)

@Serializable
data class Pagination(
    val count: Int = 0,
    val total: Int = 0,
    val limit: Int? = null,
    val offset: Int? = null,
)

@Serializable
data class TransactionListResponse(
    val count: Int = 0,
    val total: Int = 0,
    val limit: Int = 0,
    val offset: Int = 0,
    val items: List<TransactionListItem> = emptyList(),
)

@Serializable
data class TransactionListItem(
    val id: String,
    @SerialName("purchased_at") val purchasedAt: String,
    @SerialName("source_id") val sourceId: String,
    @SerialName("source_transaction_id") val sourceTransactionId: String,
    @SerialName("store_name") val storeName: String? = null,
    @SerialName("merchant_name") val merchantName: String? = null,
    @SerialName("total_gross_cents") val totalGrossCents: Int,
    @SerialName("discount_total_cents") val discountTotalCents: Int? = null,
    val currency: String = "EUR",
)

@Serializable
data class TransactionDetailResponse(
    val transaction: TransactionDetail,
    val items: List<TransactionItem> = emptyList(),
    val discounts: List<TransactionDiscount> = emptyList(),
    val documents: List<TransactionDocument> = emptyList(),
)

@Serializable
data class TransactionDetail(
    val id: String,
    @SerialName("source_id") val sourceId: String,
    @SerialName("source_transaction_id") val sourceTransactionId: String,
    @SerialName("purchased_at") val purchasedAt: String,
    @SerialName("merchant_name") val merchantName: String? = null,
    @SerialName("total_gross_cents") val totalGrossCents: Int,
    @SerialName("discount_total_cents") val discountTotalCents: Int? = null,
    val currency: String = "EUR",
    @SerialName("raw_payload") val rawPayload: JsonObject? = null,
)

@Serializable
data class TransactionItem(
    val id: String,
    @SerialName("line_no") val lineNo: Int,
    val name: String,
    val qty: Double = 0.0,
    val unit: String? = null,
    @SerialName("line_total_cents") val lineTotalCents: Int,
    val category: String? = null,
)

@Serializable
data class TransactionDiscount(
    val id: String,
    @SerialName("source_label") val sourceLabel: String,
    val scope: String,
    val kind: String,
    @SerialName("amount_cents") val amountCents: Int,
)

@Serializable
data class TransactionDocument(
    val id: String,
    @SerialName("mime_type") val mimeType: String,
    @SerialName("file_name") val fileName: String? = null,
    @SerialName("created_at") val createdAt: String,
)

@Serializable
data class OfferOverview(
    val counts: OfferCounts = OfferCounts(),
)

@Serializable
data class OfferCounts(
    val watchlists: Int = 0,
    @SerialName("active_matches") val activeMatches: Int = 0,
    @SerialName("unread_alerts") val unreadAlerts: Int = 0,
)

@Serializable
data class OfferWatchlistListResponse(
    val count: Int = 0,
    val items: List<OfferWatchlist> = emptyList(),
)

@Serializable
data class OfferWatchlist(
    val id: String,
    @SerialName("product_name") val productName: String? = null,
    @SerialName("query_text") val queryText: String? = null,
    @SerialName("source_id") val sourceId: String? = null,
    @SerialName("max_price_cents") val maxPriceCents: Int? = null,
    @SerialName("min_discount_percent") val minDiscountPercent: Double? = null,
    val active: Boolean,
    val notes: String? = null,
    @SerialName("created_at") val createdAt: String,
    @SerialName("updated_at") val updatedAt: String,
)

@Serializable
data class OfferAlertListResponse(
    val count: Int = 0,
    val items: List<OfferAlert> = emptyList(),
)

@Serializable
data class OfferAlert(
    val id: String,
    val status: String,
    @SerialName("event_type") val eventType: String,
    val title: String,
    val body: String? = null,
    @SerialName("read_at") val readAt: String? = null,
    @SerialName("created_at") val createdAt: String,
    val match: OfferMatch? = null,
)

@Serializable
data class OfferMatch(
    val offer: OfferCard,
)

@Serializable
data class OfferCard(
    @SerialName("source_id") val sourceId: String,
    @SerialName("merchant_name") val merchantName: String,
    val title: String,
    @SerialName("price_cents") val priceCents: Int? = null,
    @SerialName("original_price_cents") val originalPriceCents: Int? = null,
    @SerialName("discount_percent") val discountPercent: Double? = null,
)

@Serializable
data class MobileDeviceRegistrationRequest(
    @SerialName("device_id") val deviceId: String,
    val platform: String = "android",
    @SerialName("push_provider") val pushProvider: String = "fcm",
    @SerialName("push_token") val pushToken: String,
    @SerialName("device_label") val deviceLabel: String? = null,
    @SerialName("app_version") val appVersion: String? = null,
    @SerialName("build_number") val buildNumber: String? = null,
    val locale: String? = null,
    @SerialName("notification_permission_granted") val notificationPermissionGranted: Boolean = false,
)

@Serializable
data class SourceStatusListResponse(
    val count: Int = 0,
    val items: List<SourceStatus> = emptyList(),
    val sources: List<SourceStatus> = emptyList(),
)

@Serializable
data class SourceStatus(
    @SerialName("source_id") val sourceId: String,
    @SerialName("display_name") val displayName: String,
    val kind: String,
    val enabled: Boolean,
    val status: String,
    @SerialName("needs_attention") val needsAttention: Boolean = false,
    val auth: SourceAuthStatus,
    val sync: SourceSyncStatus,
    val account: SourceAccount = SourceAccount(),
)

@Serializable
data class SourceAccount(
    val id: String? = null,
    @SerialName("account_ref") val accountRef: String? = null,
    val status: String? = null,
    @SerialName("last_success_at") val lastSuccessAt: String? = null,
)

@Serializable
data class SourceAuthStatus(
    @SerialName("source_id") val sourceId: String,
    val state: String,
    val detail: String? = null,
    @SerialName("reauth_required") val reauthRequired: Boolean = false,
    @SerialName("needs_connection") val needsConnection: Boolean = false,
    @SerialName("available_actions") val availableActions: List<String> = emptyList(),
)

@Serializable
data class SourceSyncStatus(
    @SerialName("source_id") val sourceId: String,
    val status: String,
    @SerialName("in_progress") val inProgress: Boolean = false,
    @SerialName("latest_job") val latestJob: SourceLatestJob? = null,
    @SerialName("last_success_at") val lastSuccessAt: String? = null,
    @SerialName("last_seen_receipt_at") val lastSeenReceiptAt: String? = null,
    @SerialName("last_seen_receipt_id") val lastSeenReceiptId: String? = null,
)

@Serializable
data class SourceLatestJob(
    @SerialName("job_id") val jobId: String,
    val status: String,
    @SerialName("trigger_type") val triggerType: String,
    @SerialName("started_at") val startedAt: String? = null,
    @SerialName("finished_at") val finishedAt: String? = null,
    val error: String? = null,
)

@Serializable
data class ChatThreadListResponse(
    val items: List<ChatThread> = emptyList(),
    val total: Int = 0,
)

@Serializable
data class ChatThread(
    @SerialName("thread_id") val threadId: String,
    val title: String,
    @SerialName("stream_status") val streamStatus: String,
    @SerialName("created_at") val createdAt: String,
    @SerialName("updated_at") val updatedAt: String,
)

@Serializable
data class ChatMessageListResponse(
    val items: List<ChatMessage> = emptyList(),
    val total: Int = 0,
)

@Serializable
data class ChatMessage(
    @SerialName("message_id") val messageId: String,
    @SerialName("thread_id") val threadId: String,
    val role: String,
    @SerialName("content_json") val contentJson: JsonElement,
    @SerialName("created_at") val createdAt: String,
    @SerialName("tool_name") val toolName: String? = null,
    @SerialName("error") val error: String? = null,
)

@Serializable
data class ChatMessageCreateResult(
    val thread: ChatThread,
    val message: ChatMessage,
)

@Serializable
data class DocumentUploadResult(
    @SerialName("document_id") val documentId: String,
    @SerialName("storage_uri") val storageUri: String,
    val sha256: String,
    @SerialName("mime_type") val mimeType: String,
    val status: String,
)

@Serializable
data class DocumentProcessResult(
    @SerialName("document_id") val documentId: String,
    @SerialName("job_id") val jobId: String,
    val status: String,
    val reused: Boolean,
)

@Serializable
data class DocumentStatusResult(
    @SerialName("document_id") val documentId: String,
    @SerialName("transaction_id") val transactionId: String? = null,
    @SerialName("source_id") val sourceId: String? = null,
    val status: String,
    @SerialName("review_status") val reviewStatus: String? = null,
    @SerialName("ocr_provider") val ocrProvider: String? = null,
    @SerialName("ocr_confidence") val ocrConfidence: Double? = null,
    @SerialName("ocr_fallback_used") val ocrFallbackUsed: Boolean? = null,
    @SerialName("ocr_latency_ms") val ocrLatencyMs: Int? = null,
    @SerialName("processed_at") val processedAt: String? = null,
)

@Serializable
data class ChatStreamEvent(
    val type: String,
    @SerialName("contentIndex") val contentIndex: Int? = null,
    val delta: String? = null,
    val reason: String? = null,
    @SerialName("toolName") val toolName: String? = null,
    val id: String? = null,
    val usage: ChatStreamUsage? = null,
)

@Serializable
data class ChatStreamUsage(
    val input: Int? = null,
    val output: Int? = null,
    @SerialName("totalTokens") val totalTokens: Int? = null,
)

@Serializable
data class AuthLoginRequest(
    val username: String,
    val password: String,
    @SerialName("session_mode") val sessionMode: String = "token",
    @SerialName("device_label") val deviceLabel: String = "Android Harness",
    @SerialName("client_name") val clientName: String = "Android Harness",
    @SerialName("client_platform") val clientPlatform: String = "android",
)

@Serializable
data class ChatThreadCreateRequest(
    val title: String? = null,
)

@Serializable
data class ChatMessageCreateRequest(
    val content: String,
    @SerialName("idempotency_key") val idempotencyKey: String,
)

@Serializable
data class ChatStreamRequest(
    @SerialName("model_id") val modelId: String? = null,
)

@Serializable
data class OfferWatchlistCreateRequest(
    @SerialName("query_text") val queryText: String,
)

@Serializable
data class OfferWatchlistUpdateRequest(
    val active: Boolean,
)

@Serializable
data class OfferAlertUpdateRequest(
    val read: Boolean,
)

fun ChatMessage.plainText(): String {
    return contentJson.asPlainText()
}

fun JsonElement.asPlainText(): String {
    return when (this) {
        is JsonPrimitive -> content
        is JsonArray -> joinToString("\n") { it.asPlainText() }.trim()
        is JsonObject -> {
            val type = this["type"]?.let { (it as? JsonPrimitive)?.content }
            if (type == "text") {
                this["text"]?.let { (it as? JsonPrimitive)?.content.orEmpty() }.orEmpty()
            } else {
                this["text"]?.let { (it as? JsonPrimitive)?.content.orEmpty() }
                    ?.takeIf { it.isNotBlank() }
                    ?: values.joinToString("\n") { it.asPlainText() }.trim()
            }
        }
        else -> ""
    }
}
