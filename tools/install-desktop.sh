#!/bin/bash
# install-desktop.sh - add a launcher for the viewer to the application grid.
#
# Writes $XDG_DATA_HOME/applications/typec-pd.desktop pointing at this checkout,
# so run it again if the repository moves. Remove with:
#   rm ~/.local/share/applications/typec-pd.desktop
set -eu

HERE=$(cd "$(dirname "$0")" && pwd)
DEST="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
FILE="$DEST/typec-pd.desktop"

[ -f "$HERE/typec_gui.py" ] || { echo "typec_gui.py not found next to $0"; exit 1; }

mkdir -p "$DEST"
cat > "$FILE" <<EOF
[Desktop Entry]
Type=Application
Name=USB-C / PD
Comment=USB Type-C connectors and USB Power Delivery state
Exec=python3 "$HERE/typec_gui.py"
Icon=drive-harddisk-usb
Terminal=false
Categories=System;Utility;
Keywords=usb;typec;pd;power;delivery;charger;
StartupNotify=true
EOF

chmod +x "$FILE"
command -v update-desktop-database >/dev/null && update-desktop-database "$DEST" 2>/dev/null || true

echo "installed $FILE"
echo "launch it from the application grid, or: python3 $HERE/typec_gui.py"
