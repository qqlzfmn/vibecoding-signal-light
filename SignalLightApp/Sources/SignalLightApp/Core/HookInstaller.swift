import Foundation

/// Install and repair local agent hook configuration.
/// Port of `signal_light/hooks/installer.py`.
enum HookInstaller {

    // MARK: - Constants

    /// The hook command that agents will invoke. Points back at this binary.
    /// When compiled into the app bundle, the executable is at Contents/MacOS/SignalLightApp.
    private static var executablePath: String {
        Bundle.main.executablePath ?? ProcessInfo.processInfo.arguments[0]
    }

    static func codexHookCommand() -> String {
        return "\(executablePath) codex-hook"
    }

    static func claudeCodeHookCommand() -> String {
        return "\(executablePath) claude-code-hook"
    }

    static let codexEvents: [String: Int] = [
        "SessionStart": 5,
        "UserPromptSubmit": 5,
        "PreToolUse": 5,
        "PostToolUse": 5,
        "PermissionRequest": 10,
        "Stop": 5,
        "SessionEnd": 5,
    ]

    static let claudeCodeEvents: [String: Int] = [
        "SessionStart": 5,
        "UserPromptSubmit": 5,
        "PreToolUse": 5,
        "PostToolUse": 5,
        "PostToolUseFailure": 5,
        "PreCompact": 5,
        "SubagentStart": 5,
        "SubagentStop": 5,
        "PermissionRequest": 10,
        "Notification": 5,
        "Stop": 5,
        "SessionEnd": 5,
    ]

    // MARK: - Types

    enum Agent: String, CaseIterable {
        case codex
        case claudeCode = "claude-code"

        var displayName: String {
            switch self {
            case .codex: return "Codex"
            case .claudeCode: return "Claude Code"
            }
        }

        var configPath: String {
            let home = NSHomeDirectory()
            switch self {
            case .codex:
                return (home as NSString).appendingPathComponent(".codex/hooks.json")
            case .claudeCode:
                return (home as NSString).appendingPathComponent(".claude/settings.json")
            }
        }

        var events: [String: Int] {
            switch self {
            case .codex: return codexEvents
            case .claudeCode: return claudeCodeEvents
            }
        }

        var passesEventArg: Bool {
            switch self {
            case .codex: return true
            case .claudeCode: return false
            }
        }

        var usesMatcher: Bool {
            switch self {
            case .codex: return false
            case .claudeCode: return true
            }
        }

        func hookCommand(for event: String) -> String {
            if passesEventArg {
                return "\(hookScript) \(event)"
            }
            return hookScript
        }

        var hookScript: String {
            switch self {
            case .codex: return codexHookCommand()
            case .claudeCode: return claudeCodeHookCommand()
            }
        }
    }

    struct AgentStatus {
        let agent: Agent
        let installed: Bool
        let configExists: Bool
        let validJson: Bool
        let missingEvents: [String]
        let brokenEvents: [String]
        let message: String
    }

    // MARK: - Inspection

    static func inspectAgent(_ agent: Agent) -> AgentStatus {
        let configExists = FileManager.default.fileExists(atPath: agent.configPath)

        let (config, validJson) = loadJSONConfig(at: agent.configPath)

        guard configExists else {
            return AgentStatus(
                agent: agent,
                installed: false,
                configExists: false,
                validJson: true,
                missingEvents: Array(agent.events.keys),
                brokenEvents: [],
                message: "config missing"
            )
        }

        guard validJson else {
            return AgentStatus(
                agent: agent,
                installed: false,
                configExists: true,
                validJson: false,
                missingEvents: Array(agent.events.keys),
                brokenEvents: [],
                message: "invalid JSON"
            )
        }

        guard let hooks = config["hooks"] as? [String: Any] else {
            return AgentStatus(
                agent: agent,
                installed: false,
                configExists: true,
                validJson: true,
                missingEvents: Array(agent.events.keys),
                brokenEvents: [],
                message: "hooks missing"
            )
        }

        var missing: [String] = []
        var broken: [String] = []
        for event in agent.events.keys {
            let entries: Any? = hooks[event]
            if entries == nil {
                missing.append(event)
            } else if !eventHasExpectedHook(entries: entries!, agent: agent, event: event) {
                broken.append(event)
            }
        }

        let installed = missing.isEmpty && broken.isEmpty
        let message: String
        if installed {
            message = "installed"
        } else if !missing.isEmpty && !broken.isEmpty {
            message = "\(missing.count) missing, \(broken.count) broken"
        } else if !missing.isEmpty {
            message = "\(missing.count) missing"
        } else {
            message = "\(broken.count) broken"
        }

        return AgentStatus(
            agent: agent,
            installed: installed,
            configExists: configExists,
            validJson: true,
            missingEvents: missing,
            brokenEvents: broken,
            message: message
        )
    }

    // MARK: - Install

    static func installAgent(_ agent: Agent) throws {
        var (config, validJson) = loadJSONConfig(at: agent.configPath)
        if !validJson {
            config = [:]
        }

        let originalText = try? String(contentsOfFile: agent.configPath, encoding: .utf8)

        // Ensure hooks dict exists.
        var hooks = (config["hooks"] as? [String: Any]) ?? [:]
        for (event, timeout) in agent.events {
            hooks[event] = mergeEventGroups(
                existingEntries: hooks[event],
                agent: agent,
                event: event,
                timeout: timeout
            )
        }
        config["hooks"] = hooks

        let newData = try JSONSerialization.data(
            withJSONObject: config, options: [.prettyPrinted, .withoutEscapingSlashes]
        )
        guard let newText = String(data: newData, encoding: .utf8) else {
            throw InstallError.encodingFailed
        }
        let newTextNL = newText + "\n"

        if originalText == newTextNL {
            return // unchanged
        }

        // Backup existing config.
        if FileManager.default.fileExists(atPath: agent.configPath) {
            backupConfig(at: agent.configPath)
        }

        // Write.
        let dir = (agent.configPath as NSString).deletingLastPathComponent
        try FileManager.default.createDirectory(atPath: dir, withIntermediateDirectories: true)
        try newTextNL.write(toFile: agent.configPath, atomically: true, encoding: .utf8)
    }

