import Foundation

/// Session state management — read/write/aggregate sessions.json with flock-based locking.
/// Port of `signal_light/session.py`.
enum SessionStore {

    // MARK: - Paths

    static var stateDir: String { StatePaths.stateDir }

    static var sessionFile: String { StatePaths.sessionFile }

    static var lockFile: String { StatePaths.lockFile }

    static var sessionTTL: TimeInterval {
        if let raw = ProcessInfo.processInfo.environment["SIGNAL_LIGHT_SESSION_TTL_SECONDS"],
           let value = TimeInterval(raw) {
            return value
        }
        return 86400.0
    }

    // MARK: - Public API

    /// Update one session's signal. Returns the new aggregate signal name.
    @discardableResult
    static func applySessionSignal(sessionKey: String, signalName: String) -> String {
        return withLock {
            var state = readSessionFile()
            let now = Date().timeIntervalSince1970
            pruneSessions(&state.sessions, now: now)

            if SignalSemantics.sessionEnd.contains(signalName)
                || SignalSemantics.sessionClear.contains(signalName) {
                state.sessions.removeValue(forKey: sessionKey)
            } else if SignalSemantics.turnEnd.contains(signalName) {
                if let current = state.sessions[sessionKey],
                   SignalSemantics.turnEndKeep.contains(current.signal) {
                    // keep the session — don't remove
                } else {
                    state.sessions.removeValue(forKey: sessionKey)
                }
            } else {
                state.sessions[sessionKey] = SessionEntry(signal: signalName, updatedAt: now)
            }

            let aggregate = aggregateSignal(from: state.sessions)
            writeSessionFile(state)
            return aggregate
        }
    }

    /// Clear all tracked session states.
    static func clearSessionState() {
        withLock {
            writeSessionFile(SessionFile(sessions: [:]))
        }
    }

    /// Read the current snapshot (aggregate + sessions) without modifying.
    /// `sessions` holds typed `SessionEntry` values.
    static func readSessionSnapshot() -> [String: Any] {
        return withLock {
            var state = readSessionFile()
            pruneSessions(&state.sessions, now: Date().timeIntervalSince1970)
            return [
                "aggregate": aggregateSignal(from: state.sessions),
                "sessions": state.sessions,
            ]
        }
    }

    // MARK: - File I/O (typed JSON, see Models/SessionState.swift)

    /// Decode failure (missing/corrupt file or malformed JSON) yields an empty
    /// state — same silent tolerance as before.
    private static func readSessionFile() -> SessionFile {
        guard let data = FileManager.default.contents(atPath: sessionFile),
              let state = try? JSONDecoder().decode(SessionFile.self, from: data) else {
            return SessionFile(sessions: [:])
        }
        return state
    }

    private static func writeSessionFile(_ state: SessionFile) {
        try? FileManager.default.createDirectory(
            atPath: stateDir, withIntermediateDirectories: true
        )
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.prettyPrinted, .withoutEscapingSlashes]
        guard let data = try? encoder.encode(state) else { return }
        try? data.write(to: URL(fileURLWithPath: sessionFile), options: .atomic)
    }

    private static func pruneSessions(_ sessions: inout [String: SessionEntry], now: TimeInterval) {
        sessions = sessions.filter { _, entry in
            now - entry.updatedAt <= sessionTTL
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
