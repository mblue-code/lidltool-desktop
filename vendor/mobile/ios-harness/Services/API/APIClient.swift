import Foundation
import UniformTypeIdentifiers

struct APIError: LocalizedError {
    let message: String
    let code: String?
    let statusCode: Int?

    var errorDescription: String? { message }
}

final class APIClient {
    private let baseURL: String
    private let bearerToken: String?
    private let session: URLSession
    private let decoder: JSONDecoder
    private let encoder: JSONEncoder

    init(baseURL: String, bearerToken: String? = nil, session: URLSession = .shared) {
        self.baseURL = Self.normalizeBaseURL(baseURL)
        self.bearerToken = bearerToken
        self.session = session
        self.decoder = JSONDecoder()
        self.encoder = JSONEncoder()
    }

    static func normalizeBaseURL(_ raw: String) -> String {
        let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.hasSuffix("/") ? String(trimmed.dropLast()) : trimmed
    }

    func health() async throws -> HealthStatus {
        try await get("/api/v1/health")
    }

    func setupRequired() async throws -> AuthSetupStatus {
        try await get("/api/v1/auth/setup-required")
    }

    func login(username: String, password: String) async throws -> CurrentUser {
        try await post("/api/v1/auth/login", payload: AuthLoginRequest(username: username, password: password))
    }

    func currentUser() async throws -> CurrentUser {
        try await get("/api/v1/auth/me")
    }

    func dashboardSummary() async throws -> DashboardSummary {
        try await get("/api/v1/dashboard/summary")
    }

    func transactions(query: String? = nil, limit: Int = 50) async throws -> TransactionListResponse {
        try await get(
            "/api/v1/transactions",
            params: [
                URLQueryItem(name: "limit", value: String(limit)),
                URLQueryItem(name: "query", value: query?.isEmpty == true ? nil : query)
            ]
        )
    }

    func transactionDetail(_ transactionID: String) async throws -> TransactionDetailResponse {
        try await get("/api/v1/transactions/\(transactionID)")
    }

    func offersOverview() async throws -> OfferOverview {
        try await get("/api/v1/offers")
    }

    func watchlists() async throws -> OfferWatchlistListResponse {
        try await get("/api/v1/offers/watchlists")
    }

    func updateWatchlist(id: String, active: Bool) async throws -> OfferWatchlist {
        try await patch("/api/v1/offers/watchlists/\(id)", payload: OfferWatchlistUpdateRequest(active: active))
    }

    func offerAlerts(limit: Int = 30) async throws -> OfferAlertListResponse {
        try await get(
            "/api/v1/offers/alerts",
            params: [URLQueryItem(name: "limit", value: String(limit))]
        )
    }

    func markAlertRead(id: String, read: Bool) async throws -> OfferAlert {
        try await patch("/api/v1/offers/alerts/\(id)", payload: OfferAlertUpdateRequest(read: read))
    }

    func registerCurrentMobileDevice(_ payload: MobileDeviceRegistrationRequest) async throws -> MobileDeviceRegistrationResponse {
        try await put("/api/v1/mobile/devices/current", payload: payload)
    }

    func unregisterCurrentMobileDevice() async throws {
        let _: EmptyResult = try await delete("/api/v1/mobile/devices/current")
    }

    func sourcesStatus() async throws -> SourceStatusListResponse {
        try await get("/api/v1/sources/status")
    }

    func chatThreads() async throws -> ChatThreadListResponse {
        try await get("/api/v1/chat/threads")
    }

    func createChatThread(title: String? = nil) async throws -> ChatThread {
        try await post("/api/v1/chat/threads", payload: ChatThreadCreateRequest(title: title))
    }

    func chatMessages(threadID: String) async throws -> ChatMessageListResponse {
        try await get("/api/v1/chat/threads/\(threadID)/messages")
    }

    func createChatMessage(threadID: String, content: String, idempotencyKey: String) async throws -> ChatMessageCreateResult {
        try await post(
            "/api/v1/chat/threads/\(threadID)/messages",
            payload: ChatMessageCreateRequest(content: content, idempotencyKey: idempotencyKey)
        )
    }

