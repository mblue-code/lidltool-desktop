import SwiftUI

struct AppMessage: Identifiable, Equatable {
    let id = UUID()
    let text: String
}

struct HarnessSceneBackground: View {
    @Environment(\.colorScheme) private var colorScheme

    var body: some View {
        ZStack {
            if colorScheme == .dark {
                Color(hex: 0x091018)

                LinearGradient(
                    colors: [
                        Color(hex: 0x10151D),
                        Color(hex: 0x0B1119),
                        Color(hex: 0x091018)
                    ],
                    startPoint: .topLeading,
                    endPoint: .bottomTrailing
                )

                RadialGradient(
                    colors: [
                        Color(hex: 0xF0C27D, opacity: 0.22),
                        .clear
                    ],
                    center: .topLeading,
                    startRadius: 0,
                    endRadius: 420
                )

                RadialGradient(
                    colors: [
                        Color(hex: 0x7FC5FF, opacity: 0.24),
                        .clear
                    ],
                    center: .topTrailing,
                    startRadius: 0,
                    endRadius: 460
                )

                LinearGradient(
                    colors: [
                        .clear,
                        Color.black.opacity(0.16)
                    ],
                    startPoint: .center,
                    endPoint: .bottom
                )
            } else {
                HarnessColors.background
            }
        }
        .ignoresSafeArea()
    }
}

private struct HarnessGlassSurface: ViewModifier {
    @Environment(\.colorScheme) private var colorScheme

    let cornerRadius: CGFloat
    let fill: Color
    let border: Color
    let elevated: Bool

    init(
        cornerRadius: CGFloat = 16,
        fill: Color = HarnessColors.card,
        border: Color = HarnessColors.border,
        elevated: Bool = false
    ) {
        self.cornerRadius = cornerRadius
        self.fill = fill
        self.border = border
        self.elevated = elevated
    }

    func body(content: Content) -> some View {
        let shape = RoundedRectangle(cornerRadius: cornerRadius, style: .continuous)

        content
            .background {
                if colorScheme == .dark {
                    shape
                        .fill(fill)
                        .overlay(
                            LinearGradient(
                                colors: [
                                    Color.white.opacity(elevated ? 0.09 : 0.06),
                                    Color.white.opacity(0.02),
                                    .clear
                                ],
                                startPoint: .topLeading,
                                endPoint: .bottomTrailing
                            )
                        )
                } else {
                    shape.fill(fill)
                }
            }
            .overlay(
                shape.stroke(border.opacity(colorScheme == .dark ? 0.95 : 1.0), lineWidth: 1)
            )
            .shadow(
                color: colorScheme == .dark ? .black.opacity(elevated ? 0.28 : 0.18) : .black.opacity(0.08),
                radius: elevated ? 14 : 8,
                y: elevated ? 10 : 6
            )
    }
}

extension View {
    func harnessGlassSurface(
        cornerRadius: CGFloat = 16,
        fill: Color = HarnessColors.card,
        border: Color = HarnessColors.border,
        elevated: Bool = false
    ) -> some View {
        modifier(HarnessGlassSurface(cornerRadius: cornerRadius, fill: fill, border: border, elevated: elevated))
    }
}

struct MessageBanner: View {
    let message: AppMessage
    let onDismiss: () -> Void

    var body: some View {
        HStack(spacing: 12) {
            Text(message.text)
                .font(.subheadline)
                .foregroundStyle(HarnessColors.text)
            Spacer()
            Button(L10n.close, action: onDismiss)
                .font(.subheadline.weight(.semibold))
        }
        .padding(14)
        .harnessGlassSurface(cornerRadius: 14, fill: HarnessColors.warningTint, border: HarnessColors.warning.opacity(0.4), elevated: true)
    }
}

struct EyebrowLabel: View {
    let text: String

    var body: some View {
        Text(text.uppercased(with: Locale.current))
            .font(.caption2.weight(.semibold))
            .kerning(0.8)
            .foregroundStyle(HarnessColors.textMuted)
    }
}

