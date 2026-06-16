import AppKit

final class AppDelegate: NSObject, NSApplicationDelegate {
    private var poller: SessionPoller?
    private var statusBarController: StatusBarController?

    func applicationDidFinishLaunching(_ notification: Notification) {
        // Write PID file for the Python CLI to detect running state.
        let stateDir = ProcessInfo.processInfo.environment["SIGNAL_LIGHT_STATE_DIR"]
            ?? "/private/tmp/signal-light"
        let pidPath = (stateDir as NSString).appendingPathComponent("gui-daemon.pid")

        // Ensure state directory exists.
        try? FileManager.default.createDirectory(
            atPath: stateDir, withIntermediateDirectories: true
        )

        // Write our PID.
        let pid = ProcessInfo.processInfo.processIdentifier
        try? "\(pid)".write(toFile: pidPath, atomically: true, encoding: .utf8)

        // Start polling.
        let poller = SessionPoller()
        self.poller = poller

        statusBarController = StatusBarController(poller: poller)
        poller.start()
    }

    func applicationWillTerminate(_ notification: Notification) {
        poller?.stop()

        // Clean up PID file.
        let stateDir = ProcessInfo.processInfo.environment["SIGNAL_LIGHT_STATE_DIR"]
            ?? "/private/tmp/signal-light"
        let pidPath = (stateDir as NSString).appendingPathComponent("gui-daemon.pid")
        try? FileManager.default.removeItem(atPath: pidPath)
    }
}
