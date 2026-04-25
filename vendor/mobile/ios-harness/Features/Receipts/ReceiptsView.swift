import SwiftUI

struct ReceiptsView: View {
    @EnvironmentObject private var store: HarnessStore

    var body: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 16) {
                SectionHeader(
                    eyebrow: store.t("mobile.transactions.eyebrow"),
                    title: store.t("mobile.tab.transactions"),
                    description: store.t("mobile.transactions.description")
                )

                VStack(alignment: .leading, spacing: 12) {
                    Text(store.t("mobile.manual.title"))
                        .font(.headline)
                        .foregroundStyle(HarnessColors.text)
                    TextField(store.t("mobile.manual.merchant"), text: Binding(
                        get: { store.state.manualMerchant },
                        set: { store.state.manualMerchant = $0 }
                    ))
                    .harnessInputStyle()
                    TextField(store.t("mobile.manual.amount"), text: Binding(
                        get: { store.state.manualAmount },
                        set: { store.state.manualAmount = $0 }
                    ))
                    .keyboardType(.decimalPad)
                    .harnessInputStyle()
                    TextField(store.t("mobile.manual.note"), text: Binding(
                        get: { store.state.manualNote },
                        set: { store.state.manualNote = $0 }
                    ))
                    .harnessInputStyle()
                    Button {
                        Task { await store.createManualExpense() }
                    } label: {
                        Text(store.state.manualBusy ? store.t("mobile.action.saving") : store.t("mobile.manual.save"))
                            .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.borderedProminent)
                    .tint(HarnessColors.primary)
                    .disabled(store.state.manualBusy)
                }
                .padding(16)
                .harnessGlassSurface(cornerRadius: 16)

                TextField(
                    store.t("mobile.transactions.search"),
                    text: Binding(
                        get: { store.state.transactionQuery },
                        set: { store.state.transactionQuery = $0 }
                    )
                )
                .harnessInputStyle()

                if store.state.filteredTransactions.isEmpty {
                    EmptyStateCard(
                        title: store.t("mobile.transactions.emptySearch.title"),
                        description: store.t("mobile.transactions.emptySearch.body")
                    )
                    .harnessGlassSurface(cornerRadius: 16)
                } else {
                    VStack(spacing: 0) {
                        ForEach(Array(store.state.filteredTransactions.enumerated()), id: \.element.id) { index, transaction in
                            if index > 0 { SectionDivider() }
                            VStack(alignment: .leading, spacing: 8) {
                                HStack(alignment: .top) {
                                    VStack(alignment: .leading, spacing: 4) {
                                        Text(transaction.merchantName)
                                            .font(.headline)
                                            .foregroundStyle(HarnessColors.text)
                                        Text(formatTimestamp(transaction.purchasedAt, fallback: transaction.purchasedAt))
                                            .font(.subheadline)
                                            .foregroundStyle(HarnessColors.textMuted)
                                    }
                                    Spacer()
                                    Text(moneyText(amountCents: transaction.totalCents, currency: transaction.currency))
                                        .font(.headline.weight(.semibold))
                                        .monospacedDigit()
                                }

                                if let category = transaction.category, !category.isEmpty {
                                    Text(category)
                                        .font(.caption.weight(.semibold))
                                        .foregroundStyle(HarnessColors.primary)
                                        .padding(.vertical, 3)
                                        .padding(.horizontal, 8)
                                        .background(HarnessColors.primary.opacity(0.10))
                                        .clipShape(Capsule())
                                }

                                let items = store.state.local.transactionItems.filter { $0.transactionId == transaction.id }
                                if !items.isEmpty {
                                    Text(items.prefix(3).map(\.name).joined(separator: ", "))
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
    }
}
