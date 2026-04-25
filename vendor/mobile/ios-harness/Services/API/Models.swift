import Foundation

struct MobilePairingPayload: Codable {
    let protocolVersion: Int
    let desktopId: String
    let desktopName: String
    let endpointURL: String
    let pairingToken: String
    let publicKeyFingerprint: String
    let expiresAt: String

    enum CodingKeys: String, CodingKey {
        case protocolVersion = "protocol_version"
        case desktopId = "desktop_id"
        case desktopName = "desktop_name"
        case endpointURL = "endpoint_url"
        case pairingToken = "pairing_token"
        case publicKeyFingerprint = "public_key_fingerprint"
        case expiresAt = "expires_at"
    }
}

struct MobileHandshakeRequest: Encodable {
    let deviceId: String
    let deviceName: String
    let platform: String
    let pairingToken: String
    let publicKeyFingerprint: String

    enum CodingKeys: String, CodingKey {
        case deviceId = "device_id"
        case deviceName = "device_name"
        case platform
        case pairingToken = "pairing_token"
        case publicKeyFingerprint = "public_key_fingerprint"
    }
}

struct MobileHandshakeResponse: Codable {
    let pairedDeviceId: String
    let desktopId: String
    let desktopName: String
    let endpointURL: String
    let syncToken: String
    let issuedAt: String
    let expiresAt: String

    enum CodingKeys: String, CodingKey {
        case pairedDeviceId = "paired_device_id"
        case desktopId = "desktop_id"
        case desktopName = "desktop_name"
        case endpointURL = "endpoint_url"
        case syncToken = "sync_token"
        case issuedAt = "issued_at"
        case expiresAt = "expires_at"
    }
}

struct MobileManualTransactionRequest: Encodable {
    let merchantName: String
    let totalCents: Int
    let currency: String
    let note: String?
    let idempotencyKey: String

    enum CodingKeys: String, CodingKey {
        case merchantName = "merchant_name"
        case totalCents = "total_cents"
        case currency
        case note
        case idempotencyKey = "idempotency_key"
    }
}

struct MobileManualTransactionResponse: Decodable {
    let transactionId: String?
    let reused: Bool?

    enum CodingKeys: String, CodingKey {
        case transactionId = "transaction_id"
        case reused
    }
}

struct PairedDesktop: Codable, Equatable {
    let pairedDeviceId: String
    let desktopId: String
    let desktopName: String
    let endpointURL: String
    let publicKeyFingerprint: String
    let issuedAt: String
    let expiresAt: String

    enum CodingKeys: String, CodingKey {
        case pairedDeviceId = "paired_device_id"
        case desktopId = "desktop_id"
        case desktopName = "desktop_name"
        case endpointURL = "endpoint_url"
        case publicKeyFingerprint = "public_key_fingerprint"
        case issuedAt = "issued_at"
        case expiresAt = "expires_at"
    }
}

struct SyncMetadata: Codable, Equatable {
    var cursor: String?
    var serverTime: String?
    var lastSyncAt: String?
    var lastError: String?

    enum CodingKeys: String, CodingKey {
        case cursor
        case serverTime = "server_time"
        case lastSyncAt = "last_sync_at"
        case lastError = "last_error"
    }
}

enum CaptureQueueState: String, Codable, CaseIterable {
    case localOnly = "local_only"
    case queuedForUpload = "queued_for_upload"
    case uploaded
    case processingOnDesktop = "processing_on_desktop"
    case needsReview = "needs_review"
    case completed
    case failed

    var label: String {
        rawValue.replacingOccurrences(of: "_", with: " ")
    }

    var localizedLabel: String {
        switch self {
        case .localOnly: return L10n.tr("mobile.status.localOnly")
        case .queuedForUpload: return L10n.tr("mobile.status.queued")
        case .uploaded: return L10n.tr("mobile.status.uploaded")
        case .processingOnDesktop: return L10n.tr("mobile.status.processing")
        case .needsReview: return L10n.tr("mobile.status.needsReview")
        case .completed: return L10n.tr("mobile.status.completed")
        case .failed: return L10n.tr("mobile.status.failed")
        }
    }
}

