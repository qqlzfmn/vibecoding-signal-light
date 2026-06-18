#!/bin/bash
set -euo pipefail

# ── Paths ──────────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BUILD_DIR="$SCRIPT_DIR/.build"
APP_BUNDLE="$BUILD_DIR/SignalLightApp.app"
PKG_ROOT="$BUILD_DIR/pkg-root"
PKG_COMPONENT="$BUILD_DIR/SignalLightApp-component.pkg"
PKG_FINAL="$BUILD_DIR/SignalLightApp.pkg"

echo "==> Step 1: Building app..."
bash "$SCRIPT_DIR/build.sh"

echo ""
echo "==> Step 2: Preparing package root..."
rm -rf "$PKG_ROOT"
mkdir -p "$PKG_ROOT/Applications"
cp -R "$APP_BUNDLE" "$PKG_ROOT/Applications/"

echo ""
echo "==> Step 3: Building component package..."
pkgbuild \
    --root "$PKG_ROOT" \
    --identifier "com.starlight36.SignalLightApp" \
    --version "0.2.0" \
    --install-location "/" \
    "$PKG_COMPONENT"

echo ""
echo "==> Step 4: Building product archive..."
cat > "$BUILD_DIR/distribution.xml" << 'EOF'
<?xml version="1.0" encoding="utf-8"?>
<installer-gui-script minSpecVersion="2">
    <title>Signal Light</title>
    <options customize="never" require-scripts="false" hostArchitectures="arm64"/>
    <domains enable_localSystem="true"/>
    <choices-outline>
        <line choice="default"/>
    </choices-outline>
    <choice id="default">
        <pkg-ref id="com.starlight36.SignalLightApp"/>
    </choice>
    <pkg-ref id="com.starlight36.SignalLightApp"
             version="0.2.0">SignalLightApp-component.pkg</pkg-ref>
</installer-gui-script>
EOF

productbuild \
    --distribution "$BUILD_DIR/distribution.xml" \
    --package-path "$BUILD_DIR" \
    "$PKG_FINAL"

# Clean up intermediate files
rm -rf "$PKG_ROOT"
rm -f "$PKG_COMPONENT"
rm -f "$BUILD_DIR/distribution.xml"

echo ""
echo "==> Done!"
echo "    Package: $PKG_FINAL"
echo "    Size:    $(du -h "$PKG_FINAL" | cut -f1)"
