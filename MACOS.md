# macOS build target — 1.0.0

The Windows release is the packaged deliverable. This release also includes an
**experimental macOS build target**, not a tested or signed Mac installer.
Build and test it on an actual Mac before relying on it. Apple Silicon and Intel
require separate native builds; this script does not produce a universal binary.

## Build on your Mac

1. Extract the source ZIP. Use macOS 13 or later and Python 3.11+ from python.org
   or Homebrew, matching your Mac's architecture. Do not use the system Python.
2. Install Node.js 22+ and FFmpeg/ffprobe. With an existing Homebrew installation:
   `brew install python@3.12 node ffmpeg`.
3. Run `bash scripts/build-native-macos.sh` in the project folder. It creates an
   isolated build environment, installs the declared Python/Cocoa dependencies,
   and uses the prebuilt interface. Internet access is required for dependencies.
   To choose Python, set `DROPDL_BUILD_PYTHON` to its executable path.
4. The result is `dist/DropDLStudio.app`. Copy the **complete app bundle** into
   Applications; open it from Finder. The bundle includes Python and collects
   FFmpeg/ffprobe and Node from the builder, including discovered linked libraries.
   Test that they work on a clean Mac without Homebrew.

The Mac host uses Cocoa through pywebview, native pickers, the system media player
and Finder Reveal. It looks for tools in its bundled `bin` directory and the two
standard Homebrew prefixes, so Finder launch does not require a shell PATH.
User data is in `~/Library/Application Support/DropDL`; media defaults to
`~/Downloads/DropDL`. Users who previously ran the source on Mac may have data in
`~/DropDL`; retain a backup and migrate that folder with the app closed if needed.

## Required on-device checks

- Finder launch with no terminal; all tools found; correct Dock/application icon.
- Video, audio and playlist downloads; pause/resume and interrupted recovery.
- Native imports, Finder drops, library collections and missing-file relinking.
- English and Arabic layout; editor opening, independent tracks, preview sound,
  exporting MP4/audio into a selected folder, cancellation and original preservation.
- Native mini-player resizing, detach/attach and system-player default.
- Clean shutdown and relaunch with queue/library/project/settings retained.

The native bundle currently requires an **application rebuild to update yt-dlp**;
the source/online Windows install keeps its existing automatic stable engine
updater. This limitation is visible in engine status. Mac code signing and Apple
notarization are not configured here, and Gatekeeper may warn about an unsigned
download. No security settings are changed by this script. Binary redistribution
must include applicable third-party licenses; review your FFmpeg build's license
configuration before publishing a Mac bundle.

Build references: [pywebview installation](https://pywebview.flowrl.com/guide/installation),
[pywebview freezing](https://pywebview.flowrl.com/guide/freezing), and
[PyInstaller bundle options](https://www.pyinstaller.org/en/stable/usage.html).
