import SwiftUI
import UIKit

enum HarnessColors {
    static let primary = dynamic(light: 0x0065EA, dark: 0x147FFF)
    static let primaryDark = dynamic(light: 0x147FFF, dark: 0x7FC5FF)
    static let background = dynamic(
        light: 0xFCFCFC,
        dark: 0x091018,
        lightOpacity: 1.0,
        darkOpacity: 1.0
    )
    static let card = dynamic(
        light: 0xFFFFFF,
        dark: 0x0B1019,
        lightOpacity: 1.0,
        darkOpacity: 0.84
    )
    static let surface = dynamic(
        light: 0xF0F2F5,
        dark: 0x111926,
        lightOpacity: 1.0,
        darkOpacity: 0.88
    )
    static let surfaceStrong = dynamic(
        light: 0xE3ECF9,
        dark: 0x182130,
        lightOpacity: 1.0,
        darkOpacity: 0.92
    )
    static let text = dynamic(
        light: 0x05070B,
        dark: 0xF5F7FB,
        lightOpacity: 1.0,
        darkOpacity: 1.0
    )
    static let textMuted = dynamic(
        light: 0x626A75,
        dark: 0xBCC5D1,
        lightOpacity: 1.0,
        darkOpacity: 0.78
    )
    static let border = dynamic(
        light: 0xDADEE5,
        dark: 0xD2E2FF,
        lightOpacity: 1.0,
        darkOpacity: 0.12
    )
    static let success = dynamic(
        light: 0x189A30,
        dark: 0x8DF0BD,
        lightOpacity: 1.0,
        darkOpacity: 1.0
    )
    static let successTint = dynamic(
        light: 0xE6F7EA,
        dark: 0x112A14,
        lightOpacity: 1.0,
        darkOpacity: 0.88
    )
    static let warning = dynamic(
        light: 0xE89D00,
        dark: 0xF4D18A,
        lightOpacity: 1.0,
        darkOpacity: 1.0
    )
    static let warningTint = dynamic(
        light: 0xFFF2D9,
        dark: 0x332405,
        lightOpacity: 1.0,
        darkOpacity: 0.88
    )
    static let info = dynamic(
        light: 0x008FE6,
        dark: 0x7FC5FF,
        lightOpacity: 1.0,
        darkOpacity: 1.0
    )
    static let infoTint = dynamic(
        light: 0xE4F4FD,
        dark: 0x0E2637,
        lightOpacity: 1.0,
        darkOpacity: 0.88
    )
    static let destructive = dynamic(
        light: 0xFFE7E8,
        dark: 0x3A1013,
        lightOpacity: 1.0,
        darkOpacity: 0.88
    )
    static let destructiveText = dynamic(
        light: 0xE7000B,
        dark: 0xFF8E92,
        lightOpacity: 1.0,
        darkOpacity: 1.0
    )
    static let navSurface = dynamic(
        light: 0xFCFCFC,
        dark: 0x09131F,
        lightOpacity: 1.0,
        darkOpacity: 0.96
    )
    static let navRaised = dynamic(
        light: 0xF0F2F5,
        dark: 0x13233A,
        lightOpacity: 1.0,
        darkOpacity: 0.94
    )
    static let navOnSurface = dynamic(
        light: 0x05070B,
        dark: 0xF5F7FB,
        lightOpacity: 1.0,
        darkOpacity: 1.0
    )

    private static func dynamic(
        light: UInt64,
        dark: UInt64,
        lightOpacity: Double = 1.0,
        darkOpacity: Double = 1.0
    ) -> Color {
        Color(uiColor: UIColor { traits in
            let useDark = traits.userInterfaceStyle == .dark
            let hex = useDark ? dark : light
            return UIColor(
                red: Double((hex >> 16) & 0xFF) / 255.0,
                green: Double((hex >> 8) & 0xFF) / 255.0,
                blue: Double(hex & 0xFF) / 255.0,
                alpha: useDark ? darkOpacity : lightOpacity
            )
        })
    }
}

extension Color {
    init(hex: UInt64, opacity: Double = 1.0) {
        self.init(
            .sRGB,
            red: Double((hex >> 16) & 0xFF) / 255.0,
            green: Double((hex >> 8) & 0xFF) / 255.0,
            blue: Double(hex & 0xFF) / 255.0,
            opacity: opacity
        )
    }
}
