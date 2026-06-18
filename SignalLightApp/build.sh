#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SOURCES_DIR="$SCRIPT_DIR/Sources/SignalLightApp"
RESOURCES_DIR="$SCRIPT_DIR/Resources"
BUILD_DIR="$SCRIPT_DIR/.build"
APP_BUNDLE="$BUILD_DIR/SignalLightApp.app"

echo "==> Building SignalLightApp..."

# Clean
rm -rf "$APP_BUNDLE"

# Create .app bundle structure
mkdir -p "$APP_BUNDLE/Contents/MacOS"
mkdir -p "$APP_BUNDLE/Contents/Resources"

# Compile all Swift sources
SOURCES=(
    "$SOURCES_DIR/Models/SessionState.swift"
    "$SOURCES_DIR/Models/SignalDefinition.swift"
    "$SOURCES_DIR/Services/SessionPoller.swift"
    "$SOURCES_DIR/Services/LaunchdManager.swift"
    "$SOURCES_DIR/Core/SessionStore.swift"
    "$SOURCES_DIR/Core/CodexHookAdapter.swift"
    "$SOURCES_DIR/Core/ClaudeCodeHookAdapter.swift"
    "$SOURCES_DIR/Core/HookInstaller.swift"
    "$SOURCES_DIR/Views/TrafficLightView.swift"
    "$SOURCES_DIR/Views/DetailPanelWindow.swift"
    "$SOURCES_DIR/Views/StatusBarController.swift"
    "$SOURCES_DIR/App/AppDelegate.swift"
    "$SOURCES_DIR/App/main.swift"
)

swiftc \
    -target arm64-apple-macos13.0 \
    -O \
    -o "$APP_BUNDLE/Contents/MacOS/SignalLightApp" \
    "${SOURCES[@]}"

# Copy Info.plist
cp "$RESOURCES_DIR/Info.plist" "$APP_BUNDLE/Contents/Info.plist"

echo "==> Built: $APP_BUNDLE"
echo "==> Run:   open $APP_BUNDLE"
