#!/usr/bin/env bash
# Check, smoke-test and package dist/DropDLStudio.app (built by build-native-macos.sh) into a DMG.
#   bash scripts/package-macos.sh [arch-label]      -> dist/DropDL-Studio-<version>-macOS-<arch>.dmg
set -euo pipefail
if [[ "$(uname -s)" != "Darwin" ]]; then echo "Run this on macOS." >&2; exit 1; fi
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$ROOT"
APP="dist/DropDLStudio.app"
ARCH="${1:-$(uname -m)}"
VERSION="$(python3 -c 'import json;print(json.load(open("frontend/package.json"))["version"])')"
[[ -d "$APP" ]] || { echo "Build the app first: bash scripts/build-native-macos.sh" >&2; exit 1; }

echo "== 1. The bundled tools must not depend on Homebrew or other build-machine paths"
BAD=0
while IFS= read -r -d '' bin; do
  if file "$bin" | grep -q 'Mach-O'; then
    if otool -L "$bin" | tail -n +2 | awk '{print $1}' | grep -E '^/(opt/homebrew|usr/local)/' ; then
      echo "   ^ needed by $bin"; BAD=1
    fi
  fi
done < <(find "$APP/Contents" -type f \( -name ffmpeg -o -name ffprobe -o -name node -o -name '*.dylib' \) -print0)
[[ $BAD == 0 ]] || { echo "The bundle still links to the build machine's libraries." >&2; exit 1; }
for tool in ffmpeg ffprobe node; do
  path="$(find "$APP/Contents" -type f -name "$tool" | head -1)"
  [[ -n "$path" ]] || { echo "Missing bundled $tool" >&2; exit 1; }
  env -i PATH=/usr/bin:/bin "$path" -version >/dev/null 2>&1 || env -i PATH=/usr/bin:/bin "$path" --version >/dev/null
  echo "   $tool runs without Homebrew: $path"
done

echo "== 2. Sign for local use (ad hoc: no Apple Developer certificate)"
codesign --force --deep --sign - "$APP"
codesign --verify --deep --strict "$APP"

echo "== 3. Launch the app and wait for its download engine"
LOG="$(mktemp)"
"$APP/Contents/MacOS/DropDLStudio" >"$LOG" 2>&1 &
PID=$!
OK=0
for _ in $(seq 1 90); do
  if ! kill -0 "$PID" 2>/dev/null; then echo "The app exited during startup:" >&2; cat "$LOG" >&2; break; fi
  if curl -fsS http://127.0.0.1:17321/api/health 2>/dev/null | python3 -c "import json,sys;d=json.load(sys.stdin);assert d.get('ok') and d.get('version')=='$VERSION'" 2>/dev/null; then OK=1; break; fi
  sleep 1
done
if [[ $OK == 1 ]]; then
  sleep 8                                            # the window process must stay up, not just the engine
  kill -0 "$PID" 2>/dev/null || { echo "The window process quit after startup:" >&2; cat "$LOG" >&2; OK=0; }
fi
kill "$PID" 2>/dev/null || true; sleep 2; pkill -f 'DropDLStudio' 2>/dev/null || true
if [[ $OK != 1 ]]; then
  echo "Smoke test failed. Desktop diagnostics:" >&2
  tail -n 80 "$HOME/Library/Application Support/DropDL/diagnostics.log" 2>/dev/null >&2 || true
  tail -n 80 "$HOME/Library/Application Support/DropDL/backend-console.log" 2>/dev/null >&2 || true
  exit 1
fi
echo "   engine $VERSION answered and the window stayed open"

echo "== 4. Package the DMG"
DMG="dist/DropDL-Studio-$VERSION-macOS-$ARCH.dmg"
STAGE="$(mktemp -d)"; cp -R "$APP" "$STAGE/DropDL Studio.app"; ln -s /Applications "$STAGE/Applications"
rm -f "$DMG"
hdiutil create -volname "DropDL Studio $VERSION" -srcfolder "$STAGE" -ov -format UDZO "$DMG" >/dev/null
rm -rf "$STAGE"
echo "Built: $ROOT/$DMG"
