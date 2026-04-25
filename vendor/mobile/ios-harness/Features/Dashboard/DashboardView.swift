import SwiftUI

struct DashboardView: View {
    @EnvironmentObject private var store: HarnessStore

    private var budget: BudgetSummary? {
        store.state.local.budgetSummary
    }

    private var transactions: [MobileTransaction] {
        store.state.local.transactions
    }

    private var currency: String {
        budget?.currency ?? transactions.first?.currency ?? "EUR"
    }

    private var spentCents: Int {
        budget?.spentCents ?? transactions.reduce(0) { $0 + $1.totalCents }
    }

    private var budgetCents: Int {
        budget?.budgetCents ?? 0
    }

    private var topMerchant: (String, Int)? {
        Dictionary(grouping: transactions, by: { $0.merchantName.isEmpty ? store.t("mobile.common.unknownMerchant") : $0.merchantName })
            .mapValues { $0.reduce(0) { $0 + $1.totalCents } }
            .sorted { $0.value > $1.value }
            .first
            .map { ($0.key, $0.value) }
    }

    var body: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 16) {
                SectionHeader(
                    eyebrow: store.t("mobile.tab.overview"),
                    title: store.t("mobile.overview.title"),
                    description: store.t("mobile.overview.description")
                ) {
                    Button {
                        Task { await store.syncNow() }
                    } label: {
                        Label(store.state.syncBusy ? store.t("mobile.action.syncing") : store.t("mobile.action.syncNow"), systemImage: "arrow.clockwise")
                            .labelStyle(.titleAndIcon)
                    }
                    .buttonStyle(.borderedProminent)
                    .tint(HarnessColors.primary)
                    .disabled(store.state.syncBusy)
                }

                VStack(alignment: .leading, spacing: 12) {
                    ViewThatFits(in: .horizontal) {
                        HStack(alignment: .firstTextBaseline) {
                            periodSummary
                            Spacer()
                            transactionCount
                        }
                        VStack(alignment: .leading, spacing: 8) {
                            periodSummary
                            transactionCount
                        }
                    }

                    ProgressView(value: progressValue)
                        .tint(spentCents > budgetCents && budgetCents > 0 ? HarnessColors.warning : HarnessColors.primary)

                    HStack(spacing: 0) {
                        MetricCard(
                            title: store.t("mobile.metric.remaining"),
                            value: moneyText(amountCents: max(0, budgetCents - spentCents), currency: currency),
                            supporting: budgetCents > 0 ? store.t("mobile.metric.availableBudget") : store.t("mobile.metric.noBudget"),
                            tone: spentCents > budgetCents && budgetCents > 0 ? .warning : .positive
                        )
                        Divider().opacity(0.4).frame(height: 56)
                        MetricCard(
                            title: store.t("mobile.metric.transactions"),
                            value: String(transactions.count),
                            supporting: store.t("mobile.metric.storedLocally"),
                            tone: .info
                        )
                    }
                }
                .padding(14)
                .harnessGlassSurface(cornerRadius: 14, elevated: true)

                SectionHeader(title: store.t("mobile.capture.title"))
                VStack(spacing: 0) {
                    MetricRow(label: store.t("mobile.metric.queued"), value: String(store.state.local.captures.filter { $0.state == .queuedForUpload || $0.state == .localOnly }.count))
                    SectionDivider()
                    MetricRow(label: store.t("mobile.status.needsReview"), value: String(store.state.local.captures.filter { $0.state == .needsReview }.count))
                    SectionDivider()
                    MetricRow(label: store.t("mobile.status.completed"), value: String(store.state.local.captures.filter { $0.state == .completed }.count))
                }
                .padding(12)
                .harnessGlassSurface(cornerRadius: 14)

                SectionHeader(title: store.t("mobile.highlights.title"))
                VStack(spacing: 0) {
                    MetricRow(label: store.t("mobile.highlights.topMerchant"), value: topMerchant.map { "\($0.0) · \(moneyText(amountCents: $0.1, currency: currency))" } ?? store.t("mobile.common.notEnoughData"))
                    SectionDivider()
                    MetricRow(label: store.t("mobile.highlights.lastSync"), value: store.state.local.sync.lastSyncAt.map { formatTimestamp($0, fallback: $0) } ?? store.t("mobile.common.notSyncedYet"))
                    SectionDivider()
                    MetricRow(label: store.t("mobile.highlights.receiptMedia"), value: String(format: store.t("mobile.highlights.localArtifacts"), store.state.local.captures.count))
                }
                .padding(12)
                .harnessGlassSurface(cornerRadius: 14)

                SectionHeader(title: store.t("mobile.recentTransactions.title"))
                if transactions.isEmpty {
                    EmptyStateCard(
                        title: store.t("mobile.empty.transactions.title"),
                        description: store.t("mobile.empty.transactions.body")
                    )
                    .harnessGlassSurface(cornerRadius: 14)
                } else {
                    VStack(spacing: 0) {
                        ForEach(Array(transactions.prefix(5).enumerated()), id: \.element.id) { index, transaction in
                            if index > 0 { SectionDivider() }
                            SummaryCard(
                                title: transaction.merchantName,
                                subtitle: formatTimestamp(transaction.purchasedAt, fallback: transaction.purchasedAt),
                                trailing: moneyText(amountCents: transaction.totalCents, currency: transaction.currency),
                                actionTitle: nil,
                                action: nil
                            )
                        }
                    }
                    .harnessGlassSurface(cornerRadius: 14)
                }
            }
            .padding(16)
        }
        .background(Color.clear)
    }

    private var periodSummary: some View {
                        VStack(alignment: .leading, spacing: 4) {
                            EyebrowLabel(text: budget?.period ?? store.t("mobile.overview.syncedSpend"))
                            Text(displaySpent)
                                .font(.title.weight(.bold))
                                .foregroundStyle(HarnessColors.text)
                                .monospacedDigit()
                                .lineLimit(2)
                                .minimumScaleFactor(0.75)
                        }
    }

    private var transactionCount: some View {
        VStack(alignment: .trailing, spacing: 2) {
            Text(String(transactions.count))
                .font(.title2.weight(.semibold))
                .foregroundStyle(HarnessColors.primary)
                .monospacedDigit()
            Text(store.t("mobile.metric.transactionsLower"))
                .font(.caption)
                .foregroundStyle(HarnessColors.textMuted)
        }
    }

    private var displaySpent: String {
        if budgetCents > 0 {
            return String(format: store.t("mobile.overview.of"), moneyText(amountCents: spentCents, currency: currency), moneyText(amountCents: budgetCents, currency: currency))
        }
        return moneyText(amountCents: spentCents, currency: currency)
    }

    private var progressValue: Double {
        guard budgetCents > 0 else { return 0 }
        return min(1, Double(spentCents) / Double(budgetCents))
    }
}
