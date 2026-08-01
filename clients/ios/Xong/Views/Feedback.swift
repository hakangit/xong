import AVFoundation
import Foundation
import UIKit

/// Sound and haptics for the completion moment. SPEC calls the check-off THE
/// product, and this is the part native can do better than the web build.
@MainActor
final class Feedback {
    static let shared = Feedback()

    private var player: AVAudioPlayer?
    private let impact = UIImpactFeedbackGenerator(style: .medium)
    private let notice = UINotificationFeedbackGenerator()

    private(set) var isMuted: Bool {
        get { UserDefaults.standard.bool(forKey: "xong.muted") }
        set { UserDefaults.standard.set(newValue, forKey: "xong.muted") }
    }

    private init() {
        // .ambient so Xong never interrupts music a user is already playing —
        // a task app has no business stopping someone's podcast.
        try? AVAudioSession.sharedInstance().setCategory(.ambient, mode: .default)
        if let url = Bundle.main.url(forResource: "ding", withExtension: "wav") {
            player = try? AVAudioPlayer(contentsOf: url)
            player?.prepareToPlay()
        }
    }

    func toggleMute() {
        isMuted.toggle()
    }

    func prepare() {
        impact.prepare()
    }

    func completed() {
        impact.impactOccurred(intensity: 0.9)
        guard !isMuted else { return }
        try? AVAudioSession.sharedInstance().setActive(true)
        player?.currentTime = 0
        player?.play()
    }

    func undone() {
        impact.impactOccurred(intensity: 0.4)
    }

    func blocked() {
        notice.notificationOccurred(.warning)
    }
}
