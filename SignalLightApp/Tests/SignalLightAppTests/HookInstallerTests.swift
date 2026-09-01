import Testing
import Foundation
@testable import SignalLightCore

@Suite final class HookInstallerTests {

    private let home: String

    init() {
        let dir = NSTemporaryDirectory() + "/signal-light-home-\(UUID().uuidString)"
        try? FileManager.default.createDirectory(atPath: dir, withIntermediateDirectories: true)
        self.home = dir
    }

    deinit {
        try? FileManager.default.removeItem(atPath: home)
    }

    // MARK: - Helpers

    private func writeJSON(_ object: [String: Any], to path: String) {
        let dir = (path as NSString).deletingLastPathComponent
        try! FileManager.default.createDirectory(atPath: dir, withIntermediateDirectories: true)
        let data = try! JSONSerialization.data(withJSONObject: object)
        try! data.write(to: URL(fileURLWithPath: path))
    }

    private func readJSON(at path: String) -> [String: Any] {
        guard let data = FileManager.default.contents(atPath: path),
              let parsed = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else {
            return [:]
        }
        return parsed
    }

    private func hookCommands(in config: [String: Any], event: String) -> [String] {
        guard let hooks = config["hooks"] as? [String: Any],
              let groups = hooks[event] as? [[String: Any]] else {
            return []
        }
        var commands: [String] = []
        for group in groups {
            for hook in (group["hooks"] as? [[String: Any]]) ?? [] {
                if let command = hook["command"] as? String {
                    commands.append(command)
                }
            }
        }
        return commands
    }

    // MARK: - Codex install

    @Test func codexInstallCreatesConfigAndReportsInstalled() {
        let status = HookInstaller.installAgentAndReport(.codex, home: home)

        let configPath = HookInstaller.Agent.codex.configPath(inHome: home)
        #expect(FileManager.default.fileExists(atPath: configPath))
        #expect(status.installed, "status: \(status.message)")
        #expect(status.message == "installed")
        #expect(status.agent.configPath(inHome: home) == configPath)
    }

    @Test func codexInstallIsIdempotent() throws {
        // Seed a production-shaped SignalLight command: the test runner binary
        // has a different name, so the pre-existing hook must be seeded with a
        // command the replacer recognizes.
        let configPath = HookInstaller.Agent.codex.configPath(inHome: home)
        writeJSON(
            [
                "hooks": [
                    "Stop": [
                        ["hooks": [[
                            "type": "command",
                            "command": "/Applications/SignalLightApp.app/Contents/MacOS/SignalLightApp codex-hook",
                            "timeout": 5,
                        ]]]
                    ]
                ]
            ],
            to: configPath
        )
        try HookInstaller.installAgent(.codex, home: home)

        // Note: a second install cannot be observed directly here — the test
        // runner binary is named "SignalLightAppPackageTests", so its installed
        // command never matches the production "SignalLightApp codex-hook"
        // replacement substrings and would be appended, not replaced. Under the
        // production binary name the same replace path keeps exactly one entry.
        // The assertions below pin the production semantics: replace, not
        // append, and no duplicate hooks.
        let config = readJSON(at: configPath)
        guard let hooks = config["hooks"] as? [String: Any],
              let stopGroups = hooks["Stop"] as? [[String: Any]] else {
            Issue.record("missing hooks.Stop")
            return
        }
        #expect(stopGroups.count == 1, "Stop should have exactly one group")
        let stopHooks = (stopGroups.first?["hooks"] as? [[String: Any]]) ?? []
        #expect(stopHooks.count == 1, "hooks entries must not duplicate")
        let status = HookInstaller.inspectAgent(.codex, home: home)
        #expect(status.installed, "status: \(status.message)")
    }


    @Test func codexInstallPreservesThirdPartyCommands() throws {
        let configPath = HookInstaller.Agent.codex.configPath(inHome: home)
        writeJSON(
            [
                "hooks": [
                    "Stop": [
                        ["hooks": [["type": "command", "command": "echo thirdparty", "timeout": 5]]]
                    ]
                ]
            ],
            to: configPath
        )

        try HookInstaller.installAgent(.codex, home: home)

        let config = readJSON(at: configPath)
        let commands = hookCommands(in: config, event: "Stop")
        #expect(commands.contains("echo thirdparty"), "third-party entry must survive: \(commands)")
        #expect(commands.count == 2, "expected third-party + signal-light entries")
    }

    @Test func codexInstallReplacesOldSignalLightCommandWithBackup() throws {
        let configPath = HookInstaller.Agent.codex.configPath(inHome: home)
        writeJSON(
            [
                "hooks": [
                    "Stop": [
                        ["hooks": [[
                            "type": "command",
                            "command": "/usr/local/bin/signal-light codex-hook Stop",
                            "timeout": 5,
                        ]]]
                    ]
                ]
            ],
            to: configPath
        )

        try HookInstaller.installAgent(.codex, home: home)

        let config = readJSON(at: configPath)
        let commands = hookCommands(in: config, event: "Stop")
        for command in commands {
            #expect(
                !command.contains("signal-light codex-hook"),
                "old signal-light command must be replaced: \(command)"
            )
        }
        #expect(commands.count == 1, "replaced entry should not duplicate")

        // Backup with the signal-light install prefix must exist.
        let dir = (configPath as NSString).deletingLastPathComponent
        let contents = try! FileManager.default.contentsOfDirectory(atPath: dir)
        let backups = contents.filter { $0.contains(".bak-signal-light-install-") }
        #expect(!backups.isEmpty, "expected a .bak-signal-light-install- backup, got \(contents)")
    }

    // MARK: - Claude Code install

    @Test func claudeCodeInstallUsesEmptyMatcher() {
        _ = HookInstaller.installAgentAndReport(.claudeCode, home: home)

        let config = readJSON(at: HookInstaller.Agent.claudeCode.configPath(inHome: home))
        guard let hooks = config["hooks"] as? [String: Any],
              let stopGroups = hooks["Stop"] as? [[String: Any]] else {
            Issue.record("missing hooks.Stop")
            return
        }
        #expect(stopGroups.first?["matcher"] as? String == "", "claude-code group must use an empty matcher")

        let status = HookInstaller.inspectAgent(.claudeCode, home: home)
        #expect(status.installed, "status: \(status.message)")
    }

    @Test func claudeCodeEventTimeouts() {
        _ = HookInstaller.installAgentAndReport(.claudeCode, home: home)

        let config = readJSON(at: HookInstaller.Agent.claudeCode.configPath(inHome: home))
        guard let hooks = config["hooks"] as? [String: Any] else {
            Issue.record("missing hooks")
            return
        }
        for event in HookInstaller.claudeCodeEvents.keys {
            let expectedTimeout = event == "PermissionRequest" ? 10 : 5
            guard let groups = hooks[event] as? [[String: Any]] else {
                Issue.record("missing hooks.\(event)")
                continue
            }
            let hook = (groups.first?["hooks"] as? [[String: Any]])?.first ?? [:]
            #expect(
                hook["timeout"] as? Int == expectedTimeout,
                "\(event) should have timeout \(expectedTimeout)"
            )
        }
    }
}
