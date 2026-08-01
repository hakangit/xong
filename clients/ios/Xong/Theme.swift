import SwiftUI

/// Palette lifted from clients/web/css/app.css so the native app and the
/// web app read as the same product. Both schemes are first-class per SPEC.
extension Color {
    private static func adaptive(light: UInt32, dark: UInt32) -> Color {
        Color(UIColor { $0.userInterfaceStyle == .dark ? UIColor(hex: dark) : UIColor(hex: light) })
    }

    static let xBackground = adaptive(light: 0xf3efe5, dark: 0x1b1814)
    static let xSurface = adaptive(light: 0xfaf7ef, dark: 0x242019)
    static let xSurface2 = adaptive(light: 0xeee9db, dark: 0x2c2720)
    static let xInk = adaptive(light: 0x26211a, dark: 0xece3d2)
    static let xMuted = adaptive(light: 0x7d7466, dark: 0x9a8f7c)
    static let xFaint = adaptive(light: 0xada495, dark: 0x665d4f)
    static let xLine = adaptive(light: 0xe2dac8, dark: 0x383126)
    /// Reserved for completion moments — the one warm note in the app.
    static let xAccent = adaptive(light: 0xc2501f, dark: 0xe8854a)
}

private extension UIColor {
    convenience init(hex: UInt32) {
        self.init(
            red: CGFloat((hex >> 16) & 0xff) / 255,
            green: CGFloat((hex >> 8) & 0xff) / 255,
            blue: CGFloat(hex & 0xff) / 255,
            alpha: 1
        )
    }
}

enum XFont {
    static func display(_ size: CGFloat) -> Font {
        .system(size: size, weight: .heavy, design: .default)
    }

    static func body(_ size: CGFloat, weight: Font.Weight = .regular) -> Font {
        .system(size: size, weight: weight)
    }
}
