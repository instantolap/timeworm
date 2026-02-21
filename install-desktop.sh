#!/usr/bin/env bash
# Install TimeWorm desktop integration (icon + .desktop file)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

ICON_SRC="$SCRIPT_DIR/data/icons/hicolor/scalable/apps/de.tbe.timeworm.svg"
DESKTOP_SRC="$SCRIPT_DIR/de.tbe.timeworm.desktop"

ICON_DIR="$HOME/.local/share/icons/hicolor/scalable/apps"
DESKTOP_DIR="$HOME/.local/share/applications"

mkdir -p "$ICON_DIR" "$DESKTOP_DIR"
cp "$ICON_SRC" "$ICON_DIR/de.tbe.timeworm.svg"
cp "$DESKTOP_SRC" "$DESKTOP_DIR/de.tbe.timeworm.desktop"

# Update icon cache if available
if command -v gtk-update-icon-cache &>/dev/null; then
    gtk-update-icon-cache -f -t "$HOME/.local/share/icons/hicolor" 2>/dev/null || true
fi

echo "TimeWorm desktop integration installed."
echo "  Icon:    $ICON_DIR/de.tbe.timeworm.svg"
echo "  Desktop: $DESKTOP_DIR/de.tbe.timeworm.desktop"
