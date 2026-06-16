import AppKit
import Combine

/// Manages the NSStatusItem (menu bar icon) and its menu.
final class StatusBarController {
    private let statusItem: NSStatusItem
    private let poller: SessionPoller
    private var pollerCancellable: AnyCancellable?
    private var flashTimer: Timer?

    private var panel: DetailPanelWindow?
    private var signalStartedAt: TimeInterval = 0
    private var isFlashing: Bool = false
    private var currentSignal: String = "idle"

    init(poller: SessionPoller) {
        self.poller = poller
        self.statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)

        setupMenu()
        updateIcon(aggregateSignal: "idle", isFlashOn: true)

        pollerCancellable = poller.statePublisher
            .receive(on: RunLoop.main)
            .sink { [weak self] state in
                self?.handleStateUpdate(state)
            }
    }

    // MARK: - Menu

    private func setupMenu() {
        let menu = NSMenu()

        let detailsItem = NSMenuItem(title: "Show Details", action: #selector(togglePanel), keyEquivalent: "d")
        detailsItem.target = self
        menu.addItem(detailsItem)

        menu.addItem(NSMenuItem.separator())

        let quitItem = NSMenuItem(title: "Quit", action: #selector(quit), keyEquivalent: "q")
        quitItem.target = self
        menu.addItem(quitItem)

        statusItem.menu = menu
    }

    // MARK: - State Handling

    private func handleStateUpdate(_ state: SessionPoller.State) {
        let signalName = state.aggregateSignal
        let def = SIGNAL_DEFINITIONS[signalName]
        let wasRepeating = isFlashing

        currentSignal = signalName

        if def?.isRepeating == true {
            if !wasRepeating || signalStartedAt == 0 {
                signalStartedAt = CACurrentMediaTime()
            }
            isFlashing = true
            startFlashTimer()
        } else {
            isFlashing = false
            stopFlashTimer()
            updateIcon(aggregateSignal: signalName, isFlashOn: true)
        }

        // Update panel.
        if let panel = panel, panel.isVisible {
            panel.updateSignal(
                name: def?.name ?? signalName,
                summary: def?.summary ?? "",
                sessionCount: state.sessionCount,
                isRepeating: def?.isRepeating ?? false,
                flashColor: signalColorKey(for: signalName)
            )
        }
    }

    private func startFlashTimer() {
        stopFlashTimer()
        flashTimer = Timer.scheduledTimer(withTimeInterval: 0.5, repeats: true) { [weak self] _ in
            self?.tickFlash()
        }
        tickFlash()
    }

    private func stopFlashTimer() {
        flashTimer?.invalidate()
        flashTimer = nil
    }

    private func tickFlash() {
        let elapsed = CACurrentMediaTime() - signalStartedAt
        let flashOn = Int(elapsed / 0.5) % 2 == 0
        updateIcon(aggregateSignal: currentSignal, isFlashOn: flashOn)
    }

    // MARK: - Icon Rendering

    private func updateIcon(aggregateSignal: String, isFlashOn: Bool) {
        let size = NSSize(width: 22, height: 22)
        let image = NSImage(size: size, flipped: false) { [self] rect in
            let color: NSColor
            if isFlashOn {
                color = self.colorForSignal(aggregateSignal)
            } else {
                color = self.dimColorForSignal(aggregateSignal)
            }

            let path = NSBezierPath(ovalIn: rect.insetBy(dx: 1, dy: 1))
            color.setFill()
            path.fill()

            return true
        }
        image.isTemplate = false

        statusItem.button?.image = image
        statusItem.button?.title = ""
    }

    private func colorForSignal(_ signal: String) -> NSColor {
        let def = SIGNAL_DEFINITIONS[signal]
        return def?.color.nsColor ?? SignalColor.grey.nsColor
    }

    private func dimColorForSignal(_ signal: String) -> NSColor {
        let def = SIGNAL_DEFINITIONS[signal]
        return def?.color.dimColor ?? SignalColor.grey.dimColor
    }

    private func signalColorKey(for signal: String) -> String {
        switch signal {
        case "blocked": return "red"
        case "permission", "attention", "done": return "yellow"
        case "off": return "grey"
        default: return "green"
        }
    }

    // MARK: - Actions

    @objc private func togglePanel() {
        if let panel = panel, panel.isVisible {
            panel.orderOut(nil)
            return
        }

        if panel == nil {
            let panelWidth: CGFloat = 260
            let panelHeight: CGFloat = 340
            panel = DetailPanelWindow(
                contentRect: NSRect(x: 0, y: 0, width: panelWidth, height: panelHeight),
                styleMask: [.nonactivatingPanel, .titled, .closable],
                backing: .buffered,
                defer: true
            )
        }

        let state = poller.currentState
        let def = SIGNAL_DEFINITIONS[state.aggregateSignal]
        panel?.updateSignal(
            name: def?.name ?? state.aggregateSignal,
            summary: def?.summary ?? "",
            sessionCount: state.sessionCount,
            isRepeating: def?.isRepeating ?? false,
            flashColor: signalColorKey(for: state.aggregateSignal)
        )
        panel?.showPanel()
    }

    @objc private func quit() {
        NSApp.terminate(nil)
    }
}