struct CaptureQueueItem: Codable, Identifiable, Equatable {
    let id: String
    var fileName: String
    var localPath: String
    var mimeType: String
    var byteCount: Int
    var capturedAt: String
    var state: CaptureQueueState
    var desktopCaptureId: String?
    var statusMessage: String?

    enum CodingKeys: String, CodingKey {
        case id
        case fileName = "file_name"
        case localPath = "local_path"
        case mimeType = "mime_type"
        case byteCount = "byte_count"
        case capturedAt = "captured_at"
        case state
        case desktopCaptureId = "desktop_capture_id"
        case statusMessage = "status_message"
    }
}

struct MobileTransaction: Codable, Identifiable, Equatable {
    let id: String
    var purchasedAt: String
    var merchantName: String
    var totalCents: Int
    var currency: String
    var category: String?
    var note: String?

    enum CodingKeys: String, CodingKey {
        case id
        case purchasedAt = "purchased_at"
        case merchantName = "merchant_name"
        case totalCents = "total_cents"
        case currency
        case category
        case note
    }
}

struct MobileTransactionItem: Codable, Identifiable, Equatable {
    let id: String
    let transactionId: String
    var name: String
    var quantity: Double?
    var lineTotalCents: Int
    var category: String?

    enum CodingKeys: String, CodingKey {
        case id
        case transactionId = "transaction_id"
        case name
        case quantity
        case lineTotalCents = "line_total_cents"
        case category
    }
}

struct BudgetSummary: Codable, Equatable {
    var period: String
    var spentCents: Int
    var budgetCents: Int
    var currency: String
    var categorySummaries: [BudgetCategorySummary]

    enum CodingKeys: String, CodingKey {
        case period
        case spentCents = "spent_cents"
        case budgetCents = "budget_cents"
        case currency
        case categorySummaries = "category_summaries"
    }
}

struct BudgetCategorySummary: Codable, Identifiable, Equatable {
    var id: String { category }
    var category: String
    var spentCents: Int
    var budgetCents: Int

    enum CodingKeys: String, CodingKey {
        case category
        case spentCents = "spent_cents"
        case budgetCents = "budget_cents"
    }
}

struct CaptureUploadMetadata: Encodable {
    let captureId: String
    let capturedAt: String
    let fileName: String
    let mimeType: String
    let byteCount: Int

    enum CodingKeys: String, CodingKey {
        case captureId = "capture_id"
        case capturedAt = "captured_at"
        case fileName = "file_name"
        case mimeType = "mime_type"
        case byteCount = "byte_count"
    }
}

struct CaptureUploadResponse: Decodable {
    let captureId: String
    let status: String
    let message: String?

    enum CodingKeys: String, CodingKey {
        case captureId = "capture_id"
        case status
        case message
    }
}

struct MobileSyncChangesResponse: Decodable {
    let cursor: String
    let serverTime: String
    let transactions: [MobileTransaction]
    let transactionItems: [MobileTransactionItem]
    let budgetSummary: BudgetSummary?
    let captureStatuses: [CaptureStatusUpdate]

    enum CodingKeys: String, CodingKey {
        case cursor
        case serverTime = "server_time"
        case transactions
        case transactionItems = "transaction_items"
        case budgetSummary = "budget_summary"
        case captureStatuses = "capture_statuses"
    }
}

struct CaptureStatusUpdate: Decodable {
    let captureId: String
    let status: CaptureQueueState
    let message: String?

    enum CodingKeys: String, CodingKey {
        case captureId = "capture_id"
        case status
        case message
    }
}

struct APIEnvelope<T: Decodable>: Decodable {
    let ok: Bool
    let result: T?
    let warnings: [String]
    let error: String?
    let errorCode: String?

    enum CodingKeys: String, CodingKey {
        case ok
        case result
        case warnings
        case error
        case errorCode = "error_code"
    }
}

struct HealthStatus: Decodable {
    let status: String
    let ready: Bool
}

struct AuthSetupStatus: Decodable {
    let required: Bool
    let bootstrapTokenRequired: Bool

    enum CodingKeys: String, CodingKey {
        case required
        case bootstrapTokenRequired = "bootstrap_token_required"
    }
}

