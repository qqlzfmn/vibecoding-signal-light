import AppKit

public final class AppDelegate: NSObject, NSApplicationDelegate {
    private var poller: SessionPoller?
    private var statusBarController: StatusBarController?

    public override init() {}

    public func applicationDidFinishLaunching(_ notification: Notification) {
        // Ensure state directory exists.
        try? FileManager.default.createDirectory(
            atPath: StatePaths.stateDir, withIntermediateDirectories: true
        )

        // Start polling.
        let poller = SessionPoller()
        self.poller = poller

        statusBarController = StatusBarController(poller: poller)
        poller.start()
    }

    public func applicationWillTerminate(_ notification: Notification) {
        poller?.stop()
    }
}