    func streamChat(threadID: String, onEvent: @escaping (ChatStreamEvent) async -> Void) async throws {
        let body = try encoder.encode(ChatStreamRequest())
        var request = try authorizedRequest(path: "/api/v1/chat/threads/\(threadID)/stream")
        request.httpMethod = "POST"
        request.setValue("application/json; charset=utf-8", forHTTPHeaderField: "Content-Type")
        request.httpBody = body

        let (bytes, response) = try await session.bytes(for: request)
        try validate(response: response)

        var eventLines: [String] = []
        for try await line in bytes.lines {
            if line.isEmpty {
                if !eventLines.isEmpty {
                    let payload = eventLines
                        .filter { $0.hasPrefix("data:") }
                        .map { String($0.dropFirst(5)).trimmingCharacters(in: .whitespaces) }
                        .joined(separator: "\n")
                    if !payload.isEmpty, let data = payload.data(using: .utf8) {
                        let event = try decoder.decode(ChatStreamEvent.self, from: data)
                        await onEvent(event)
                    }
                    eventLines.removeAll(keepingCapacity: true)
                }
            } else {
                eventLines.append(line)
            }
        }
    }

    func uploadDocument(fileURL: URL, source: String = "ocr_upload") async throws -> DocumentUploadResult {
        let fileData = try Data(contentsOf: fileURL)
        let mimeType = UTType(filenameExtension: fileURL.pathExtension)?.preferredMIMEType ?? "application/octet-stream"
        let boundary = UUID().uuidString
        let body = multipartData(
            boundary: boundary,
            parts: [
                .file(name: "file", filename: fileURL.lastPathComponent, mimeType: mimeType, data: fileData),
                .text(name: "source", value: source)
            ]
        )

        var request = try authorizedRequest(path: "/api/v1/documents/upload")
        request.httpMethod = "POST"
        request.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")
        request.httpBody = body
        return try await requestEnvelope(request)
    }

    func processDocument(documentID: String) async throws -> DocumentProcessResult {
        let boundary = UUID().uuidString
        let body = multipartData(boundary: boundary, parts: [])
        var request = try authorizedRequest(path: "/api/v1/documents/\(documentID)/process")
        request.httpMethod = "POST"
        request.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")
        request.httpBody = body
        return try await requestEnvelope(request)
    }

    func documentStatus(documentID: String, jobID: String? = nil) async throws -> DocumentStatusResult {
        try await get(
            "/api/v1/documents/\(documentID)/status",
            params: [URLQueryItem(name: "job_id", value: jobID)]
        )
    }

    func mobileHandshake(_ payload: MobileHandshakeRequest) async throws -> MobileHandshakeResponse {
        try await post("/api/mobile-pair/v1/handshake", payload: payload)
    }

    func uploadMobileCapture(fileURL: URL, metadata: CaptureUploadMetadata) async throws -> CaptureUploadResponse {
        let fileData = try Data(contentsOf: fileURL)
        let boundary = UUID().uuidString
        let body = multipartData(
            boundary: boundary,
            parts: [
                .file(name: "file", filename: metadata.fileName, mimeType: metadata.mimeType, data: fileData),
                .json(name: "metadata", data: try encoder.encode(metadata))
            ]
        )

        var request = try authorizedRequest(path: "/api/mobile-captures/v1")
        request.httpMethod = "POST"
        request.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")
        request.httpBody = body
        return try await requestEnvelope(request)
    }

    func mobileSyncChanges(cursor: String?) async throws -> MobileSyncChangesResponse {
        try await get(
            "/api/mobile-sync/v1/changes",
            params: [URLQueryItem(name: "cursor", value: cursor)]
        )
    }

    func createMobileManualTransaction(_ payload: MobileManualTransactionRequest) async throws -> MobileManualTransactionResponse {
        try await post("/api/mobile-sync/v1/manual-transactions", payload: payload)
    }

    private func get<T: Decodable>(_ path: String, params: [URLQueryItem] = []) async throws -> T {
        var request = try authorizedRequest(path: path, params: params)
        request.httpMethod = "GET"
        return try await requestEnvelope(request)
    }

    private func post<T: Decodable, P: Encodable>(_ path: String, payload: P) async throws -> T {
        var request = try authorizedRequest(path: path)
        request.httpMethod = "POST"
        request.setValue("application/json; charset=utf-8", forHTTPHeaderField: "Content-Type")
        request.httpBody = try encoder.encode(payload)
        return try await requestEnvelope(request)
    }