struct SectionHeader<Actions: View>: View {
    let eyebrow: String?
    let title: String
    let description: String?
    @ViewBuilder let actions: Actions

    init(
        eyebrow: String? = nil,
        title: String,
        description: String? = nil,
        @ViewBuilder actions: () -> Actions = { EmptyView() }
    ) {
        self.eyebrow = eyebrow
        self.title = title
        self.description = description
        self.actions = actions()
    }

    var body: some View {
        ViewThatFits(in: .horizontal) {
            headerRow
            headerColumn
        }
    }

    private var headerRow: some View {
        HStack(alignment: .top, spacing: 12) {
            VStack(alignment: .leading, spacing: 4) {
                headerText
            }
            Spacer()
            actions
        }
    }

    private var headerColumn: some View {
        VStack(alignment: .leading, spacing: 10) {
            headerText
            actions
        }
    }

    private var headerText: some View {
        VStack(alignment: .leading, spacing: 4) {
            if let eyebrow {
                EyebrowLabel(text: eyebrow)
            }
            Text(title)
                .font(.title3.weight(.semibold))
                .foregroundStyle(HarnessColors.text)
                .fixedSize(horizontal: false, vertical: true)
            if let description {
                Text(description)
                    .font(.subheadline)
                    .foregroundStyle(HarnessColors.textMuted)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }
}

struct InfoBannerCard: View {
    let title: String
    let bodyText: String
    let tint: Color

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            EyebrowLabel(text: title)
            Text(bodyText)
                .font(.subheadline)
                .foregroundStyle(HarnessColors.text)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(16)
        .harnessGlassSurface(cornerRadius: 16, fill: tint, border: tint.opacity(0.45))
    }
}

enum MetricTone {
    case neutral
    case positive
    case warning
    case info

    var container: Color {
        switch self {
        case .neutral: HarnessColors.card
        case .positive: HarnessColors.successTint
        case .warning: HarnessColors.warningTint
        case .info: HarnessColors.infoTint
        }
    }

    var valueColor: Color {
        switch self {
        case .neutral: HarnessColors.text
        case .positive: HarnessColors.success
        case .warning: HarnessColors.warning
        case .info: HarnessColors.info
        }
    }
}

struct MetricCard: View {
    let title: String
    let value: String
    let supporting: String
    var tone: MetricTone = .neutral

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            EyebrowLabel(text: title)
            Text(value)
                .font(.title3.weight(.bold))
                .foregroundStyle(tone.valueColor)
                .monospacedDigit()
                .lineLimit(2)
                .minimumScaleFactor(0.74)
            Text(supporting)
                .font(.caption)
                .foregroundStyle(HarnessColors.textMuted)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 12)
    }
}

struct SummaryCard: View {
    let title: String
    let subtitle: String
    let trailing: String
    let actionTitle: String?
    let action: (() -> Void)?

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(title)
                .font(.headline)
                .foregroundStyle(HarnessColors.text)
                .lineLimit(2)
            Text(subtitle)
                .font(.subheadline)
                .foregroundStyle(HarnessColors.textMuted)
                .lineLimit(2)
            Text(trailing)
                .font(.title3.weight(.bold))
                .foregroundStyle(HarnessColors.text)
                .monospacedDigit()
                .lineLimit(1)
                .minimumScaleFactor(0.82)
            if let actionTitle, let action {
                Button(actionTitle, action: action)
                    .buttonStyle(.borderless)
                    .foregroundStyle(HarnessColors.primary)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(12)
    }
}

struct MetricRow: View {
    let label: String
    let value: String

    var body: some View {
        HStack(alignment: .firstTextBaseline, spacing: 12) {
            EyebrowLabel(text: label)
                .lineLimit(1)
            Spacer()
            Text(value)
                .font(.subheadline)
                .foregroundStyle(HarnessColors.text)
                .monospacedDigit()
                .multilineTextAlignment(.trailing)
                .lineLimit(3)
                .minimumScaleFactor(0.82)
        }
    }
}

