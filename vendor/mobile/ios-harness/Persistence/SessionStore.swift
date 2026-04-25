import Foundation

struct MobileLocalState: Codable, Equatable {
    var pairedDesktop: PairedDesktop?
    var syncTokenFallback: String?
    var sync = SyncMetadata()
    var captures: [CaptureQueueItem] = []
    var transactions: [MobileTransaction] = []
    var transactionItems: [MobileTransactionItem] = []
    var budgetSummary: BudgetSummary?
}

final class SessionStore {
    private enum Keys {
        static let syncToken = "mobile.syncToken"
        static let deviceId = "mobile.deviceId"
        static let language = "mobile.language"
    }

    private let keychain: KeychainStore
    private let encoder: JSONEncoder
    private let decoder: JSONDecoder
    private let stateURL: URL
    private let capturesDirectoryURL: URL

    init(keychain: KeychainStore = KeychainStore()) {
        self.keychain = keychain
        self.encoder = JSONEncoder()
        self.encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        self.decoder = JSONDecoder()

        let supportDirectory = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("LidlToolHarness", isDirectory: true)
        self.stateURL = supportDirectory.appendingPathComponent("mobile-state.json")
        self.capturesDirectoryURL = supportDirectory.appendingPathComponent("captures", isDirectory: true)

        try? FileManager.default.createDirectory(at: capturesDirectoryURL, withIntermediateDirectories: true)
    }

    var syncToken: String? {
        get { keychain.get(Keys.syncToken) }
        set {
            if let newValue, !newValue.isEmpty {
                keychain.set(newValue, for: Keys.syncToken)
            } else {
                keychain.delete(Keys.syncToken)
            }
        }
    }

    var deviceId: String {
        if let value = keychain.get(Keys.deviceId), !value.isEmpty {
            return value
        }
        let value = UUID().uuidString
        keychain.set(value, for: Keys.deviceId)
        return value
    }

    var language: AppLanguage {
        get {
            AppLanguage(rawValue: UserDefaults.standard.string(forKey: Keys.language) ?? "") ?? .english
        }
        set {
            UserDefaults.standard.set(newValue.rawValue, forKey: Keys.language)
        }
    }

    func load() -> MobileLocalState {
        guard let data = try? Data(contentsOf: stateURL) else {
            return MobileLocalState()
        }
        return (try? decoder.decode(MobileLocalState.self, from: data)) ?? MobileLocalState()
    }

    func save(_ state: MobileLocalState) {
        do {
            try FileManager.default.createDirectory(at: stateURL.deletingLastPathComponent(), withIntermediateDirectories: true)
            let data = try encoder.encode(state)
            try data.write(to: stateURL, options: [.atomic])
        } catch {
            assertionFailure("Failed to persist mobile state: \(error.localizedDescription)")
        }
    }

    func importCapture(from sourceURL: URL) throws -> CaptureQueueItem {
        let didAccess = sourceURL.startAccessingSecurityScopedResource()
        defer {
            if didAccess {
                sourceURL.stopAccessingSecurityScopedResource()
            }
        }

        let id = UUID().uuidString
        let fileName = sourceURL.lastPathComponent.isEmpty ? "\(id).receipt" : sourceURL.lastPathComponent
        let destinationURL = capturesDirectoryURL.appendingPathComponent("\(id)-\(fileName)")

        if FileManager.default.fileExists(atPath: destinationURL.path) {
            try FileManager.default.removeItem(at: destinationURL)
        }
        try FileManager.default.copyItem(at: sourceURL, to: destinationURL)

        let attributes = try FileManager.default.attributesOfItem(atPath: destinationURL.path)
        let byteCount = (attributes[.size] as? NSNumber)?.intValue ?? 0

        return CaptureQueueItem(
            id: id,
            fileName: fileName,
            localPath: destinationURL.path,
            mimeType: mimeType(for: destinationURL),
            byteCount: byteCount,
            capturedAt: ISO8601DateFormatter().string(from: Date()),
            state: .queuedForUpload,
            desktopCaptureId: nil,
            statusMessage: nil
        )
    }

    func importCapture(data: Data, suggestedFileName: String, mimeType: String) throws -> CaptureQueueItem {
        let id = UUID().uuidString
        let safeFileName = suggestedFileName.isEmpty ? "\(id).jpg" : suggestedFileName
        let destinationURL = capturesDirectoryURL.appendingPathComponent("\(id)-\(safeFileName)")

        if FileManager.default.fileExists(atPath: destinationURL.path) {
            try FileManager.default.removeItem(at: destinationURL)
        }
        try data.write(to: destinationURL, options: [.atomic])

        return CaptureQueueItem(
            id: id,
            fileName: safeFileName,
            localPath: destinationURL.path,
            mimeType: mimeType,
            byteCount: data.count,
            capturedAt: ISO8601DateFormatter().string(from: Date()),
            state: .queuedForUpload,
            desktopCaptureId: nil,
            statusMessage: nil
        )
    }

    func captureFileURL(for item: CaptureQueueItem) -> URL {
        URL(fileURLWithPath: item.localPath)
    }

    func clear() {
        syncToken = nil
        save(MobileLocalState())
    }

    private func mimeType(for url: URL) -> String {
        switch url.pathExtension.lowercased() {
        case "jpg", "jpeg":
            return "image/jpeg"
        case "png":
            return "image/png"
        case "heic":
            return "image/heic"
        case "pdf":
            return "application/pdf"
        default:
            return "application/octet-stream"
        }
    }
}
