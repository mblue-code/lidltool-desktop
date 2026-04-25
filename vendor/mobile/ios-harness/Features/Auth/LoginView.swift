import SwiftUI

struct LoginView: View {
    @EnvironmentObject private var store: HarnessStore

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                LanguageSelector()

                EyebrowLabel(text: store.t("login.eyebrow"))

                Text(store.t("login.title"))
                    .font(.largeTitle.weight(.bold))
                    .foregroundStyle(HarnessColors.text)

                Text(store.t("mobile.login.subtitle"))
                    .font(.body)
                    .foregroundStyle(HarnessColors.textMuted)

                InfoBannerCard(
                    title: store.t("mobile.login.noCloud.title"),
                    bodyText: store.t("mobile.login.noCloud.body"),
                    tint: HarnessColors.warningTint
                )

                VStack(alignment: .leading, spacing: 12) {
                    EyebrowLabel(text: store.t("mobile.login.payload"))

                    TextEditor(text: Binding(
                        get: { store.state.pairingPayloadText },
                        set: { store.state.pairingPayloadText = $0 }
                    ))
                    .frame(minHeight: 180)
                    .textInputAutocapitalization(.never)
                    .autocorrectionDisabled()
                    .font(.system(.footnote, design: .monospaced))
                    .scrollContentBackground(.hidden)
                    .harnessInputStyle()

                    Button {
                        Task { await store.pairFromPayloadText(store.state.pairingPayloadText) }
                    } label: {
                        if store.state.pairingBusy {
                            ProgressView()
                                .frame(maxWidth: .infinity)
                        } else {
                            Text(store.t("mobile.login.pairPhone"))
                                .frame(maxWidth: .infinity)
                        }
                    }
                    .buttonStyle(.borderedProminent)
                    .tint(HarnessColors.primary)
                    .disabled(store.state.pairingBusy)
                }
                .padding(16)
                .harnessGlassSurface(cornerRadius: 16)
            }
            .padding(20)
        }
        .background(Color.clear)
    }
}
