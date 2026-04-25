import SwiftUI

struct MainTabView: View {
    @EnvironmentObject private var store: HarnessStore

    init() {
#if os(iOS)
        let selectedColor = UIColor(red: 0.0, green: 0.396, blue: 0.918, alpha: 1.0)
        let normalColor = UIColor.secondaryLabel
        let appearance = UITabBarAppearance()
        appearance.configureWithDefaultBackground()

        for itemAppearance in [
            appearance.stackedLayoutAppearance,
            appearance.inlineLayoutAppearance,
            appearance.compactInlineLayoutAppearance
        ] {
            itemAppearance.selected.iconColor = selectedColor
            itemAppearance.selected.titleTextAttributes = [.foregroundColor: selectedColor]
            itemAppearance.normal.iconColor = normalColor
            itemAppearance.normal.titleTextAttributes = [.foregroundColor: normalColor]
        }

        let tabBar = UITabBar.appearance()
        tabBar.standardAppearance = appearance
        tabBar.scrollEdgeAppearance = appearance
        tabBar.tintColor = selectedColor
        tabBar.unselectedItemTintColor = normalColor
#endif
    }

    var body: some View {
        selectedTab
            .safeAreaInset(edge: .bottom) {
                HarnessTabBar(selection: $store.state.selectedTab)
            }
    }

    @ViewBuilder
    private var selectedTab: some View {
        switch store.state.selectedTab {
        case .home:
            tabContainer {
                DashboardView()
            }
        case .transactions:
            tabContainer {
                ReceiptsView()
            }
        case .capture:
            tabContainer {
                OCRView()
            }
        case .analysis:
            tabContainer {
                AnalysisView()
            }
        case .sync:
            tabContainer {
                SourcesView()
            }
        case .settings:
            tabContainer {
                OffersView()
            }
        }
    }

    private func tabContainer<Content: View>(@ViewBuilder content: () -> Content) -> some View {
        NavigationStack {
            content()
                .toolbar { navigationToolbar }
                .modifier(NavigationBarAppearance())
        }
    }

    @ToolbarContentBuilder
    private var navigationToolbar: some ToolbarContent {
#if os(iOS)
        ToolbarItem(placement: .topBarLeading) {
            toolbarIdentity
        }

        ToolbarItemGroup(placement: .topBarTrailing) {
            toolbarActions
        }
#else
        ToolbarItem(placement: .automatic) {
            toolbarIdentity
        }

        ToolbarItemGroup(placement: .automatic) {
            toolbarActions
        }
#endif
    }

    private var toolbarIdentity: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(store.state.local.pairedDesktop?.desktopName ?? L10n.appTitle)
                .font(.headline.weight(.semibold))
                .foregroundStyle(HarnessColors.navOnSurface)
            Text(store.state.local.pairedDesktop.map { browserURL(from: $0.endpointURL) } ?? store.t("mobile.common.localOnly"))
                .font(.caption)
                .foregroundStyle(HarnessColors.navOnSurface.opacity(0.72))
        }
    }

    private var toolbarActions: some View {
        HStack(spacing: 12) {
            Button {
                Task { await store.syncNow() }
            } label: {
                Label(L10n.refresh, systemImage: "arrow.clockwise")
                    .labelStyle(.iconOnly)
            }
            .foregroundStyle(HarnessColors.navOnSurface)
            .buttonStyle(.plain)

            Button {
                store.forgetPairing()
            } label: {
                Label(store.t("action.logout"), systemImage: "xmark.circle")
                    .labelStyle(.iconOnly)
            }
            .foregroundStyle(HarnessColors.navOnSurface)
            .buttonStyle(.plain)
        }
    }
}

private struct NavigationBarAppearance: ViewModifier {
    @Environment(\.colorScheme) private var colorScheme

    func body(content: Content) -> some View {
#if os(iOS)
        content
            .toolbarBackground(HarnessColors.navSurface, for: .navigationBar)
            .toolbarBackground(.visible, for: .navigationBar)
            .toolbarColorScheme(colorScheme == .dark ? .dark : .light, for: .navigationBar)
#else
        content
#endif
    }
}

private struct HarnessTabBar: View {
    @Binding var selection: AppTab

    var body: some View {
        HStack(spacing: 4) {
            ForEach(AppTab.allCases, id: \.self) { tab in
                Button {
                    withAnimation(.easeOut(duration: 0.16)) {
                        selection = tab
                    }
                } label: {
                    VStack(spacing: 3) {
                        Image(systemName: tab.systemImage)
                            .font(.system(size: 17, weight: .semibold))
                            .frame(height: 19)
                        Text(tab.title)
                            .font(.caption2.weight(selection == tab ? .semibold : .medium))
                            .lineLimit(1)
                            .minimumScaleFactor(0.72)
                    }
                    .frame(maxWidth: .infinity, minHeight: 48)
                    .foregroundStyle(selection == tab ? HarnessColors.primary : HarnessColors.textMuted)
                    .background {
                        if selection == tab {
                            RoundedRectangle(cornerRadius: 14, style: .continuous)
                                .fill(HarnessColors.primary.opacity(0.12))
                        }
                    }
                    .contentShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
                }
                .buttonStyle(.plain)
                .accessibilityLabel(tab.title)
                .accessibilityAddTraits(selection == tab ? .isSelected : [])
            }
        }
        .padding(6)
        .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 24, style: .continuous))
        .overlay {
            RoundedRectangle(cornerRadius: 24, style: .continuous)
                .stroke(HarnessColors.border, lineWidth: 1)
        }
        .padding(.horizontal, 10)
        .padding(.top, 6)
        .padding(.bottom, 8)
    }
}