    private func patch<T: Decodable, P: Encodable>(_ path: String, payload: P) async throws -> T {
        var request = try authorizedRequest(path: path)
        request.httpMethod = "PATCH"
        request.setValue("application/json; charset=utf-8", forHTTPHeaderField: "Content-Type")
        request.httpBody = try encoder.encode(payload)
        return try await requestEnvelope(request)
    }

    private func put<T: Decodable, P: Encodable>(_ path: String, payload: P) async throws -> T {
        var request = try authorizedRequest(path: path)
        request.httpMethod = "PUT"
        request.setValue("application/json; charset=utf-8", forHTTPHeaderField: "Content-Type")
        request.httpBody = try encoder.encode(payload)
        return try await requestEnvelope(request)
    }

    private func delete<T: Decodable>(_ path: String) async throws -> T {
        var request = try authorizedRequest(path: path)
        request.httpMethod = "DELETE"
        return try await requestEnvelope(request)
    }

    private func requestEnvelope<T: Decodable>(_ request: URLRequest) async throws -> T {
        let (data, response) = try await session.data(for: request)
        try validate(response: response, data: data)
        if let rawResult = try? decoder.decode(T.self, from: data) {
            return rawResult
        }
        let envelope = try decoder.decode(APIEnvelope<T>.self, from: data)
        guard envelope.ok, let result = envelope.result else {
            throw APIError(message: envelope.error ?? "Request failed", code: envelope.errorCode, statusCode: (response as? HTTPURLResponse)?.statusCode)
        }
        return result
    }

    private func validate(response: URLResponse, data: Data = Data()) throws {
        guard let response = response as? HTTPURLResponse else {
            throw APIError(message: "Invalid response", code: nil, statusCode: nil)
        }

        guard (200 ... 299).contains(response.statusCode) else {
            let apiError: APIEnvelope<EmptyResult>? = try? decoder.decode(APIEnvelope<EmptyResult>.self, from: data)
            throw APIError(
                message: apiError?.error ?? "HTTP \(response.statusCode)",
                code: apiError?.errorCode,
                statusCode: response.statusCode
            )
        }
    }

    private func authorizedRequest(path: String, params: [URLQueryItem] = []) throws -> URLRequest {
        guard var components = URLComponents(string: baseURL) else {
            throw APIError(message: "Invalid backend URL", code: nil, statusCode: nil)
        }

        let basePath = components.path.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        let extraPath = path.trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        components.path = "/" + [basePath, extraPath].filter { !$0.isEmpty }.joined(separator: "/")
        if !params.isEmpty {
            components.queryItems = params.filter { $0.value != nil && $0.value?.isEmpty == false }
        }

        guard let url = components.url else {
            throw APIError(message: "Invalid backend URL", code: nil, statusCode: nil)
        }

        var request = URLRequest(url: url)
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        if let bearerToken, !bearerToken.isEmpty {
            request.setValue("Bearer \(bearerToken)", forHTTPHeaderField: "Authorization")
        }
        request.timeoutInterval = 120
        return request
    }

    private func multipartData(boundary: String, parts: [MultipartPart]) -> Data {
        var data = Data()
        for part in parts {
            data.append("--\(boundary)\r\n".data(using: .utf8)!)
            switch part {
            case .text(let name, let value):
                data.append("Content-Disposition: form-data; name=\"\(name)\"\r\n\r\n".data(using: .utf8)!)
                data.append("\(value)\r\n".data(using: .utf8)!)
            case .json(let name, let jsonData):
                data.append("Content-Disposition: form-data; name=\"\(name)\"\r\n".data(using: .utf8)!)
                data.append("Content-Type: application/json; charset=utf-8\r\n\r\n".data(using: .utf8)!)
                data.append(jsonData)
                data.append("\r\n".data(using: .utf8)!)
            case .file(let name, let filename, let mimeType, let fileData):
                data.append("Content-Disposition: form-data; name=\"\(name)\"; filename=\"\(filename)\"\r\n".data(using: .utf8)!)
                data.append("Content-Type: \(mimeType)\r\n\r\n".data(using: .utf8)!)
                data.append(fileData)
                data.append("\r\n".data(using: .utf8)!)
            }
        }
        data.append("--\(boundary)--\r\n".data(using: .utf8)!)
        return data
    }
}

private enum MultipartPart {
    case text(name: String, value: String)
    case json(name: String, data: Data)
    case file(name: String, filename: String, mimeType: String, data: Data)
}

private struct EmptyResult: Decodable {}
