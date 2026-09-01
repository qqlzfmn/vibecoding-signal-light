import Foundation

/// Single source of truth for on-disk state paths. All callers derive from
/// `stateDir`, which honours the `SIGNAL_LIGHT_STATE_DIR` override.
enum StatePaths {
    static var stateDir: String {
        ProcessInfo.processInfo.environment["SIGNAL_LIGHT_STATE_DIR"]
            ?? "/private/tmp/signal-light"
    }

    static var sessionFile: String {
        (stateDir as NSString).appendingPathComponent("sessions.json")
    }

    static var lockFile: String {
        (stateDir as NSString).appendingPathComponent("state.lock")
    }

    static var pidFile: String {
        (stateDir as NSString).appendingPathComponent("gui-daemon.pid")
    }

    static var logFile: String {
        (stateDir as NSString).appendingPathComponent("app.log")
    }
}
