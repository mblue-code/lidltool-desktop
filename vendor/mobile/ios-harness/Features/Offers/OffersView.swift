import SwiftUI

struct OffersView: View {
    @EnvironmentObject private var store: HarnessStore

    var body: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 16) {
                SectionHeader(
                    eyebrow: store.t("mobile.settings.eyebrow"),
                    title: store.t("mobile.settings.title"),
                    description: store.t("mobile.settings.description")
                )

                LanguageSelector()

                VStack(spacing: 0) {
                    MetricRow(label: store.t("mobile.settings.pairedDevice"), value: store.state.local.pairedDesktop?.pairedDeviceId ?? store.t("common.na"))
                    SectionDivider()
                    MetricRow(label: store.t("mobile.settings.desktopId"), value: store.state.local.pairedDesktop?.desktopId ?? store.t("common.na"))
                    SectionDivider()
                    MetricRow(label: store.t("mobile.settings.fingerprint"), value: store.state.local.pairedDesktop?.publicKeyFingerprint ?? store.t("common.na"))
                    SectionDivider()
                    MetricRow(label: store.t("mobile.metric.transactions"), value: String(store.state.local.transactions.count))
                    SectionDivider()
                    MetricRow(label: store.t("mobile.settings.captures"), value: String(store.state.local.captures.count))
                }
                .padding(12)
                .harnessGlassSurface(cornerRadius: 16)

                InfoBannerCard(
                    title: store.t("mobile.settings.persistence.title"),
                    bodyText: store.t("mobile.settings.persistence.body"),
                    tint: HarnessColors.infoTint
                )

                Button(role: .destructive) {
                    store.forgetPairing()
                } label: {
                    Text(store.t("mobile.settings.forget"))
                        .frame(maxWidth: .infinity)
                }
                .buttonStyle(.borderedProminent)
                .tint(HarnessColors.destructiveText)
            }
            .padding(16)
        }
        .background(Color.clear)
    }
}
