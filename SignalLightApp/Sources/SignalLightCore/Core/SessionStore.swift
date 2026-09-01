import Foundation

/// Session state management — read/write/aggregate sessions.json with flock-based locking.
/// Port of `signal_light/session.py`.
enum SessionStore {

    // MARK: - Paths

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

    static var sessionTTL: TimeInterval {
        if let raw = ProcessInfo.processInfo.environment["SIGNAL_LIGHT_SESSION_TTL_SECONDS"],
           let value = TimeInterval(raw) {
            return value
        }
        return 86400.0
    }

    // MARK: - Priority sets (mirrors session.py)

    private static let redSignals: Set<String> = ["blocked"]
    private static let yellowSignals: Set<String> = ["permission", "attention", "done"]
    private static let workingSignals: Set<String> = ["thinking", "working", "tool_done"]
    private static let sessionEndSignals: Set<String> = ["session_end"]
    private static let sessionClearSignals: Set<String> = ["off"]
    private static let turnEndSignals: Set<String> = ["turn_end"]
    private static let turnEndKeepSignals: Set<String> = ["permission", "blocked"]

    // MARK: - Public API

    /// Update one session's signal. Returns the new aggregate signal name.
    @discardableResult
    static func applySessionSignal(sessionKey: String, signalName: String) -> String {
        return withLock {
            var state = readSessionState()
            var sessions = state["sessions"] as? [String: [String: Any]] ?? [:]
            let now = Date().timeIntervalSince1970
            pruneSessions(&sessions, now: now)

            if sessionEndSignals.contains(signalName) {
                sessions.removeValue(forKey: sessionKey)
            } else if sessionClearSignals.contains(signalName) {
                sessions.removeValue(forKey: sessionKey)
            } else if turnEndSignals.contains(signalName) {
                if let current = sessions[sessionKey],
                   let currentSignal = current["signal"] as? String,
                   turnEndKeepSignals.contains(currentSignal) {
                    // keep the session — don't remove
                } else {
                    sessions.removeValue(forKey: sessionKey)
                }
            } else {
                sessions[sessionKey] = [
                    "signal": signalName,
                    "updated_at": now,
                ]
            }

            let aggregate = aggregateSessions(sessions)
            state["sessions"] = sessions
            writeSessionState(state)
            return aggregate
        }
    }

    /// Clear all tracked session states.
    static func clearSessionState() {
        withLock {
            writeSessionState(["sessions": [String: Any]()])
        }
    }

    /// Read the current snapshot (aggregate + sessions) without modifying.
    static func readSessionSnapshot() -> [String: Any] {
        return withLock {
            let state = readSessionState()
            var sessions = state["sessions"] as? [String: [String: Any]] ?? [:]
            let now = Date().timeIntervalSince1970
            pruneSessions(&sessions, now: now)
            let aggregate = aggregateSessions(sessions)
            return [
                "aggregate": aggregate,
                "sessions": sessions,
            ]
        }
    }

    // MARK: - Aggregate

    /// Priority: blocked > permission > attention > working > idle
    static func aggregateSessions(_ sessions: [String: [String: Any]]) -> String {
        let signals = sessions.values.compactMap { $0["signal"] as? String }

        if signals.contains(where: { redSignals.contains($0) }) {
            return "blocked"
        }
        if signals.contains("permission") {
            return "permission"
        }
        if signals.contains(where: { yellowSignals.contains($0) }) {
            return "attention"
        }
        if signals.contains(where: { workingSignals.contains($0) }) {
            return "working"
        }
        return "idle"
    }

    // MARK: - File I/O

    private static func readSessionState() -> [String: Any] {
        guard let data = FileManager.default.contents(atPath: sessionFile),
              let state = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              state["sessions"] is [String: Any] else {
            return ["sessions": [String: Any]()]
        }
        return state
    }

    private static func writeSessionState(_ state: [String: Any]) {
        try? FileManager.default.createDirectory(
            atPath: stateDir, withIntermediateDirectories: true
        )
        guard let data = try? JSONSerialization.data(
            withJSONObject: state, options: [.prettyPrinted, .withoutEscapingSlashes]
        ) else { return }
        try? data.write(to: URL(fileURLWithPath: sessionFile), options: .atomic)
    }

    private static func pruneSessions(_ sessions: inout [String: [String: Any]], now: TimeInterval) {
        let expired = sessions.filter { _, entry in
            let updatedAt = entry["updated_at"] as? TimeInterval ?? 0
            return now - updatedAt > sessionTTL
        }
        for key in expired.keys {
            sessions.removeValue(forKey: key)
        }
    }

    // MARK: - File locking (fcntl flock, mirroring Python's fcntl.LOCK_EX)

    private static func withLock<T>(_ body: () -> T) -> T {
        try? FileManager.default.createDirectory(
            atPath: stateDir, withIntermediateDirectories: true
        )

        // Open or create the lock file.
        if !FileManager.default.fileExists(atPath: lockFile) {
            FileManager.default.createFile(atPath: lockFile, contents: nil)
        }

        guard let fd = fopen(lockFile, "a+") else {
            // Can't open lock file — proceed without locking (best effort).
            return body()
        }
        defer { fclose(fd) }

        flock(fileno(fd), LOCK_EX)
        defer { flock(fileno(fd), LOCK_UN) }

        return body()
    }
}

// MARK: - POSIX flock import

#if os(macOS)
import Darwin
#else
import Glibc
#endif

private let LOCK_EX: Int32 = 2
private let LOCK_UN: Int32 = 8