    /// Install hooks for the given agent. Returns the status after install.
    @discardableResult
    static func installAgentAndReport(_ agent: Agent) -> AgentStatus {
        try? installAgent(agent)
        return inspectAgent(agent)
    }

    // MARK: - Internal helpers

    private static func loadJSONConfig(at path: String) -> ([String: Any], Bool) {
        guard let data = FileManager.default.contents(atPath: path) else {
            return ([:], true)
        }
        do {
            let parsed = try JSONSerialization.jsonObject(with: data)
            guard let dict = parsed as? [String: Any] else {
                return ([:], false)
            }
            return (dict, true)
        } catch {
            return ([:], false)
        }
    }

    private static func backupConfig(at path: String) {
        let formatter = DateFormatter()
        formatter.dateFormat = "yyyyMMdd-HHmmss"
        let stamp = formatter.string(from: Date())
        let backupPath = path + ".bak-signal-light-install-\(stamp)"
        try? FileManager.default.copyItem(atPath: path, toPath: backupPath)
    }

    private static func eventHasExpectedHook(entries: Any, agent: Agent, event: String) -> Bool {
        guard let groups = entries as? [Any] else { return false }
        let expected = agent.hookCommand(for: event)
        let timeout = agent.events[event] ?? 5

        for group in groups {
            guard let groupDict = group as? [String: Any] else { continue }
            // For Claude Code, skip groups with non-empty matcher.
            if agent.usesMatcher,
               let matcher = groupDict["matcher"] as? String,
               !matcher.isEmpty {
                continue
            }
            guard let hooks = groupDict["hooks"] as? [[String: Any]] else { continue }
            for hook in hooks {
                if hook["type"] as? String == "command",
                   hook["command"] as? String == expected,
                   hook["timeout"] as? Int == timeout {
                    return true
                }
            }
        }
        return false
    }

    private static func mergeEventGroups(
        existingEntries: Any?, agent: Agent, event: String, timeout: Int
    ) -> [Any] {
        let replacement = hookGroup(agent: agent, event: event, timeout: timeout)
        guard let groups = existingEntries as? [Any] else {
            return [replacement]
        }

        var merged: [Any] = []
        var replaced = false

        for group in groups {
            guard let groupDict = group as? [String: Any] else {
                merged.append(group)
                continue
            }
            let (replacementGroup, cleanedGroup, hadSignalLight) = replaceSignalLightHooks(
                group: groupDict, agent: agent, replacement: replacement
            )
            if hadSignalLight {
                if let rg = replacementGroup { merged.append(rg); replaced = true }
                if let cg = cleanedGroup { merged.append(cg) }
            } else {
                merged.append(group)
            }
        }

        if !replaced {
            merged.append(replacement)
        }

        return merged
    }

    private static func replaceSignalLightHooks(
        group: [String: Any], agent: Agent, replacement: [String: Any]
    ) -> (replacementGroup: [String: Any]?, cleanedGroup: [String: Any]?, hadSignalLight: Bool) {
        guard let hooks = group["hooks"] as? [[String: Any]] else {
            return (nil, group, false)
        }

        let replacementHooks = replacement["hooks"] as? [[String: Any]] ?? []
        var updatedHooks: [[String: Any]] = []
        var keptHooks: [[String: Any]] = []
        var replaced = false

        for hook in hooks {
            if hook["type"] as? String == "command",
               isSignalLightCommand(hook["command"] as? String, agent: agent) {
                if !replaced {
                    updatedHooks.append(contentsOf: replacementHooks)
                    replaced = true
                }
                // Skip old signal light hook.
            } else {
                keptHooks.append(hook)
                updatedHooks.append(hook)
            }
        }

        guard replaced else { return (nil, group, false) }

        var replacementGroup = group
        replacementGroup["hooks"] = updatedHooks
        if let matcher = replacement["matcher"] {
            replacementGroup["matcher"] = matcher
        }

        if keptHooks.isEmpty {
            // All hooks replaced — just one group.
            var pureReplacement = group
            pureReplacement["hooks"] = replacementHooks
            if let matcher = replacement["matcher"] {
                pureReplacement["matcher"] = matcher
            }
            return (pureReplacement, nil, true)
        }

        var cleanedGroup = group
        cleanedGroup["hooks"] = keptHooks
        return (replacementGroup, cleanedGroup, true)
    }

    private static func isSignalLightCommand(_ command: String?, agent: Agent) -> Bool {
        guard let command = command, !command.trimmingCharacters(in: .whitespaces).isEmpty else {
            return false
        }
        let parts = command.components(separatedBy: .whitespaces)
        let joined = parts.filter { !$0.isEmpty }.joined(separator: " ")
        return joined.contains("signal-light codex-hook")
            || joined.contains("signal-light claude-code-hook")
            || joined.contains("SignalLightApp codex-hook")
            || joined.contains("SignalLightApp claude-code-hook")
    }

    private static func hookGroup(agent: Agent, event: String, timeout: Int) -> [String: Any] {
        var group: [String: Any] = [
            "hooks": [
                [
                    "type": "command",
                    "command": agent.hookCommand(for: event),
                    "timeout": timeout,
                ] as [String: Any]
            ]
        ]
        if agent.usesMatcher {
            group["matcher"] = ""
        }
        return group
    }

    enum InstallError: Error {
        case encodingFailed
    }
}
