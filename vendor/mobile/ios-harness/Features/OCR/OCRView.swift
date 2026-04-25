import SwiftUI
import PhotosUI
import UniformTypeIdentifiers
import UIKit

struct OCRView: View {
    @EnvironmentObject private var store: HarnessStore
    @State private var isImporting = false
    @State private var selectedPhoto: PhotosPickerItem?
    @State private var showingCamera = false

    var body: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 16) {
                SectionHeader(
                    eyebrow: store.t("mobile.capture.eyebrow"),
                    title: store.t("mobile.capture.title"),
                    description: store.t("mobile.capture.description")
                ) {
                    HStack(spacing: 8) {
                        Button(store.t("mobile.capture.camera")) {
                            showingCamera = true
                        }
                        .buttonStyle(.borderedProminent)
                        .tint(HarnessColors.primary)
                        .disabled(store.state.importBusy || !UIImagePickerController.isSourceTypeAvailable(.camera))

                        PhotosPicker(
                            selection: $selectedPhoto,
                            matching: .images,
                            photoLibrary: .shared()
                        ) {
                            Text(store.state.importBusy ? store.t("mobile.action.importing") : store.t("mobile.capture.photo"))
                        }
                        .buttonStyle(.bordered)
                        .disabled(store.state.importBusy)

                        Button(store.state.importBusy ? store.t("mobile.action.importing") : store.t("mobile.capture.file")) {
                            isImporting = true
                        }
                        .buttonStyle(.bordered)
                        .disabled(store.state.importBusy)
                    }
                }

                InfoBannerCard(
                    title: store.t("mobile.capture.ingestion.title"),
                    bodyText: store.t("mobile.capture.ingestion.body"),
                    tint: HarnessColors.infoTint
                )

                if store.state.local.captures.isEmpty {
                    EmptyStateCard(
                        title: store.t("mobile.capture.empty.title"),
                        description: store.t("mobile.capture.empty.body")
                    )
                    .harnessGlassSurface(cornerRadius: 16)
                } else {
                    VStack(spacing: 0) {
                        ForEach(Array(store.state.local.captures.enumerated()), id: \.element.id) { index, capture in
                            if index > 0 { SectionDivider() }
                            VStack(alignment: .leading, spacing: 8) {
                                HStack(alignment: .top) {
                                    VStack(alignment: .leading, spacing: 4) {
                                        Text(capture.fileName)
                                            .font(.headline)
                                        Text(formatTimestamp(capture.capturedAt, fallback: capture.capturedAt))
                                            .font(.subheadline)
                                            .foregroundStyle(HarnessColors.textMuted)
                                    }
                                    Spacer()
                                    Text(capture.state.localizedLabel)
                                        .font(.caption.weight(.semibold))
                                        .foregroundStyle(tone(for: capture.state))
                                        .padding(.vertical, 4)
                                        .padding(.horizontal, 8)
                                        .background(tone(for: capture.state).opacity(0.12))
                                        .clipShape(Capsule())
                                }

                                MetricRow(label: store.t("mobile.capture.type"), value: capture.mimeType)
                                MetricRow(label: store.t("mobile.capture.size"), value: ByteCountFormatter.string(fromByteCount: Int64(capture.byteCount), countStyle: .file))
                                if let status = capture.statusMessage, !status.isEmpty {
                                    Text(status)
                                        .font(.caption)
                                        .foregroundStyle(HarnessColors.textMuted)
                                }
                            }
                            .padding(12)
                        }
                    }
                    .harnessGlassSurface(cornerRadius: 16)
                }
            }
            .padding(16)
        }
        .background(Color.clear)
        .sheet(isPresented: $showingCamera) {
            CameraCaptureView { image in
                showingCamera = false
                guard let data = image.jpegData(compressionQuality: 0.86) else {
                    store.state.message = AppMessage(text: store.t("mobile.capture.cameraEncodeError"))
                    return
                }
                store.importPhotoCapture(data: data, suggestedFileName: "camera-capture.jpg", mimeType: "image/jpeg")
            } onCancel: {
                showingCamera = false
            }
        }
        .onChange(of: selectedPhoto) { _, item in
            guard let item else { return }
            Task {
                do {
                    if let data = try await item.loadTransferable(type: Data.self) {
                        await MainActor.run {
                            store.importPhotoCapture(data: data)
                            selectedPhoto = nil
                        }
                    }
                } catch {
                    await MainActor.run {
                        store.state.message = AppMessage(text: error.localizedDescription)
                        selectedPhoto = nil
                    }
                }
            }
        }
        .fileImporter(
            isPresented: $isImporting,
            allowedContentTypes: [.image, .pdf],
            allowsMultipleSelection: false
        ) { result in
            switch result {
            case .success(let urls):
                guard let url = urls.first else { return }
                store.importCapture(from: url)
            case .failure(let error):
                store.state.message = AppMessage(text: error.localizedDescription)
            }
        }
    }

    private func tone(for state: CaptureQueueState) -> Color {
        switch state {
        case .completed:
            return HarnessColors.success
        case .failed, .needsReview:
            return HarnessColors.warning
        case .uploaded, .processingOnDesktop:
            return HarnessColors.info
        case .localOnly, .queuedForUpload:
            return HarnessColors.textMuted
        }
    }
}

private struct CameraCaptureView: UIViewControllerRepresentable {
    let onImage: (UIImage) -> Void
    let onCancel: () -> Void

    func makeCoordinator() -> Coordinator {
        Coordinator(onImage: onImage, onCancel: onCancel)
    }

    func makeUIViewController(context: Context) -> UIImagePickerController {
        let picker = UIImagePickerController()
        picker.sourceType = .camera
        picker.cameraCaptureMode = .photo
        picker.delegate = context.coordinator
        return picker
    }

    func updateUIViewController(_ uiViewController: UIImagePickerController, context: Context) {}

    final class Coordinator: NSObject, UINavigationControllerDelegate, UIImagePickerControllerDelegate {
        let onImage: (UIImage) -> Void
        let onCancel: () -> Void

        init(onImage: @escaping (UIImage) -> Void, onCancel: @escaping () -> Void) {
            self.onImage = onImage
            self.onCancel = onCancel
        }

        func imagePickerController(
            _ picker: UIImagePickerController,
            didFinishPickingMediaWithInfo info: [UIImagePickerController.InfoKey: Any]
        ) {
            if let image = info[.originalImage] as? UIImage {
                onImage(image)
            } else {
                onCancel()
            }
        }

        func imagePickerControllerDidCancel(_ picker: UIImagePickerController) {
            onCancel()
        }
    }
}
