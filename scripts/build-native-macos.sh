#!/usr/bin/env bash
# Experimental native macOS target. Run on the architecture being distributed.
set -euo pipefail
if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "This target must be built on macOS; cross-compiling from Windows/Linux is unsupported." >&2
  exit 1
fi
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
PYTHON_BIN="${DROPDL_BUILD_PYTHON:-python3}"
"$PYTHON_BIN" -c 'import sys; assert sys.version_info >= (3,11), "Python 3.11+ is required"'
for tool in ffmpeg ffprobe node; do
  command -v "$tool" >/dev/null || { echo "Install $tool first (see MACOS.md)." >&2; exit 1; }
done
node -e 'if(Number(process.versions.node.split(".")[0])<22)process.exit(1)' || { echo "Node.js 22+ is required." >&2; exit 1; }
[[ -f frontend/dist/index.html ]] || { echo "Build the frontend first." >&2; exit 1; }
"$PYTHON_BIN" -m venv .venv-macos-build
BUILD_PYTHON="$ROOT/.venv-macos-build/bin/python"
"$BUILD_PYTHON" -m pip install -r backend/requirements.txt pyobjc pillow
"$BUILD_PYTHON" -c 'import json; from pathlib import Path; assert json.loads(Path("frontend/package.json").read_text())["version"] == json.loads(Path("frontend/dist/build.json").read_text())["version"], "Rebuild the interface for this version"'
# Supplying an ICO lets PyInstaller convert the same artwork into a Mac ICNS.
# Bundled binaries and their discovered dylibs must match the host architecture.
"$BUILD_PYTHON" -m PyInstaller --clean --noconfirm --onedir --windowed \
  --name DropDLStudio --osx-bundle-identifier org.dropdl.studio \
  --icon installer/dropdl.ico --paths backend \
  --add-data 'installer/dropdl.ico:installer' \
  --add-data 'frontend/dist:frontend/dist' \
  --add-binary "$(command -v ffmpeg):bin" \
  --add-binary "$(command -v ffprobe):bin" \
  --add-binary "$(command -v node):bin" \
  --collect-all yt_dlp --collect-all yt_dlp_ejs --collect-all webview \
  --collect-all uvicorn --exclude-module PyQt5 --exclude-module PyQt6 \
  --exclude-module PySide2 --exclude-module PySide6 backend/desktop.py
echo "Built: $ROOT/dist/DropDLStudio.app"
echo "Test the complete bundle on a clean Mac before distributing it. See MACOS.md."