struct SessionToken: Decodable {
    let accessToken: String
    let tokenType: String
    let expiresAt: String
    let expiresInSeconds: Int

    enum CodingKeys: String, CodingKey {
        case accessToken = "access_token"
        case tokenType = "token_type"
        case expiresAt = "expires_at"
        case expiresInSeconds = "expires_in_seconds"
    }
}

struct SessionRecord: Decodable {
    let sessionId: String
    let deviceLabel: String?
    let clientName: String?
    let clientPlatform: String?
    let expiresAt: String

    enum CodingKeys: String, CodingKey {
        case sessionId = "session_id"
        case deviceLabel = "device_label"
        case clientName = "client_name"
        case clientPlatform = "client_platform"
        case expiresAt = "expires_at"
    }
}

struct CurrentUser: Decodable {
    let userId: String
    let username: String
    let displayName: String?
    let isAdmin: Bool
    let token: SessionToken?
    let session: SessionRecord?

    enum CodingKeys: String, CodingKey {
        case userId = "user_id"
        case username
        case displayName = "display_name"
        case isAdmin = "is_admin"
        case token
        case session
    }
}

struct DashboardSummary: Decodable {
    let period: DashboardPeriod
    let totals: DashboardTotals
    let recentTransactions: [TransactionListItem]
    let offers: OfferCounts
    let sources: DashboardSourceCounts
    let generatedAt: String

    enum CodingKeys: String, CodingKey {
        case period
        case totals
        case recentTransactions = "recent_transactions"
        case offers
        case sources
        case generatedAt = "generated_at"
    }
}

struct DashboardPeriod: Decodable {
    let year: Int
    let month: Int?
}

struct DashboardTotals: Decodable {
    let receiptCount: Int
    let grossCents: Int
    let grossCurrency: String
    let paidCents: Int
    let paidCurrency: String
    let savedCents: Int
    let savedCurrency: String

    enum CodingKeys: String, CodingKey {
        case receiptCount = "receipt_count"
        case grossCents = "gross_cents"
        case grossCurrency = "gross_currency"
        case paidCents = "paid_cents"
        case paidCurrency = "paid_currency"
        case savedCents = "saved_cents"
        case savedCurrency = "saved_currency"
    }
}

struct DashboardSourceCounts: Decodable {
    let count: Int
    let needsAttention: Int
    let healthy: Int
    let syncing: Int

    enum CodingKeys: String, CodingKey {
        case count
        case needsAttention = "needs_attention"
        case healthy
        case syncing
    }
}

struct TransactionListResponse: Decodable {
    let count: Int
    let total: Int
    let limit: Int
    let offset: Int
    let items: [TransactionListItem]
}

struct TransactionListItem: Decodable, Identifiable {
    let id: String
    let purchasedAt: String
    let sourceId: String
    let sourceTransactionId: String
    let storeName: String?
    let merchantName: String?
    let totalGrossCents: Int
    let discountTotalCents: Int?
    let currency: String

    enum CodingKeys: String, CodingKey {
        case id
        case purchasedAt = "purchased_at"
        case sourceId = "source_id"
        case sourceTransactionId = "source_transaction_id"
        case storeName = "store_name"
        case merchantName = "merchant_name"
        case totalGrossCents = "total_gross_cents"
        case discountTotalCents = "discount_total_cents"
        case currency
    }
}

struct TransactionDetailResponse: Decodable, Identifiable {
    let transaction: TransactionDetail
    let items: [TransactionItem]
    let discounts: [TransactionDiscount]
    let documents: [TransactionDocument]

    var id: String { transaction.id }
}

struct TransactionDetail: Decodable {
    let id: String
    let sourceId: String
    let sourceTransactionId: String
    let purchasedAt: String
    let merchantName: String?
    let totalGrossCents: Int
    let discountTotalCents: Int?
    let currency: String

    enum CodingKeys: String, CodingKey {
        case id
        case sourceId = "source_id"
        case sourceTransactionId = "source_transaction_id"
        case purchasedAt = "purchased_at"
        case merchantName = "merchant_name"
        case totalGrossCents = "total_gross_cents"
        case discountTotalCents = "discount_total_cents"
        case currency
    }
}