struct LoadingCard: View {
    let label: String

    var body: some View {
        HStack(spacing: 12) {
            ProgressView()
            Text(label)
                .font(.subheadline)
                .foregroundStyle(HarnessColors.textMuted)
            Spacer()
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

struct EmptyStateCard: View {
    let title: String
    let description: String

    var body: some View {
        VStack(spacing: 8) {
            Text(title)
                .font(.headline)
                .foregroundStyle(HarnessColors.text)
            Text(description)
                .font(.subheadline)
                .foregroundStyle(HarnessColors.textMuted)
                .multilineTextAlignment(.center)
        }
        .frame(maxWidth: .infinity)
        .padding(24)
    }
}

struct SectionDivider: View {
    var body: some View {
        Divider().opacity(0.4).padding(.vertical, 8)
    }
}

struct LanguageSelector: View {
    @EnvironmentObject private var store: HarnessStore

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(store.t("language.title"))
                .font(.headline)
                .foregroundStyle(HarnessColors.text)

            HStack(spacing: 8) {
                ForEach(AppLanguage.allCases, id: \.self) { language in
                    Button {
                        store.setLanguage(language)
                    } label: {
                        Text(language.label)
                            .font(.subheadline.weight(.semibold))
                            .frame(maxWidth: .infinity)
                    }
                    .buttonStyle(.borderedProminent)
                    .tint(store.state.language == language ? HarnessColors.primary : HarnessColors.surfaceStrong)
                    .foregroundStyle(store.state.language == language ? Color.white : HarnessColors.text)
                }
            }
        }
        .padding(14)
        .harnessGlassSurface(cornerRadius: 14)
    }
}

private struct HarnessInputChrome: ViewModifier {
    func body(content: Content) -> some View {
        content
            .padding(.horizontal, 14)
            .padding(.vertical, 12)
            .harnessGlassSurface(cornerRadius: 12, fill: HarnessColors.surface)
    }
}

extension View {
    func harnessInputStyle() -> some View {
        modifier(HarnessInputChrome())
    }
}

enum L10n {
    static var language: AppLanguage = .english

    static var appTitle: String { tr("app.title") }
    static var refresh: String { tr("action.refresh") }
    static var logout: String { tr("action.logout") }
    static var close: String { tr("common.close") }

    static func tr(_ key: String, language: AppLanguage? = nil) -> String {
        let lang = language ?? self.language
        guard
            let path = Bundle.main.path(forResource: lang.rawValue, ofType: "lproj"),
            let bundle = Bundle(path: path)
        else {
            return NSLocalizedString(key, comment: "")
        }
        return bundle.localizedString(forKey: key, value: nil, table: "Localizable")
    }
}

func moneyText(amountCents: Int, currency: String) -> String {
    let formatter = NumberFormatter()
    formatter.numberStyle = .currency
    formatter.locale = .current
    formatter.currencyCode = currency
    return formatter.string(from: NSNumber(value: Double(amountCents) / 100.0)) ?? "\(amountCents)"
}

func formatTimestamp(_ raw: String?, fallback: String) -> String {
    guard let raw, !raw.isEmpty else {
        return fallback
    }

    let parser = ISO8601DateFormatter()
    parser.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
    let fallbackParser = ISO8601DateFormatter()

    let date = parser.date(from: raw) ?? fallbackParser.date(from: raw)
    guard let date else {
        return raw
    }

    let formatter = DateFormatter()
    formatter.dateStyle = .medium
    formatter.timeStyle = .short
    formatter.locale = .current
    return formatter.string(from: date)
}

func browserURL(from baseURL: String) -> String {
    guard let components = URLComponents(string: baseURL), let scheme = components.scheme else {
        return baseURL
    }

    var value = "\(scheme)://\(components.host ?? baseURL)"
    if let port = components.port {
        value += ":\(port)"
    }
    return value
}
