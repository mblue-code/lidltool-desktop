import SwiftUI

@main
struct LidlToolHarnessApp: App {
    @UIApplicationDelegateAdaptor(HarnessAppDelegate.self) private var appDelegate
    @StateObject private var store = HarnessStore()

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(store)
                .onAppear {
                    appDelegate.attach(store: store)
                }
        }
    }
}
