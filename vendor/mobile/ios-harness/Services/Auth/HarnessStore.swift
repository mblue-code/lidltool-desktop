import Foundation
import SwiftUI
#if os(iOS)
import UIKit
#endif

enum AppTab: String, CaseIterable, Hashable {
    case home
    case transactions
    case capture
    case analysis
    case sync
    case settings

    var title: String {
        switch self {
        case .home: return L10n.tr("mobile.tab.overview")
        case .transactions: return L10n.tr("mobile.tab.transactions")
        case .capture: return L10n.tr("mobile.tab.capture")
        case .analysis: return L10n.tr("mobile.tab.analysis")
        case .sync: return L10n.tr("mobile.tab.sync")
        case .settings: return L10n.tr("mobile.tab.settings")
        }
    }

    var systemImage: String {
        switch self {
        case .home: return "rectangle.grid.2x2"
        case .transactions: return "list.bullet.rectangle"
        case .capture: return "doc.badge.plus"
        case .analysis: return "chart.bar.xaxis"
        case .sync: return "arrow.triangle.2.circlepath"
        case .settings: return "gearshape"
        }
    }
}

enum AppLanguage: String, CaseIterable, Codable, Equatable {
    case english = "en"
    case german = "de"

    var label: String {
        switch self {
        case .english: return "English"
        case .german: return "Deutsch"
        }
    }
}

struct HarnessState {
    var local = MobileLocalState()
    var selectedTab: AppTab = .home
    var language: AppLanguage = .english
    var pairingPayloadText = ""
    var pairingBusy = false
    var syncBusy = false
    var importBusy = false
    var manualBusy = false
    var manualMerchant = ""
    var manualAmount = ""
    var manualNote = ""
    var transactionQuery = ""
    var message: AppMessage?

    var isPaired: Bool {
        local.pairedDesktop != nil
    }

    var filteredTransactions: [MobileTransaction] {
        let query = transactionQuery.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        guard !query.isEmpty else { return local.transactions }
        return local.transactions.filter { transaction in
            transaction.merchantName.lowercased().contains(query)
                || transaction.category?.lowercased().contains(query) == true
                || transaction.note?.lowercased().contains(query) == true
        }
    }
}

@MainActor
final class HarnessStore: ObservableObject {
    @Published var state: HarnessState

    private let sessionStore: SessionStore

    init(sessionStore: SessionStore = SessionStore()) {
        self.sessionStore = sessionStore
        self.state = HarnessState(local: sessionStore.load(), language: sessionStore.language)
        L10n.language = self.state.language
    }

    func clearMessage() {
        state.message = nil
    }

    func setLanguage(_ language: AppLanguage) {
        state.language = language
        sessionStore.language = language
        L10n.language = language
    }

    func t(_ key: String) -> String {
        L10n.tr(key, language: state.language)
    }

    func pairFromPayloadText(_ text: String) async {
        let trimmed = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty, let data = trimmed.data(using: .utf8) else {
            state.message = AppMessage(text: t("mobile.error.pairingPayload"))
            return
        }

        state.pairingBusy = true
        state.message = nil

        do {
            let decoder = JSONDecoder()
            let payload = try decoder.decode(MobilePairingPayload.self, from: data)
            guard payload.protocolVersion == 1 else {
                throw APIError(message: "Unsupported pairing protocol version \(payload.protocolVersion).", code: nil, statusCode: nil)
            }

            let request = MobileHandshakeRequest(
                deviceId: sessionStore.deviceId,
                deviceName: deviceName(),
                platform: "ios",
                pairingToken: payload.pairingToken,
                publicKeyFingerprint: payload.publicKeyFingerprint
            )
            let response = try await APIClient(baseURL: payload.endpointURL).mobileHandshake(request)

            state.local.pairedDesktop = PairedDesktop(
                pairedDeviceId: response.pairedDeviceId,
                desktopId: response.desktopId,
                desktopName: response.desktopName,
                endpointURL: response.endpointURL,
                publicKeyFingerprint: payload.publicKeyFingerprint,
                issuedAt: response.issuedAt,
                expiresAt: response.expiresAt
            )
            state.local.sync = SyncMetadata()
            state.local.syncTokenFallback = response.syncToken
            sessionStore.syncToken = response.syncToken
            persist()
            state.pairingPayloadText = ""
            state.selectedTab = .home
            state.message = AppMessage(text: String(format: t("mobile.message.paired"), response.desktopName))
            await syncNow()
        } catch {
            present(error, fallback: t("error.loginFailed"))
        }

        state.pairingBusy = false
    }

    func syncNow() async {
        guard let api = pairedAPI() else { return }
        state.syncBusy = true
        state.local.sync.lastError = nil

        do {
            for capture in state.local.captures where capture.state == .queuedForUpload || capture.state == .failed {
                try await uploadCapture(capture, api: api)
            }

            let changes = try await api.mobileSyncChanges(cursor: state.local.sync.cursor)
            state.local.sync.cursor = changes.cursor
            state.local.sync.serverTime = changes.serverTime
            state.local.sync.lastSyncAt = ISO8601DateFormatter().string(from: Date())
            apply(changes)
            persist()
        } catch {
            state.local.sync.lastError = (error as? LocalizedError)?.errorDescription ?? error.localizedDescription
            persist()
            present(error, fallback: t("mobile.error.syncFailed"))
        }

        state.syncBusy = false
    }

