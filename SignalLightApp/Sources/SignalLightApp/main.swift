import AppKit
import SignalLightCore

if let code = CLIDispatch.run(CommandLine.arguments) {
    exit(code)
}

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.run()
