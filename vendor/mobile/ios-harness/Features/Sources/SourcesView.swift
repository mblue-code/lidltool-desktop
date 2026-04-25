import SwiftUI

struct SourcesView: View {
    @EnvironmentObject private var store: HarnessStore

    var body: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 16) {
                SectionHeader(
                    eyebrow: store.t("mobile.sync.eyebrow"),
                    title: store.t("mobile.sync.title"),
                    description: store.t("mobile.sync.description")
                ) {
                    Button(store.state.syncBusy ? store.t("mobile.action.syncing") : store.t("mobile.action.syncNow")) {
                        Task { await store.syncNow() }
                    }
                    .buttonStyle(.borderedProminent)
                    .tint(HarnessColors.primary)
                    .disabled(store.state.syncBusy)
                }

                VStack(spacing: 0) {
                    MetricRow(label: store.t("mobile.sync.desktop"), value: store.state.local.pairedDesktop?.desktopName ?? store.t("mobile.common.notPaired"))
                    SectionDivider()
                    MetricRow(label: store.t("mobile.sync.endpoint"), value: store.state.local.pairedDesktop.map { browserURL(from: $0.endpointURL) } ?? store.t("common.na"))
                    SectionDivider()
                    MetricRow(label: store.t("mobile.sync.cursor"), value: store.state.local.sync.cursor ?? store.t("mobile.common.none"))
                    SectionDivider()
                    MetricRow(label: store.t("mobile.highlights.lastSync"), value: formatTimestamp(store.state.local.sync.lastSyncAt, fallback: store.t("mobile.common.never")))
                    SectionDivider()
                    MetricRow(label: store.t("mobile.sync.serverTime"), value: formatTimestamp(store.state.local.sync.serverTime, fallback: store.t("common.na")))
                }
                .padding(12)
                .harnessGlassSurface(cornerRadius: 16)

                if let error = store.state.local.sync.lastError, !error.isEmpty {
                    InfoBannerCard(
                        title: store.t("mobile.sync.lastError"),
                        bodyText: error,
                        tint: HarnessColors.warningTint
                    )
                }

                InfoBannerCard(
                    title: store.t("mobile.sync.protocol.title"),
                    bodyText: store.t("mobile.sync.protocol.body"),
                    tint: HarnessColors.surfaceStrong
                )
            }
            .padding(16)
        }
        .background(Color.clear)
    }
}