struct TransactionItem: Decodable, Identifiable {
    let id: String
    let lineNo: Int
    let name: String
    let qty: Double
    let unit: String?
    let lineTotalCents: Int
    let category: String?

    enum CodingKeys: String, CodingKey {
        case id
        case lineNo = "line_no"
        case name
        case qty
        case unit
        case lineTotalCents = "line_total_cents"
        case category
    }
}

struct TransactionDiscount: Decodable, Identifiable {
    let id: String
    let sourceLabel: String
    let scope: String
    let kind: String
    let amountCents: Int

    enum CodingKeys: String, CodingKey {
        case id
        case sourceLabel = "source_label"
        case scope
        case kind
        case amountCents = "amount_cents"
    }
}

struct TransactionDocument: Decodable, Identifiable {
    let id: String
    let mimeType: String
    let fileName: String?
    let createdAt: String

    enum CodingKeys: String, CodingKey {
        case id
        case mimeType = "mime_type"
        case fileName = "file_name"
        case createdAt = "created_at"
    }
}

struct OfferOverview: Decodable {
    let counts: OfferCounts
}

struct OfferCounts: Decodable {
    let watchlists: Int
    let activeMatches: Int
    let unreadAlerts: Int

    enum CodingKeys: String, CodingKey {
        case watchlists
        case activeMatches = "active_matches"
        case unreadAlerts = "unread_alerts"
    }
}

struct OfferWatchlistListResponse: Decodable {
    let count: Int
    let items: [OfferWatchlist]
}

struct OfferWatchlist: Decodable, Identifiable {
    let id: String
    let productName: String?
    let queryText: String?
    let sourceId: String?
    let active: Bool
    let notes: String?
    let createdAt: String
    let updatedAt: String

    enum CodingKeys: String, CodingKey {
        case id
        case productName = "product_name"
        case queryText = "query_text"
        case sourceId = "source_id"
        case active
        case notes
        case createdAt = "created_at"
        case updatedAt = "updated_at"
    }
}

struct OfferAlertListResponse: Decodable {
    let count: Int
    let items: [OfferAlert]
}

struct OfferAlert: Decodable, Identifiable {
    let id: String
    let status: String
    let eventType: String
    let title: String
    let body: String?
    let readAt: String?
    let createdAt: String
    let match: OfferMatch?

    enum CodingKeys: String, CodingKey {
        case id
        case status
        case eventType = "event_type"
        case title
        case body
        case readAt = "read_at"
        case createdAt = "created_at"
        case match
    }
}

struct OfferMatch: Decodable {
    let offer: OfferCard
}

struct OfferCard: Decodable {
    let sourceId: String
    let merchantName: String
    let title: String
    let priceCents: Int?
    let originalPriceCents: Int?
    let discountPercent: Double?

    enum CodingKeys: String, CodingKey {
        case sourceId = "source_id"
        case merchantName = "merchant_name"
        case title
        case priceCents = "price_cents"
        case originalPriceCents = "original_price_cents"
        case discountPercent = "discount_percent"
    }
}

struct SourceStatusListResponse: Decodable {
    let count: Int
    let items: [SourceStatus]
    let sources: [SourceStatus]
}

struct SourceStatus: Decodable, Identifiable {
    let sourceId: String
    let displayName: String
    let kind: String
    let enabled: Bool
    let status: String
    let needsAttention: Bool
    let auth: SourceAuthStatus
    let sync: SourceSyncStatus
    let account: SourceAccount

    var id: String { sourceId }

    enum CodingKeys: String, CodingKey {
        case sourceId = "source_id"
        case displayName = "display_name"
        case kind
        case enabled
        case status
        case needsAttention = "needs_attention"
        case auth
        case sync
        case account
    }
}

struct SourceAccount: Decodable {
    let id: String?
    let accountRef: String?
    let status: String?
    let lastSuccessAt: String?

    enum CodingKeys: String, CodingKey {
        case id
        case accountRef = "account_ref"
        case status
        case lastSuccessAt = "last_success_at"
    }
}

struct SourceAuthStatus: Decodable {
    let sourceId: String
    let state: String
    let detail: String?
    let reauthRequired: Bool
    let needsConnection: Bool
    let availableActions: [String]