    func importCapture(from url: URL) {
        state.importBusy = true
        do {
            let item = try sessionStore.importCapture(from: url)
            state.local.captures.insert(item, at: 0)
            persist()
            state.message = AppMessage(text: t("mobile.message.receiptQueued"))
        } catch {
            present(error, fallback: t("mobile.error.importReceipt"))
        }
        state.importBusy = false
    }

    func importPhotoCapture(data: Data, suggestedFileName: String = "camera-capture.jpg", mimeType: String = "image/jpeg") {
        state.importBusy = true
        do {
            let item = try sessionStore.importCapture(
                data: data,
                suggestedFileName: suggestedFileName,
                mimeType: mimeType
            )
            state.local.captures.insert(item, at: 0)
            persist()
            state.message = AppMessage(text: t("mobile.message.photoQueued"))
        } catch {
            present(error, fallback: t("mobile.error.importPhoto"))
        }
        state.importBusy = false
    }

    func createManualExpense() async {
        guard let api = pairedAPI() else { return }
        let merchant = state.manualMerchant.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !merchant.isEmpty, let amountCents = amountCents(from: state.manualAmount) else {
            state.message = AppMessage(text: t("mobile.error.manualRequired"))
            return
        }
        state.manualBusy = true
        do {
            _ = try await api.createMobileManualTransaction(
                MobileManualTransactionRequest(
                    merchantName: merchant,
                    totalCents: amountCents,
                    currency: "EUR",
                    note: state.manualNote.trimmingCharacters(in: .whitespacesAndNewlines).nilIfEmpty,
                    idempotencyKey: "ios-\(sessionStore.deviceId)-\(Date().timeIntervalSince1970)"
                )
            )
            state.manualMerchant = ""
            state.manualAmount = ""
            state.manualNote = ""
            state.message = AppMessage(text: t("mobile.message.manualSaved"))
            await syncNow()
        } catch {
            present(error, fallback: t("mobile.error.manualFailed"))
        }
        state.manualBusy = false
    }

    func forgetPairing() {
        sessionStore.clear()
        let language = state.language
        state = HarnessState(language: language)
        L10n.language = language
    }

    private func uploadCapture(_ capture: CaptureQueueItem, api: APIClient) async throws {
        guard let index = state.local.captures.firstIndex(where: { $0.id == capture.id }) else { return }

        let metadata = CaptureUploadMetadata(
            captureId: capture.id,
            capturedAt: capture.capturedAt,
            fileName: capture.fileName,
            mimeType: capture.mimeType,
            byteCount: capture.byteCount
        )

        let response = try await api.uploadMobileCapture(
            fileURL: sessionStore.captureFileURL(for: capture),
            metadata: metadata
        )
        state.local.captures[index].desktopCaptureId = response.captureId
        state.local.captures[index].state = CaptureQueueState(rawValue: response.status) ?? .uploaded
        state.local.captures[index].statusMessage = response.message
        persist()
    }

    private func apply(_ changes: MobileSyncChangesResponse) {
        merge(changes.transactions, into: &state.local.transactions)
        merge(changes.transactionItems, into: &state.local.transactionItems)
        if let budgetSummary = changes.budgetSummary {
            state.local.budgetSummary = budgetSummary
        }

        for update in changes.captureStatuses {
            if let index = state.local.captures.firstIndex(where: { $0.id == update.captureId || $0.desktopCaptureId == update.captureId }) {
                state.local.captures[index].state = update.status
                state.local.captures[index].statusMessage = update.message
            }
        }
    }

    private func merge<T: Identifiable & Equatable>(_ incoming: [T], into existing: inout [T]) where T.ID == String {
        for item in incoming {
            if let index = existing.firstIndex(where: { $0.id == item.id }) {
                existing[index] = item
            } else {
                existing.append(item)
            }
        }
    }

    private func pairedAPI() -> APIClient? {
        let token = sessionStore.syncToken ?? state.local.syncTokenFallback
        guard let desktop = state.local.pairedDesktop, let token, !token.isEmpty else {
            state.message = AppMessage(text: "Pair this iPhone with LidlTool Desktop first.")
            return nil
        }
        return APIClient(baseURL: desktop.endpointURL, bearerToken: token)
    }

    private func persist() {
        sessionStore.save(state.local)
    }

    private func present(_ error: Error, fallback: String) {
        state.message = AppMessage(text: (error as? LocalizedError)?.errorDescription ?? fallback)
    }

    private func deviceName() -> String {
#if os(iOS)
        UIDevice.current.name
#else
        Host.current().localizedName ?? "Apple device"
#endif
    }

    private func amountCents(from raw: String) -> Int? {
        let normalized = raw.trimmingCharacters(in: .whitespacesAndNewlines).replacingOccurrences(of: ",", with: ".")
        guard let value = Decimal(string: normalized), value >= 0 else { return nil }
        return NSDecimalNumber(decimal: value * Decimal(100)).rounding(accordingToBehavior: nil).intValue
    }
}

private extension String {
    var nilIfEmpty: String? {
        isEmpty ? nil : self
    }
}
