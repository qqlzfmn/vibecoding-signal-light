import AppKit

public final class AppDelegate: NSObject, NSApplicationDelegate {
    private var poller: SessionPoller?
    private var statusBarController: StatusBarController?

    public override init() {}

    public func applicationDidFinishLaunching(_ notification: Notification) {
        // Write PID file for the Python CLI to detect running state.
        let pidPath = StatePaths.pidFile

        // Ensure state directory exists.
        try? FileManager.default.createDirectory(
            atPath: StatePaths.stateDir, withIntermediateDirectories: true
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

    public func applicationWillTerminate(_ notification: Notification) {
        poller?.stop()

        // Clean up PID file.
        let pidPath = StatePaths.pidFile
        try? FileManager.default.removeItem(atPath: pidPath)
    }
}
