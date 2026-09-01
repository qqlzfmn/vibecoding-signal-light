import Testing
import Foundation
@testable import SignalLightCore

/// SessionStore reads its state dir from the process environment, and the
/// environment is process-global — so these tests must not run concurrently.
@Suite(.serialized)
final class SessionStoreTests {

    private let tmpDir: String

    init() {
        let dir = NSTemporaryDirectory() + "/signal-light-tests-\(UUID().uuidString)"
        try? FileManager.default.createDirectory(atPath: dir, withIntermediateDirectories: true)
        self.tmpDir = dir
        setenv("SIGNAL_LIGHT_STATE_DIR", dir, 1)
    }

    deinit {
        unsetenv("SIGNAL_LIGHT_STATE_DIR")
        try? FileManager.default.removeItem(atPath: tmpDir)
    }

    // MARK: - Helpers

    private func writeSessionsFile(_ sessions: [String: [String: Any]]) {
        let state: [String: Any] = ["sessions": sessions]
        let data = try! JSONSerialization.data(withJSONObject: state)
        try! data.write(to: URL(fileURLWithPath: SessionStore.sessionFile))
    }

    private func readSessionsFile() -> [String: [String: Any]] {
        guard let data = FileManager.default.contents(atPath: SessionStore.sessionFile),
              let state = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let sessions = state["sessions"] as? [String: [String: Any]] else {
            return [:]
        }
        return sessions
    }

    // MARK: - aggregateSessions priority

    @Test func aggregatePriorityBlockedHighest() {
        let now = Date().timeIntervalSince1970
        let sessions: [String: [String: Any]] = [
            "a": ["signal": "working", "updated_at": now],
            "b": ["signal": "permission", "updated_at": now],
            "c": ["signal": "blocked", "updated_at": now],
        ]
        #expect(SessionStore.aggregateSessions(sessions) == "blocked")
    }

    @Test func aggregatePriorityPermission() {
        let now = Date().timeIntervalSince1970
        let sessions: [String: [String: Any]] = [
            "a": ["signal": "working", "updated_at": now],
            "b": ["signal": "permission", "updated_at": now],
        ]
        #expect(SessionStore.aggregateSessions(sessions) == "permission")
    }

    @Test func aggregatePriorityAttentionSet() {
        let now = Date().timeIntervalSince1970
        for signal in ["attention", "done"] {
            let sessions: [String: [String: Any]] = [
                "a": ["signal": signal, "updated_at": now],
                "b": ["signal": "working", "updated_at": now],
            ]
            #expect(SessionStore.aggregateSessions(sessions) == "attention", "\(signal)")
        }
    }

    @Test func aggregatePriorityWorkingSet() {
        let now = Date().timeIntervalSince1970
        for signal in ["thinking", "working", "tool_done"] {
            let sessions: [String: [String: Any]] = [
                "a": ["signal": signal, "updated_at": now],
            ]
            #expect(SessionStore.aggregateSessions(sessions) == "working")
        }
    }

    @Test func aggregateEmptyIsIdle() {
        #expect(SessionStore.aggregateSessions([:]) == "idle")
    }

    // MARK: - applySessionSignal

    @Test func applyWorkingSignalPersistsAndAggregates() {
        let aggregate = SessionStore.applySessionSignal(sessionKey: "s1", signalName: "working")
        #expect(aggregate == "working")

        let sessions = readSessionsFile()
        #expect(sessions["s1"]?["signal"] as? String == "working")
    }

    @Test func applySessionEndRemovesSession() {
        SessionStore.applySessionSignal(sessionKey: "s1", signalName: "working")
        SessionStore.applySessionSignal(sessionKey: "s1", signalName: "session_end")

        let sessions = readSessionsFile()
        #expect(sessions["s1"] == nil)
        #expect(SessionStore.readSessionSnapshot()["aggregate"] as? String == "idle")
    }

    @Test func applyOffRemovesSession() {
        SessionStore.applySessionSignal(sessionKey: "s1", signalName: "working")
        SessionStore.applySessionSignal(sessionKey: "s1", signalName: "off")

        let sessions = readSessionsFile()
        #expect(sessions["s1"] == nil)
    }

    @Test func turnEndRemovesNonProtectedSession() {
        SessionStore.applySessionSignal(sessionKey: "s1", signalName: "working")
        SessionStore.applySessionSignal(sessionKey: "s1", signalName: "turn_end")

        let sessions = readSessionsFile()
        #expect(sessions["s1"] == nil)
    }

    @Test func turnEndKeepsPermissionSession() {
        SessionStore.applySessionSignal(sessionKey: "s1", signalName: "permission")
        SessionStore.applySessionSignal(sessionKey: "s1", signalName: "turn_end")

        let sessions = readSessionsFile()
        #expect(sessions["s1"]?["signal"] as? String == "permission")
    }

    @Test func turnEndKeepsBlockedSession() {
        SessionStore.applySessionSignal(sessionKey: "s1", signalName: "blocked")
        SessionStore.applySessionSignal(sessionKey: "s1", signalName: "turn_end")

        let sessions = readSessionsFile()
        #expect(sessions["s1"]?["signal"] as? String == "blocked")
    }

    // MARK: - TTL pruning

    @Test func expiredSessionPrunedOnRead() {
        let expiredAt = Date().timeIntervalSince1970 - SessionStore.sessionTTL - 60
        writeSessionsFile([
            "expired": ["signal": "working", "updated_at": expiredAt],
            "fresh": ["signal": "blocked", "updated_at": Date().timeIntervalSince1970],
        ])

        let snapshot = SessionStore.readSessionSnapshot()
        let sessions = snapshot["sessions"] as? [String: [String: Any]] ?? [:]
        #expect(sessions["expired"] == nil)
        #expect(sessions["fresh"] != nil)
        #expect(snapshot["aggregate"] as? String == "blocked")
    }

    // MARK: - clearSessionState

    @Test func clearSessionStateEmptiesStore() {
        SessionStore.applySessionSignal(sessionKey: "s1", signalName: "working")
        SessionStore.applySessionSignal(sessionKey: "s2", signalName: "blocked")

        SessionStore.clearSessionState()

        #expect(readSessionsFile().isEmpty)
        #expect(SessionStore.readSessionSnapshot()["aggregate"] as? String == "idle")
    }
}
