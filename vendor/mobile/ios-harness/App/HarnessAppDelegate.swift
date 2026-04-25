import Foundation
import UIKit

@MainActor
final class HarnessAppDelegate: NSObject, UIApplicationDelegate {
    private weak var store: HarnessStore?

    func attach(store: HarnessStore) {
        self.store = store
    }

    func application(
        _ application: UIApplication,
        didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]? = nil
    ) -> Bool {
        true
    }
}
