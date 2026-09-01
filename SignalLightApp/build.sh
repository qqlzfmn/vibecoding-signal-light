#!/bin/bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
RESOURCES_DIR="$SCRIPT_DIR/Resources"
BUILD_DIR="$SCRIPT_DIR/.build"
APP_BUNDLE="$BUILD_DIR/SignalLightApp.app"

echo "==> Building SignalLightApp (SwiftPM)..."

cd "$SCRIPT_DIR"

# Compile via SwiftPM (release).
BIN_PATH="$(swift build -c release --show-bin-path)"
swift build -c release

# Assemble .app bundle (SwiftPM also uses .build/, so only touch the bundle).
rm -rf "$APP_BUNDLE"
mkdir -p "$APP_BUNDLE/Contents/MacOS"
mkdir -p "$APP_BUNDLE/Contents/Resources"

cp "$BIN_PATH/SignalLightApp" "$APP_BUNDLE/Contents/MacOS/SignalLightApp"

# Copy Info.plist
cp "$RESOURCES_DIR/Info.plist" "$APP_BUNDLE/Contents/Info.plist"
# Copy omp/pi hook template
cp "$RESOURCES_DIR/omp-hook-template.ts" "$APP_BUNDLE/Contents/Resources/"

echo "==> Built: $APP_BUNDLE"
echo "==> Run:   open $APP_BUNDLE"