    enum CodingKeys: String, CodingKey {
        case sourceId = "source_id"
        case state
        case detail
        case reauthRequired = "reauth_required"
        case needsConnection = "needs_connection"
        case availableActions = "available_actions"
    }
}

struct SourceSyncStatus: Decodable {
    let sourceId: String
    let status: String
    let inProgress: Bool
    let latestJob: SourceLatestJob?
    let lastSuccessAt: String?

    enum CodingKeys: String, CodingKey {
        case sourceId = "source_id"
        case status
        case inProgress = "in_progress"
        case latestJob = "latest_job"
        case lastSuccessAt = "last_success_at"
    }
}

struct SourceLatestJob: Decodable {
    let jobId: String
    let status: String
    let triggerType: String
    let startedAt: String?
    let finishedAt: String?
    let error: String?

    enum CodingKeys: String, CodingKey {
        case jobId = "job_id"
        case status
        case triggerType = "trigger_type"
        case startedAt = "started_at"
        case finishedAt = "finished_at"
        case error
    }
}

struct ChatThreadListResponse: Decodable {
    let items: [ChatThread]
    let total: Int
}

struct ChatThread: Decodable, Identifiable {
    let threadId: String
    let title: String
    let streamStatus: String
    let createdAt: String
    let updatedAt: String

    var id: String { threadId }

    enum CodingKeys: String, CodingKey {
        case threadId = "thread_id"
        case title
        case streamStatus = "stream_status"
        case createdAt = "created_at"
        case updatedAt = "updated_at"
    }
}

struct ChatMessageListResponse: Decodable {
    let items: [ChatMessage]
    let total: Int
}

struct ChatMessage: Decodable, Identifiable {
    let messageId: String
    let threadId: String
    let role: String
    let contentJSON: JSONValue
    let createdAt: String
    let toolName: String?
    let error: String?

    var id: String { messageId }
    var plainText: String { contentJSON.plainText }

    enum CodingKeys: String, CodingKey {
        case messageId = "message_id"
        case threadId = "thread_id"
        case role
        case contentJSON = "content_json"
        case createdAt = "created_at"
        case toolName = "tool_name"
        case error
    }
}

struct ChatMessageCreateResult: Decodable {
    let thread: ChatThread
    let message: ChatMessage
}

struct DocumentUploadResult: Decodable {
    let documentId: String
    let storageURI: String
    let sha256: String
    let mimeType: String
    let status: String

    enum CodingKeys: String, CodingKey {
        case documentId = "document_id"
        case storageURI = "storage_uri"
        case sha256
        case mimeType = "mime_type"
        case status
    }
}

struct DocumentProcessResult: Decodable {
    let documentId: String
    let jobId: String
    let status: String
    let reused: Bool

    enum CodingKeys: String, CodingKey {
        case documentId = "document_id"
        case jobId = "job_id"
        case status
        case reused
    }
}

struct DocumentStatusResult: Decodable {
    let documentId: String
    let transactionId: String?
    let status: String
    let reviewStatus: String?
    let ocrConfidence: Double?

    enum CodingKeys: String, CodingKey {
        case documentId = "document_id"
        case transactionId = "transaction_id"
        case status
        case reviewStatus = "review_status"
        case ocrConfidence = "ocr_confidence"
    }
}

struct ChatStreamEvent: Decodable {
    let type: String
    let contentIndex: Int?
    let delta: String?
    let reason: String?
    let toolName: String?
    let id: String?
    let usage: ChatStreamUsage?

    enum CodingKeys: String, CodingKey {
        case type
        case contentIndex
        case delta
        case reason
        case toolName
        case id
        case usage
    }
}

struct ChatStreamUsage: Decodable {
    let input: Int?
    let output: Int?
    let totalTokens: Int?

    enum CodingKeys: String, CodingKey {
        case input
        case output
        case totalTokens
    }
}

struct AuthLoginRequest: Encodable {
    let username: String
    let password: String
    let sessionMode: String = "token"
    let deviceLabel: String = "iOS Harness"
    let clientName: String = "iOS Harness"
    let clientPlatform: String = "ios"

