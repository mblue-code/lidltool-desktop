import SwiftUI

struct AnalysisView: View {
    @EnvironmentObject private var store: HarnessStore

    private var transactions: [MobileTransaction] {
        store.state.local.transactions
    }

    private var items: [MobileTransactionItem] {
        store.state.local.transactionItems
    }

    private var currency: String {
        store.state.local.budgetSummary?.currency ?? transactions.first?.currency ?? "EUR"
    }

    private var totalCents: Int {
        transactions.reduce(0) { $0 + $1.totalCents }
    }

    private var averageCents: Int {
        transactions.isEmpty ? 0 : totalCents / transactions.count
    }

    private var categoryRows: [AnalysisRow] {
        let transactionRows = Dictionary(grouping: transactions, by: { normalizedLabel($0.category, fallback: store.t("mobile.common.uncategorized")) })
            .mapValues { $0.reduce(0) { $0 + $1.totalCents } }
        let itemRows = Dictionary(grouping: items, by: { normalizedLabel($0.category, fallback: store.t("mobile.common.uncategorized")) })
            .mapValues { $0.reduce(0) { $0 + $1.lineTotalCents } }
        let source = itemRows.isEmpty ? transactionRows : itemRows
        return source
            .map { AnalysisRow(label: $0.key, cents: $0.value) }
            .sorted { $0.cents > $1.cents }
    }

    private var merchantRows: [AnalysisRow] {
        Dictionary(grouping: transactions, by: { $0.merchantName.isEmpty ? store.t("mobile.common.unknownMerchant") : $0.merchantName })
            .mapValues { $0.reduce(0) { $0 + $1.totalCents } }
            .map { AnalysisRow(label: $0.key, cents: $0.value) }
            .sorted { $0.cents > $1.cents }
    }

    private var monthRows: [AnalysisRow] {
        Dictionary(grouping: transactions, by: { monthKey(from: $0.purchasedAt) })
            .mapValues { $0.reduce(0) { $0 + $1.totalCents } }
            .map { AnalysisRow(label: $0.key, cents: $0.value) }
            .sorted { $0.label > $1.label }
    }

    var body: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 16) {
                SectionHeader(
                    eyebrow: store.t("mobile.tab.analysis"),
                    title: store.t("mobile.analysis.title"),
                    description: store.t("mobile.analysis.description")
                )

                if transactions.isEmpty {
                    EmptyStateCard(
                        title: store.t("mobile.analysis.empty.title"),
                        description: store.t("mobile.analysis.empty.body")
                    )
                    .harnessGlassSurface(cornerRadius: 14)
                } else {
                    ViewThatFits(in: .horizontal) {
                        HStack(spacing: 0) {
                            totalMetric
                            Divider().opacity(0.4).frame(height: 56)
                            averageMetric
                        }
                        VStack(spacing: 0) {
                            totalMetric
                            SectionDivider()
                            averageMetric
                        }
                    }
                    .harnessGlassSurface(cornerRadius: 14)

                    AnalysisRankedCard(
                        title: store.t("mobile.analysis.topCategories"),
                        rows: Array(categoryRows.prefix(6)),
                        totalCents: max(1, categoryRows.reduce(0) { $0 + $1.cents }),
                        currency: currency,
                        emptyText: store.t("mobile.common.notEnoughData")
                    )

                    AnalysisRankedCard(
                        title: store.t("mobile.analysis.topMerchants"),
                        rows: Array(merchantRows.prefix(6)),
                        totalCents: max(1, totalCents),
                        currency: currency,
                        emptyText: store.t("mobile.common.notEnoughData")
                    )

                    AnalysisRankedCard(
                        title: store.t("mobile.analysis.monthlyTrend"),
                        rows: Array(monthRows.prefix(6)),
                        totalCents: max(1, totalCents),
                        currency: currency,
                        emptyText: store.t("mobile.common.notEnoughData")
                    )

                    InfoBannerCard(
                        title: store.t("mobile.analysis.localOnly.title"),
                        bodyText: store.t("mobile.analysis.localOnly.body"),
                        tint: HarnessColors.infoTint
                    )
                }
            }
            .padding(16)
        }
        .background(Color.clear)
    }

    private var totalMetric: some View {
        MetricCard(
            title: store.t("mobile.metric.total"),
            value: moneyText(amountCents: totalCents, currency: currency),
            supporting: store.t("mobile.metric.syncedSpend"),
            tone: .neutral
        )
    }

    private var averageMetric: some View {
        MetricCard(
            title: store.t("mobile.metric.average"),
            value: moneyText(amountCents: averageCents, currency: currency),
            supporting: store.t("mobile.metric.perTransaction"),
            tone: .info
        )
    }

    private func monthKey(from raw: String) -> String {
        let value = String(raw.prefix(7))
        return value.isEmpty ? store.t("common.unknown") : value
    }

    private func normalizedLabel(_ raw: String?, fallback: String) -> String {
        let value = raw?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        return value.isEmpty ? fallback : value
    }
}

private struct AnalysisRow: Identifiable {
    var id: String { label }
    let label: String
    let cents: Int
}

private struct AnalysisRankedCard: View {
    let title: String
    let rows: [AnalysisRow]
    let totalCents: Int
    let currency: String
    let emptyText: String

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text(title)
                .font(.headline)
                .foregroundStyle(HarnessColors.text)

            if rows.isEmpty {
                Text(emptyText)
                    .font(.subheadline)
                    .foregroundStyle(HarnessColors.textMuted)
            } else {
                ForEach(rows) { row in
                    VStack(alignment: .leading, spacing: 5) {
                        HStack(alignment: .firstTextBaseline, spacing: 12) {
                            Text(row.label)
                                .font(.subheadline.weight(.semibold))
                                .foregroundStyle(HarnessColors.text)
                                .lineLimit(2)
                            Spacer()
                            Text(moneyText(amountCents: row.cents, currency: currency))
                                .font(.subheadline.weight(.semibold))
                                .foregroundStyle(HarnessColors.text)
                                .monospacedDigit()
                                .lineLimit(1)
                                .minimumScaleFactor(0.82)
                        }
                        ProgressView(value: min(1, Double(row.cents) / Double(totalCents)))
                            .tint(HarnessColors.primary)
                    }
                }
            }
        }
        .padding(14)
        .harnessGlassSurface(cornerRadius: 14)
    }
}
