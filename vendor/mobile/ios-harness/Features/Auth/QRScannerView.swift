import AVFoundation
import SwiftUI
import UIKit

struct QRScannerView: View {
    @Environment(\.dismiss) private var dismiss
    @EnvironmentObject private var store: HarnessStore

    let onScan: (String) -> Void

    @State private var permissionState = CameraPermissionState.checking

    var body: some View {
        NavigationStack {
            ZStack {
                HarnessColors.background
                    .ignoresSafeArea()

                switch permissionState {
                case .checking:
                    ProgressView()
                        .controlSize(.large)
                case .authorized:
                    QRMetadataScannerView { value in
                        onScan(value)
                    }
                    .ignoresSafeArea(edges: .bottom)
                    scannerOverlay
                case .denied:
                    permissionDeniedView
                case .unavailable:
                    unavailableView
                }
            }
            .navigationTitle(store.t("mobile.login.scanQR"))
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button(store.t("common.cancel")) {
                        dismiss()
                    }
                }
            }
            .task {
                await requestCameraAccess()
            }
        }
    }

    private var scannerOverlay: some View {
        VStack(spacing: 16) {
            Spacer()

            RoundedRectangle(cornerRadius: 18, style: .continuous)
                .strokeBorder(Color.white.opacity(0.86), lineWidth: 3)
                .frame(width: 240, height: 240)
                .shadow(radius: 12)
                .accessibilityHidden(true)

            Text(store.t("mobile.login.scanHint"))
                .font(.subheadline.weight(.semibold))
                .multilineTextAlignment(.center)
                .foregroundStyle(.white)
                .padding(.horizontal, 18)
                .padding(.vertical, 12)
                .background(.black.opacity(0.58), in: Capsule())
                .padding(.horizontal, 20)

            Spacer()
        }
    }

    private var permissionDeniedView: some View {
        VStack(alignment: .leading, spacing: 16) {
            Image(systemName: "camera.fill")
                .font(.system(size: 34, weight: .semibold))
                .foregroundStyle(HarnessColors.warning)

            Text(store.t("mobile.login.cameraDenied.title"))
                .font(.title3.weight(.semibold))
                .foregroundStyle(HarnessColors.text)

            Text(store.t("mobile.login.cameraDenied.body"))
                .font(.body)
                .foregroundStyle(HarnessColors.textMuted)

            Button(store.t("mobile.login.openSettings")) {
                guard let settingsURL = URL(string: UIApplication.openSettingsURLString) else { return }
                UIApplication.shared.open(settingsURL)
            }
            .buttonStyle(.borderedProminent)
            .tint(HarnessColors.primary)

            Button(store.t("mobile.login.manualFallback")) {
                dismiss()
            }
            .buttonStyle(.bordered)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(20)
        .harnessGlassSurface(cornerRadius: 16)
        .padding(20)
    }

    private var unavailableView: some View {
        VStack(alignment: .leading, spacing: 16) {
            Image(systemName: "camera.slash.fill")
                .font(.system(size: 34, weight: .semibold))
                .foregroundStyle(HarnessColors.warning)

            Text(store.t("mobile.login.cameraUnavailable.title"))
                .font(.title3.weight(.semibold))
                .foregroundStyle(HarnessColors.text)

            Text(store.t("mobile.login.cameraUnavailable.body"))
                .font(.body)
                .foregroundStyle(HarnessColors.textMuted)

            Button(store.t("mobile.login.manualFallback")) {
                dismiss()
            }
            .buttonStyle(.borderedProminent)
            .tint(HarnessColors.primary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(20)
        .harnessGlassSurface(cornerRadius: 16)
        .padding(20)
    }

    @MainActor
    private func requestCameraAccess() async {
        guard UIImagePickerController.isSourceTypeAvailable(.camera) else {
            permissionState = .unavailable
            return
        }

        switch AVCaptureDevice.authorizationStatus(for: .video) {
        case .authorized:
            permissionState = .authorized
        case .notDetermined:
            let granted = await AVCaptureDevice.requestAccess(for: .video)
            permissionState = granted ? .authorized : .denied
        case .denied, .restricted:
            permissionState = .denied
        @unknown default:
            permissionState = .denied
        }
    }
}

private enum CameraPermissionState {
    case checking
    case authorized
    case denied
    case unavailable
}

private struct QRMetadataScannerView: UIViewControllerRepresentable {
    let onScan: (String) -> Void

    func makeUIViewController(context: Context) -> QRMetadataScannerViewController {
        QRMetadataScannerViewController(onScan: onScan)
    }

    func updateUIViewController(_ uiViewController: QRMetadataScannerViewController, context: Context) {}
}

private final class QRMetadataScannerViewController: UIViewController, AVCaptureMetadataOutputObjectsDelegate {
    private let onScan: (String) -> Void
    private let session = AVCaptureSession()
    private var previewLayer: AVCaptureVideoPreviewLayer?
    private var hasScanned = false

    init(onScan: @escaping (String) -> Void) {
        self.onScan = onScan
        super.init(nibName: nil, bundle: nil)
    }

    @available(*, unavailable)
    required init?(coder: NSCoder) {
        fatalError("init(coder:) has not been implemented")
    }

    override func viewDidLoad() {
        super.viewDidLoad()
        view.backgroundColor = .black
        configureCaptureSession()
    }

    override func viewDidLayoutSubviews() {
        super.viewDidLayoutSubviews()
        previewLayer?.frame = view.bounds
    }

    override func viewWillAppear(_ animated: Bool) {
        super.viewWillAppear(animated)
        hasScanned = false
        startSession()
    }

    override func viewWillDisappear(_ animated: Bool) {
        super.viewWillDisappear(animated)
        stopSession()
    }

    private func configureCaptureSession() {
        guard let captureDevice = AVCaptureDevice.default(for: .video),
              let input = try? AVCaptureDeviceInput(device: captureDevice),
              session.canAddInput(input) else {
            return
        }

        session.addInput(input)

        let output = AVCaptureMetadataOutput()
        guard session.canAddOutput(output) else { return }
        session.addOutput(output)
        output.setMetadataObjectsDelegate(self, queue: .main)
        output.metadataObjectTypes = [.qr]

        let layer = AVCaptureVideoPreviewLayer(session: session)
        layer.videoGravity = .resizeAspectFill
        layer.frame = view.bounds
        view.layer.insertSublayer(layer, at: 0)
        previewLayer = layer
    }

    private func startSession() {
        guard !session.isRunning else { return }
        DispatchQueue.global(qos: .userInitiated).async { [session] in
            session.startRunning()
        }
    }

    private func stopSession() {
        guard session.isRunning else { return }
        DispatchQueue.global(qos: .userInitiated).async { [session] in
            session.stopRunning()
        }
    }

    func metadataOutput(
        _ output: AVCaptureMetadataOutput,
        didOutput metadataObjects: [AVMetadataObject],
        from connection: AVCaptureConnection
    ) {
        guard !hasScanned,
              let codeObject = metadataObjects.compactMap({ $0 as? AVMetadataMachineReadableCodeObject }).first,
              codeObject.type == .qr,
              let value = codeObject.stringValue,
              !value.isEmpty else {
            return
        }

        hasScanned = true
        stopSession()
        UIImpactFeedbackGenerator(style: .light).impactOccurred()
        onScan(value)
    }
}
