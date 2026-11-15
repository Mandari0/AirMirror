#!/usr/bin/env bash
# Build a portable UxPlay bundle (exe + DLL closure + GStreamer plugins).
# Run inside MSYS2 UCRT64:  C:\msys64\msys2_shell.cmd -ucrt64 -here -c "bash build-portable.sh"
set -euo pipefail

SRC=/ucrt64
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DST="$ROOT/build/portable/uxplay"
CLOSURE="$(mktemp -t airmirror-closure.XXXXXX)"

echo "==> clean"
rm -rf "$DST"
mkdir -p "$DST/bin" "$DST/lib/gstreamer-1.0" "$DST/libexec/gstreamer-1.0" "$DST/share/glib-2.0/schemas"

echo "==> uxplay.exe"
cp -f "$SRC/bin/uxplay.exe" "$DST/bin/"

echo "==> gstreamer plugins"
cp -f "$SRC"/lib/gstreamer-1.0/libgst*.dll "$DST/lib/gstreamer-1.0/"
cp -f "$SRC/libexec/gstreamer-1.0/gst-plugin-scanner.exe" "$DST/libexec/gstreamer-1.0/"

echo "==> gsettings schemas"
cp -f "$SRC"/share/glib-2.0/schemas/* "$DST/share/glib-2.0/schemas/"

echo "==> dependency closure"
targets=("$SRC/bin/uxplay.exe" "$SRC/libexec/gstreamer-1.0/gst-plugin-scanner.exe")
for f in "$SRC"/lib/gstreamer-1.0/libgst*.dll; do targets+=("$f"); done

ldd "${targets[@]}" 2>/dev/null \
  | awk '{for(i=1;i<=NF;i++) if ($i ~ /^\/(ucrt64|mingw64)\/bin\//) print $i}' \
  | sort -u > "$CLOSURE"

count=$(wc -l < "$CLOSURE")
echo "    DLLs to copy: $count"

while read -r f; do
  [ -f "$f" ] && cp -f "$f" "$DST/bin/"
done < "$CLOSURE"
rm -f "$CLOSURE"

echo "==> done"
du -sh "$DST"
find "$DST" -type f | wc -l