    enum CodingKeys: String, CodingKey {
        case username
        case password
        case sessionMode = "session_mode"
        case deviceLabel = "device_label"
        case clientName = "client_name"
        case clientPlatform = "client_platform"
    }
}

struct ChatThreadCreateRequest: Encodable {
    let title: String?
}

struct ChatMessageCreateRequest: Encodable {
    let content: String
    let idempotencyKey: String

    enum CodingKeys: String, CodingKey {
        case content
        case idempotencyKey = "idempotency_key"
    }
}

struct ChatStreamRequest: Encodable {
    let modelID: String? = nil

    enum CodingKeys: String, CodingKey {
        case modelID = "model_id"
    }
}

struct OfferWatchlistCreateRequest: Encodable {
    let queryText: String

    enum CodingKeys: String, CodingKey {
        case queryText = "query_text"
    }
}

struct OfferWatchlistUpdateRequest: Encodable {
    let active: Bool
}

struct OfferAlertUpdateRequest: Encodable {
    let read: Bool
}

struct MobileDeviceRegistrationRequest: Encodable {
    let platform: String
    let provider: String
    let deviceToken: String
    let deviceLabel: String?
    let bundleIdentifier: String?
    let appVersion: String?
    let buildVersion: String?
    let systemVersion: String?
    let localeIdentifier: String
    let authorizationStatus: String
    let pushEnvironment: String?

    enum CodingKeys: String, CodingKey {
        case platform
        case provider
        case deviceToken = "device_token"
        case deviceLabel = "device_label"
        case bundleIdentifier = "bundle_identifier"
        case appVersion = "app_version"
        case buildVersion = "build_version"
        case systemVersion = "system_version"
        case localeIdentifier = "locale_identifier"
        case authorizationStatus = "authorization_status"
        case pushEnvironment = "push_environment"
    }
}

struct MobileDeviceRegistrationResponse: Decodable {
    let deviceId: String?
    let platform: String?
    let provider: String?
    let deviceToken: String?
    let status: String?
    let message: String?
    let registeredAt: String?
    let updatedAt: String?

    enum CodingKeys: String, CodingKey {
        case deviceId = "device_id"
        case platform
        case provider
        case deviceToken = "device_token"
        case status
        case message
        case registeredAt = "registered_at"
        case updatedAt = "updated_at"
    }
}

enum JSONValue: Codable {
    case string(String)
    case number(Double)
    case bool(Bool)
    case object([String: JSONValue])
    case array([JSONValue])
    case null

    init(from decoder: Decoder) throws {
        let container = try decoder.singleValueContainer()
        if container.decodeNil() {
            self = .null
        } else if let value = try? container.decode(Bool.self) {
            self = .bool(value)
        } else if let value = try? container.decode(Double.self) {
            self = .number(value)
        } else if let value = try? container.decode(String.self) {
            self = .string(value)
        } else if let value = try? container.decode([String: JSONValue].self) {
            self = .object(value)
        } else if let value = try? container.decode([JSONValue].self) {
            self = .array(value)
        } else {
            throw DecodingError.typeMismatch(JSONValue.self, .init(codingPath: decoder.codingPath, debugDescription: "Unsupported JSON value"))
        }
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.singleValueContainer()
        switch self {
        case .string(let value): try container.encode(value)
        case .number(let value): try container.encode(value)
        case .bool(let value): try container.encode(value)
        case .object(let value): try container.encode(value)
        case .array(let value): try container.encode(value)
        case .null: try container.encodeNil()
        }
    }

    var plainText: String {
        switch self {
        case .string(let value):
            return value
        case .number(let value):
            return String(value)
        case .bool(let value):
            return String(value)
        case .array(let values):
            return values.map(\.plainText).filter { !$0.isEmpty }.joined(separator: "\n").trimmingCharacters(in: .whitespacesAndNewlines)
        case .object(let value):
            if case .string(let type)? = value["type"], type == "text", case .string(let text)? = value["text"] {
                return text
            }
            if case .string(let text)? = value["text"], !text.isEmpty {
                return text
            }
            return value.values.map(\.plainText).filter { !$0.isEmpty }.joined(separator: "\n").trimmingCharacters(in: .whitespacesAndNewlines)
        case .null:
            return ""
        }
    }
}
