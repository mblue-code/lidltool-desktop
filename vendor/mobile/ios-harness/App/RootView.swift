import SwiftUI

struct RootView: View {
    @EnvironmentObject private var store: HarnessStore

    var body: some View {
        ZStack(alignment: .top) {
            HarnessSceneBackground()

            if !store.state.isPaired {
                LoginView()
            } else {
                MainTabView()
            }

            if let message = store.state.message {
                MessageBanner(message: message) {
                    store.clearMessage()
                }
                .padding(.horizontal, 16)
                .padding(.top, 12)
                .transition(.move(edge: .top).combined(with: .opacity))
                .zIndex(1)
            }
        }
        .animation(.easeInOut(duration: 0.2), value: store.state.message?.id)
    }
}
