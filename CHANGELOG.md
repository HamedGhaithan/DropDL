# Changelog

All notable changes to DropDL Studio. The newest release is at the top.

## 2.3.0 — a professional editing workspace

The video editor has been rebuilt around the layout editors know from Adobe Premiere Pro's Editing workspace. Every existing editing feature works as before: multi-track timeline, move/cut/roll/slip, trimming, snapping, undo/redo, titles and captions, soundtrack, recovery, export presets and folders.

### Workspace
- **Effect Controls** (top left) holds the clip properties, with exact values in a blue monospace style.
- **Program monitor** (top right) shows "Program: Sequence 01" with the resolution and frame rate.
- **Project panel** (bottom left) holds the media bin.
- **Tools palette** sits between the Project panel and the timeline.
- **Timeline** in the centre of the bottom row.
- **Audio meters** on the far right.
- Panels have tabbed headers and charcoal surfaces in dark mode, with a matching light theme and a full Arabic right-to-left mirror. Time-based controls (ruler, transport) stay left-to-right, as in professional editors.
- The header has a centred "Editing" workspace label with the project name, icon Undo/Redo, Shortcuts, Project, Media, Guide and a blue **Export** button.

### Program monitor
- **SMPTE timecode** (HH:MM:SS:FF) in blue for the current position, plus the sequence duration.
- A **program scrub bar** you can click or drag, with a playhead marker. It is keyboard accessible.
- **Transport:** go to start, previous frame, a round play/pause button, next frame, go to end.
- **J / K / L:** J goes back one second, K pauses, L plays. Space, the arrow keys, Home/End, I/O, S and Delete work as before.
- **Title and action safe margins** overlay, with a centre cross, toggled from the monitor.

### Timeline
- **Vertical tools palette** (Selection V, Razor C, Rolling edit N, Slip Y) with tooltips and shortcut badges.
- **Sequence tab** with a large blue timecode, clip count, duration and frame rate.
- **Timecode ruler** with a Premiere-style blue playhead head.
- **Clips** show three layers:
  - a lavender title bar
  - a filmstrip of real frames
  - a green **audio waveform of exactly the trimmed range**, rendered from the source (new `GET /api/jobs/{id}/waveform?variant=strip`, 4000×96, cached)
- **Track headers** use mute, show/hide and lock icons. Snapping is shown as icon toggle pills.

### Audio meters
- **Live stereo peak meters** fed by the preview mixer through Web Audio analysers, with a −60 to 0 dB scale, green/yellow/red zones, peak hold and a click-to-reset clip indicator.

### Project panel
- **List view** or **icon view** (remembered). Rows are compact, and "Add soundtrack" appears on hover.

### Fixes
- **Right-click menus in the main window did not work in 2.2.0.** They only activated inside the old layout's root element. Fixed, and covered by the library browser test.
- The detached player now guards its `localStorage` reads like the rest of the app.
- The real-browser test suites (`editor-browser`, `library-browser`, `player-browser`) were Linux-only (hard-coded `/tmp` paths and Playwright location). They now use the system temp folder and run on Windows with Microsoft Edge: point `DROPDL_PLAYWRIGHT` at a module exporting a Playwright `chromium` that launches `channel: 'msedge'`.

### Verification for 2.3.0
- Backend: 232 tests pass (1 skipped) on Windows 11, including the new waveform strip variant.
- Real browser (Microsoft Edge):
  - **Editor suite:** paused startup with no media requests, 100-clip projects, drops, lock/mute/hide, undo, grouped sliders, snapping, export presets, playback, English/Arabic, no page errors.
  - **Library suite:** passes, including the context menu.
  - **Player suite:** passes. It failed once while running immediately after the editor suite and passed on two reruns, so it is timing-sensitive.
- jsdom UI suite and the timeline, clip-time, export frame-rate and new timecode model checks pass.
- Checked visually with the real backend at 1600×940: dark, light and Arabic; playback with the meters reading live levels; icon view; safe margins.
- Not verified here: the packaged WebView2 window (meters depend on WebView2 audio, which uses the same Chromium engine).

## 2.2.0 — a completely new interface: the "command center"

The main window has a new structure, not a reskin. Every feature from 2.1 is still here (queue tools, selection, priorities, playlists, batch archives, recovery, Convert, Clip Studio, Library, Preferences, tours, command palette, mini player), along with dark/light themes, English/Arabic RTL and the 2.1 logo and fonts.

### Layout
- **Icon rail** (left; right in Arabic) replaces the wide sidebar: Downloads (with a live badge counting active downloads), Convert, Studio and Library, plus a theme switch, Preferences and Quick tour at the bottom.
- **Smart bar** across the top replaces the old capture box, search field and palette button:
  - Paste one or more links and it offers **Download** (or **Add N links**); Enter opens the download sheet already filled in and analysed.
  - Type anything else and it **filters your downloads** as you type.
  - On an empty bar, Enter (or Ctrl K) opens the command palette. `/` still focuses it.
- **Filter pills** with live counts (All, In progress, Completed, Needs attention, Video, Audio) replace the sidebar filter list.
- **Task cards** replace the table. Each card shows:
  - a large thumbnail (real poster or cover art)
  - the title, source and format
  - a status pill and the current phase
  - one progress line with %, size, speed and ETA
  - the actions for its state
  
  An active download is marked with an accent edge and a failed one with a red edge. Drag-to-reorder, multi-select and pagination are kept.
- **Inspector panel** on the right:
  - **Nothing selected:** the session overview (in progress, completed, live speed graph, total saved), overall progress, the tools and batch ZIPs.
  - **A task selected:** a large poster, title, state, the main actions (Play is the main one), URL, save location, attempts and size, priority/schedule controls, error advice, and Copy link / Save.
- **Status bar** along the bottom: engine status, live download speed, active and queued counts, parallel limit, free disk space, app and yt-dlp versions, and the version-mismatch warning.
- **Add download is a wide centered sheet** with a two-column form (source and presets on one side; output, save folder and clip maker on the other) instead of a narrow side drawer. Preferences remains a side panel.
- **Responsive:**
  - Below about 1,120 px the inspector becomes a slide-over that appears when you select a task.
  - Below 900 px cards stack into two rows.
  - On very narrow windows the rail becomes a bottom tab bar.

### Installer
- `DropDL-Setup.exe` 2.2.0 is compiled (NSIS 3.11 on Windows). It reads the installed version and offers **Upgrade** for older releases (0.5.0 and later, including 1.0.2), **Repair** for the same release, and blocks downgrades. Before replacing files it backs up app files and your profile to `%LOCALAPPDATA%\DropDLackups`, stops only DropDL's own processes, and keeps downloads and the Python environment.
- Fixed a build failure on Windows: `installer/dropdl.nsi` used forward-slash payload paths, which makensis on Windows rejects (the script had only been compiled on Linux). `Build-Installer.bat` now works on Windows.
- The quiet launcher `DropDL.exe` is rebuilt with the new icon and the 2.2.0 version stamp. The setup is unsigned, so Windows may show an Unknown publisher / SmartScreen prompt.

### For developers
- The shell is in `App.tsx` (rail, smart bar, cards, inspector and status bar are built from the same state and handlers as before) and `shell.css`, loaded after `design.css` and `editor-design.css`.
- The old home-page hero (`CaptureDeck`) is no longer used; the smart bar does its job.
- Class names that features and tests rely on were kept (`row-actions`, `play-button`, `mini-play-button`, `status-badge`, `selection-cell`, `workspace-nav`, `nav-tool`, `manager-header`, the `tour-*` IDs), so the tour, right-click menu and selection bar work unchanged.

### Verification for 2.2.0
- Backend: 231 tests pass (1 skipped) on Windows 11.
- Interface: TypeScript/Vite production build. The jsdom UI regression suite passes in English and Arabic on the new structure (198-task queue and pagination, selection, popups, tour, converter/library), plus new checks:
  - typing in the smart bar filters the cards
  - pasting several links offers a batch add and does not filter the list
  - selecting a card opens the inspector, and closing it brings the overview back
- Timeline, clip-time and export frame-rate model checks pass.
- Checked visually against the real backend in headless Edge at 1440×900: dark and light themes, English and Arabic RTL, the downloads list, the inspector, smart-bar link detection, the Add download sheet with a real analysed link, Preferences, Convert, Library, a live rate-limited download, and the editor. The phone layout was seen in a 268 px wide browser pane.
- Not verified here: the packaged WebView2 window and tray, and the compiled installer/launcher icons (NSIS is not installed on the build machine).

## 2.1.0 — new identity, new design, a better editor

### New logo
- A drop with a download arrow cut out of it, on an aqua → blue → violet tile. It replaces the previous mark in the window, sidebar, editor, home screen, favicon and the Windows icon.
- `installer/dropdl.ico` is regenerated with the same structure Windows Forms needs (seven 32-bit bitmap frames, 16–256 px; small sizes use a tighter tile for legibility). Rebuild it any time with `node ../scripts/build-icons.mjs` from `frontend/`.
- `DropDL.exe` (the quiet launcher) and the setup program embed their icon at compile time, so run `Build-Installer.bat` to get the new icon on shortcuts and in Apps & Features.

### "Aurora" design system
- One shared set of design tokens (colours, radii, shadows, focus rings, type scale) now drives the main window, the editor and the detached player, in dark and light themes. It's loaded as the last stylesheet (`design.css`, `editor-design.css`), so the earlier 1.x layers stay as a fallback.
- **Bundled fonts:** Inter for Latin text and IBM Plex Sans Arabic for Arabic, so the app looks the same on every PC instead of depending on installed fonts. Arabic mode uses the Arabic face first.
- **New default accent "Aurora"** (the logo blue). Existing users keep the accent they picked; Mint, Iris, Ocean, Rose and Amber remain.
- Readability: the base text size went from 11–12 px to 13–14 px, contrast is higher, and labels and numbers use consistent weights and tabular figures.
- **Sidebar:** brand wordmark, clear selected state with an accent bar, count pills, and a calmer engine status card.
- **Home:** a quieter hero with the new emblem instead of tilted, overlapping decorative tiles; cleaner quick-tool and stat cards.
- **Queue:** a sticky table header; coloured status pills (green done, blue active, amber waiting, red failed); a slimmer progress bar with a flowing live state; long titles truncate instead of running into the Status column.
- **Library:** cards show a real picture: a representative video frame instead of the black first frame, and the **embedded album art for audio files**. Actions are regrouped into three main buttons plus quiet links.
- **Drawers and dialogs:** consistent headers and footers. Fixed in 2.0: the Add download drawer overflowed horizontally. Download progress toasts now step aside while a drawer or dialog is open.
- The animated background wash is removed; motion is shorter and still respects the reduced-motion setting.

### Editor fixes
- **Exports no longer default to 30 FPS.** The frame rate now follows the source (23.976 → 24, 29.97 → 30, 59.94 → 60). Previously a 24 FPS film exported at 30 FPS, which duplicated frames and caused judder. Verified with a real export: H.264 at exactly 24/1 FPS.
- **Track labels line up with their tracks.** Lanes were 94 px in code but labels were styled at 110 px, so V1/V2/V3 drifted out of line. Lanes are now a compact 78 px, so all three tracks fit and V1 isn't cut off.
- **Timeline clips show a filmstrip** of real frames, with a name bar and duration, instead of an empty block.
- **Media bin:** files are listed first (with thumbnails, including album art), followed by compact filter chips. Previously filters and help text pushed the file list out of view.
- **Notices float.** "Export started" and error messages no longer push the whole editor down and squeeze the media bin.
- **Export dialog:** a solid sticky footer so the Start button no longer sits over the output summary.
- Removed a leftover "Empty timeline · zoom changes…" label that floated over the top track.
- Restyled header, transport controls, tool groups, inspector tabs and playhead on the shared design system, in both themes and both languages.

### Under the hood
- New endpoint `GET /api/jobs/{id}/poster`. Library thumbnails share the same `posters.py` routine: FFmpeg's `thumbnail` filter about 10% into a video, or the attached cover art for audio. Earlier posters are cached separately, so old black thumbnails are not reused.
- `theme.ts` replaces three copy-pasted accent tables (main window, editor, player).

### Verification for 2.1.0
- Backend: 231 tests pass (1 skipped) on Windows 11, including new tests showing that posters skip a black opening, that audio posters use the embedded cover (and audio without a cover gives none), and that the poster endpoint works.
- Interface: TypeScript/Vite production build. The jsdom UI regression suite (English/Arabic, 198-task queue), timeline/clip model checks and the new export frame-rate check all pass.
- Checked visually in a browser against the real backend: dark and light themes, English and Arabic RTL, home, queue, Add download drawer, library, editor and export dialog. A real editor export was confirmed at 24 FPS. The new icon was decoded by Windows' own System.Drawing at every size.
- Not verified here: the packaged WebView2 window, the tray icon and the compiled installer/launcher icons (NSIS is not installed on the build machine).

## 2.0.0 — the self-healing downloader

2.0 focuses on two things: downloads that finish, and the extras people actually want. Everything from 1.0.2 is retained; queues, libraries and settings upgrade in place.

### Downloads that finish
- **Format fallbacks instead of hard filters.** 1.x asked sites for e.g. `bestvideo[ext=mp4][height<=720]` and failed with *Requested format is not available* when a site didn't match exactly. 2.0 ranks every offered format with yt-dlp's sorting and always resolves to something; if a site still refuses, the task retries once with the plainest selector.
- **Self-healing post-processing.** When a step fails after the media is already downloaded, DropDL repairs only that step and continues: incompatible codecs are re-encoded instead of remuxed (e.g. Theora into MP4), and optional extras (cover art, SponsorBlock, embedded subtitles, unreadable browser cookies) are dropped one at a time. The failing step is identified from the live post-processor, so the right fix is tried first.
- **403 Forbidden → retry as a browser.** Downloads and link inspection retry with Chrome impersonation (curl-cffi) and a cleared extractor cache.
- **Stall watchdog.** A transfer that receives no data for 90 seconds (configurable, or off) is restarted from its partial file instead of hanging forever.
- **Smarter automatic retries.** Network errors, rate limits (HTTP 429), stalls and worker crashes retry with exponential back-off (10 s → 5 min, longer for rate limits), up to 4 times by default (0–10). Permanent failures — unavailable, private, geo-blocked, unsupported — are not retried. Waiting tasks show a live "Auto-retry 2 in 0:38" countdown.
- **Crash-safe resume.** Closing the window now records restart intent *before* stopping workers, so active downloads are always recovered as resumable (1.x could race and mark them "cancelled"). If the backend dies abruptly (crash, Task Manager), each download worker notices within about a second, stops cleanly and keeps its partial file — no orphaned process writing the same file after relaunch. Verified on Windows: a hard-killed backend's worker exited in 3.4 s and the relaunched app resumed at 40.9 of 61.9 MB.
- **Empty-file guard.** A failed FFmpeg step can leave a 0-byte output; it is removed before every attempt so a retry can't mistake it for a finished download.
- **One continuous progress bar** for merged video+audio downloads (1.x went 0→100% twice), with an overall ETA.
- **Clearer errors.** New categories with specific advice: rate limited, bot check ("Sign in to confirm you're not a bot"), geo-blocked, no format, forbidden, stalled. Unexpected internal errors are named and their traceback is written to the task's `worker.log`.

### Smart extras (Add download → Advanced download options)
- **Video codec:** *Automatic* (MP4 prefers H.264/AAC so files play in every player, phone and editor), *H.264 — maximum compatibility*, or *Best quality* (AV1/VP9 allowed). When a site publishes no codec data, the MP4 container is preferred.
- **SponsorBlock** for YouTube: mark sponsor/intro/outro/self-promo segments as chapters, or remove sponsors, self-promotion and interaction reminders. Removal is automatically downgraded to marking when a clip range is set, so the range never shifts.
- **Embed cover art** into MP3, M4A, Opus, FLAC, MP4 and MKV (on by default; skipped for WebM/WAV).
- **Embed subtitles** inside the video (when subtitle languages are set).
- **More audio formats:** MP3, M4A, **Opus, FLAC, WAV**, with bitrate choice (best, 320, 256, 192, 128 kbps) for lossy formats.
- **Size estimates** next to each quality after Analyze (e.g. `480p · ~16.7 MB`).
- Your choices are remembered for the next download.

### Preferences → Network & reliability
- **Parallel downloads** 1–8, applied immediately without restarting (1.x needed an environment variable).
- **Connections per download** (fragment concurrency) 1–16.
- **Automatic retries** 0–10 and **stall restart** timeout (45 s–5 min, or never).
- **Proxy:** `http://`, `https://`, `socks4://`, `socks5://`, `socks5h://` (with optional `user:pass@`), validated both in the form and by the backend. Used by downloads, link inspection and playlist loading.
- **Use cookies from browser:** Firefox, Edge, Chrome, Brave, Opera, Vivaldi or Chromium. Firefox is the most reliable on Windows; Chromium browsers lock/encrypt their cookie stores while open, and DropDL continues without them if they can't be read. Cookies stay on your PC.
- **Force IPv4** for networks with broken or slow IPv6 routes.
- **Always present as a desktop browser** (otherwise impersonation is used only after a 403).
- Network settings are snapshotted when each task starts; changes apply to tasks started afterwards.

### Performance
- The queue poll is now revision-based: when nothing changed the backend answers `{"unchanged": true}` and the interface skips re-rendering, so an idle 1,000-task queue no longer re-renders every 1.2 s. `/api/health` also reports free disk space, the engine version and the live parallel-download limit.

### Verification for 2.0.0
- **Backend:** 228 tests pass (1 skipped) on Windows 11 (Python 3.12), including 38 new 2.0 tests: format planning, every extras combination, network option mapping, each self-healing step and its order, merged progress, error classification, retry back-off/limits, live parallel slots, a real-subprocess stall watchdog, revision sync, shutdown/crash recovery, parent-death detection, settings validation and API round-trips. One Linux-only native drop test is skipped on Windows.
- **Interface:** TypeScript/Vite production build; the jsdom UI regression suite (198-task queue, selection, converter/library, English/Arabic) and timeline/clip model checks pass. The Playwright editor/library/player scripts were not run (Playwright is not a project dependency); those areas were not changed.
- **Real downloads on Windows 11** with the native backend (isolated profile): SoundCloud → MP3 at exactly 192 kbps, FLAC and Opus, each with 600×600 embedded cover art; Dailymotion → H.264/AAC MP4 with cover art and title/artist metadata (needs working browser impersonation); archive.org → H.264/AAC MP4 with cover art, recovered through the new self-healing after the site's codec-less listing led to a Theora file; a 62 MB archive.org file hard-killed mid-transfer and resumed from its partial after relaunch.
- **Not verified here:** YouTube downloads (this machine's IP received YouTube's "confirm you're not a bot" page; 2.0 now explains this and points to browser cookies), the NSIS installer (NSIS isn't installed on the build machine — run `Build-Installer.bat`), and the packaged WebView2 window/tray.
- The test suite now isolates its data folder (`tests/conftest.py`); 1.x tests wrote into the real `%LOCALAPPDATA%\DropDL` profile when run on a machine with DropDL installed. Four 1.x tests that only passed on Linux/UTC were fixed (text encoding, local-time date folders, a Linux-only native path, a path-length-dependent status code).

### Developer notes
- New modules: `frontend/src/DownloadExtras.tsx`, `frontend/src/NetworkPanel.tsx`, `frontend/src/v2.css`, `tests/test_v2.py`, `tests/conftest.py`.
- Main backend changes: `downloader.py` (format planning, `build_options`, `fallback_for`, `ProgressTracker`), `media_worker.py` (stall watchdog, `ParentWatch`), `scheduler.py` (retry policy, live slots), `settings.py` (`NETWORK_DEFAULTS`), `jobs.py` (revisions, new fields), `task_errors.py`, `main.py`.
- curl-cffi's DLL fails to load when the Python environment lives in a very long path ("The filename or extension is too long"); impersonation is then silently unavailable. The default install path is fine.

Continues the supplied custom desktop version and all changes through 0.15.0. This is the native Windows application with a local Python backend, not the Docker web edition. No Docker installation is required.

## 0.6.1 fixes

Download progress snapshots retry transient Windows file-lock failures rather than letting the progress thread exit. Unknown-size downloads and processing phases use animated progress bars; byte counts remain visible without a fabricated percentage. Live transfer tests exercise intermediate updates across a real child process.

The existing logo is packaged as traditional Windows ICO bitmap frames at seven sizes. The native WinForms window explicitly reapplies the icon after creation, in addition to the process identity and launcher icon. Native taskbar behavior still requires Windows verification.

Completion popups now have **Open downloaded** (**فتح الملف المُنزّل**), which opens the registered finished video/audio file in the operating system's default player. The command accepts a completed task ID only, checks that its media file exists, and rejects executable/non-media files. Save a copy remains available in task details.


## Desktop 0.6.2 — verified release and manual selection

This release continues the desktop 0.6.0 feature set: media converter with presets and local imports, Clip Studio, durable media library, pause/resume and scheduling, queue ordering, subtitles, metadata, subscriptions, private cookies and browser inbox. It retains 0.6.1 progress reporting, native icon and Open downloaded fixes. The web/Docker package is separate.

- Check task rows individually, select the current page, or select all matching results (up to 500). Selection persists across pages and filters; the count covers all chosen tasks. Actions apply only to eligible selected tasks: pause, resume/retry, cancel, save completed files as a ZIP, or remove queue records. Removing records cancels selected active tasks and leaves downloaded files in the media library.
- In the media library, check individual files or select matching results. Save copies as one ZIP, remove references, or explicitly confirm deletion of selected output files. Imported originals cannot be deleted by this action. Missing files can still have their references removed. File operation errors leave unsuccessful items selected.
- The window and sidebar identify desktop 0.6.2. The download engine reports its version; the host checks that the running engine and compiled interface match the release. The interface index is served without caching and the window opens a versioned URL, so persistent Windows WebView profiles do not silently reuse an older interface.
- The installer clears obsolete UI assets before copying the new build. Packaging refuses an interface whose build manifest differs from the source release. Close every DropDL window before running the installer. Launch the updated **DropDL Studio** shortcut; the window should say **DropDL Studio 0.6.2**.

Task deletion means removing task records; actual downloaded file deletion is a separate confirmed media-library operation. Media originals and user settings/history remain outside the installer cleanup.


## Desktop 0.6.3 — upgrade and repair

Run the new `DropDL-Setup.exe` directly over an existing installation; no uninstall is needed. Setup uses the registered per-user installation path, with a fallback to the standard DropDL folder. Supported desktop releases (0.5.0 onward) upgrade in place. The same-release installer offers Repair. A newer installed release blocks downgrading; unknown or incompatible version metadata stops preparation before replacing files.

- Maintenance shows the installed version, target version and existing location in English or Arabic. Upgrade retains the Python environment and checks prerequisites; Repair reinstalls required Python libraries and restores packaged app files and shortcuts.
- Setup stops processes matching the exact installed DropDL script paths before changing files, including orphaned backends. Unrelated Python processes and programs using port 17321 are not stopped. Active DropDL downloads will be interrupted.
- Existing app files and saved profile files are backed up under `%LOCALAPPDATA%\DropDL\backups`. Downloads and the Python environment remain in place. These backups are manual recovery copies, not automatic rollback of prerequisite changes. A failed prerequisite step reports `Setup-Log.txt`; rerun setup after resolving that error.
- After success, Start Menu → DropDL Studio → **Repair DropDL Studio** uses a cached same-release installer. The Windows uninstall registration also exposes a maintenance command. Repair requires internet access. It restores program files and dependencies, not damaged personal settings or queue records.
- Desktop and Start Menu shortcuts are recreated with the actual installed `DropDL.exe` as their target. The launcher runs PowerShell directly and no longer invokes `wscript.exe`. Existing taskbar pins may need to be unpinned and pinned again from the new shortcut.

### Signing release builds

The delivered build is unsigned. Registering an app in Windows Installed Apps does not grant SmartScreen trust. Public signing requires a verified publisher and a certificate or signing service trusted by Windows; self-signed certificates do not establish public trust. Newly signed releases may still show SmartScreen warnings while reputation develops. The build does not modify Defender, SmartScreen, certificate trust, or security exclusions.

On Windows with NSIS and an existing trusted code-signing certificate in `CurrentUser/My`, build with:

```powershell
python scripts/build-installer.py --certificate-thumbprint YOUR_CERTIFICATE_THUMBPRINT
```

This signs and verifies the launcher before embedding it, then signs and verifies the final installer. Failure to sign aborts the build. Hardware or cloud signing credentials must be provisioned through your certificate provider. Never include private keys or credentials in this source archive. See Microsoft's current [SmartScreen guidance](https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/smartscreen-reputation) and [signing options](https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/code-signing-options).


## Desktop 0.6.4 — play from the download list

Completed tasks now have a visible **Play / تشغيل** button in the Actions column. It opens the saved video or audio in the operating system's default media player, without downloading or creating a preview task. The existing clip and folder actions remain available.

Clicking **Open downloaded** on a completion notification dismisses that notification immediately. Clicking the matching task's Play button also dismisses its notification. Native open failures appear as an error in the app while the task remains completed and available for retry. Opening historical completed tasks does not produce new completion notifications.

Validation: production TypeScript/Vite build, English/Arabic UI checks for list playback, audio playback, popup dismissal and failed-open recovery, plus existing queue, playlist, selection and converter UI checks. Actual default-player launching uses the existing native bridge and still requires Windows verification. Upgrade/repair and shortcut behavior from 0.6.3 are retained.


## Desktop 0.7.0 — playback, diagnostics and organization

Play on a completed task or Open downloaded on its notification now opens the floating mini-player. It supports video and audio, seeking, volume, speed, ten-second jumps, minimization, and remembered playback positions. Library files and completed conversions use the same player. The notification disappears immediately when opened. Starting a clip preview closes the mini-player to avoid simultaneous playback. Playback depends on WebView codec support; Open in desktop player remains available for unsupported formats.

Preferences → File organization adds optional creator, playlist, date or media-type folders, plus original, title or date-and-title filenames. Existing optional site folders still work. Save settings before adding new tasks: queued tasks retain the rules they were created with, and existing files are not moved. Missing creator/playlist metadata uses fallback folders. Names are sanitized for Windows and include a task identifier to avoid overwrites.

Preferences → Diagnostics checks dependencies, profile access and destination storage, and shows recent failed tasks and possible historical startup findings. Save diagnostic report exports bounded logs and health checks, omitting cookies and queue history and redacting recognized credentials and URLs. Review the report before sharing. On Windows, Run installer repair opens the cached same-release installer after an interruption confirmation; the existing Start Menu repair shortcut also remains available when the engine cannot start.

This remains the desktop package. Upgrade and repair behavior from 0.6.3 is retained. Validation covers backend organization, persistence, streamed-media byte ranges and diagnostic redaction, plus English/Arabic interface controls. Native Windows codec support, external-player launching and installer repair still need verification on Windows.


## Interface upgrade (0.7.0 UI refresh)

- **Command palette** (`Ctrl+K`): search and run any action — new download, pause/resume queue, retry failed, clear finished, copy links of selected/shown tasks, open the download folder, jump to any view or tool, change theme, language or accent, open the tour. English and Arabic.
- **Paste or drop a link anywhere**: pasting a URL while no field is focused, or dragging a link onto the window, opens Add download with it filled in. Several links switch to Batch automatically; YouTube playlists switch to Playlist.
- **Live dashboard**: four stat cards (in progress, completed, live speed with a rolling speed graph, total saved).
- **Shortcuts**: `Ctrl+K` palette, `Ctrl+N` add, `/` focus queue search, `?` shortcut list, `Esc` close.
- **Refreshed design**: new colour tokens, accent-tinted backgrounds, gradient primary buttons, animated progress sheen on active downloads, status dots, modern sidebar highlight, blurred modals, improved light theme, RTL-correct throughout, reduced-motion respected.
- New files: `frontend/src/upgrade.tsx`, `frontend/src/upgrade.css`; `frontend/dist` is rebuilt. `scripts/build-frontend-offline.sh` is an esbuild-based fallback build; the normal `npm run build` (Vite) works unchanged.


## 0.8.0 — motion, UX and productivity upgrade

- **Motion:** slow aurora background, staggered row/card entrances, count-up stat numbers, cursor-following card glow, button shine, ring pulse on the empty state, spring toasts, and confetti when the queue finishes. All of it respects reduced-motion.
- **Overall progress bar** across every active download with a combined ETA; the window title shows live speed and active count (`↓ 5.2 MB/s · 3`).
- **Auto-analyze on paste/drop:** a single pasted link opens Add download and is analyzed immediately.
- **Clipboard watcher (opt-in):** copy a link anywhere; when you return to DropDL it offers to download it.
- **Completion chime and desktop notifications** (both toggleable from the command palette).
- **Bandwidth profiles:** total bandwidth unlimited / 5 MB/s / 1 MB/s from the palette.
- **Export history to CSV** from the palette.
- **Collapsible sidebar** (`[`) and **compact density** mode, both remembered.
- New files: `frontend/src/upgrade2.tsx`, `frontend/src/upgrade2.css`.

### Building the installer (Windows)

Double-click **`Build-Installer.bat`**. It installs NSIS via winget if needed, rebuilds the interface when Node is present (otherwise uses the prebuilt `frontend/dist`), and writes **`dist\DropDL-Setup.exe`**.

## 0.8.2 — custom edition visual merge

This release uses the supplied DropDL Studio 0.8.0 custom edition as its base. The latest ink/mint desktop design and rounded D/download logo are applied to the app, favicon, native Windows icon and installer. The custom edition's command palette, clipboard prompts, URL intake, speed graphs, four statistics cards, completion feedback, collapsible sidebar, CSV export and compact preference remain intact. Appearance includes matching dark/light palettes, color choices and reduced CSS motion.

Download, playlist, conversion, library, clip, queue and API implementations are retained; backend changes only update release metadata. The installer retains upgrade/repair detection, uninstall support and direct executable shortcuts. The launcher retains the quiet startup fix. Setup requires internet access to install or repair prerequisites.

## 0.8.3 — direct clipping and Windows playback

Play and Open downloaded now use the Windows default media application. Separate Mini player controls open the in-app player paused. Downloaded and imported files open directly in the clip editor without conversion or a download queue entry; if the browser cannot decode the original, a compatible preview is prepared by a separate local editing worker. Clip exports use the same editing worker and a corner progress indicator, without waiting behind or entering the download list. Exporting still creates a new media file; the original is preserved.

## 0.8.4 — dedicated Clip Studio

Clip actions open a separate native desktop window. The single-source segment timeline supports trim, split, duplicate, drag reorder, segment speed changes with a speed graph, center crop ratios, rotation, horizontal flip, brightness, contrast, saturation, audio gain and fades. Exports render the ordered segments into MP4 (video) or MP3 (audio) using the separate editing worker. Projects autosave locally and support JSON save/load, undo/redo, source/frame stepping and sequence playback. Source thumbnails and an optional original waveform assist navigation. This is a focused media editor, not a replacement for a full multitrack NLE; mixed-source tracks, titles, compositing and speed ramps are not implemented.

Right-click task rows, library cards, empty queue space or editor segments for context actions. Output deletion in the library keeps its confirmation dialog; imported originals cannot be deleted. The mini player resizes from its corner, remembers its dimensions and keeps opt-in paused playback. Accent-based glow follows focus and hover.


## 0.9.0 — multi-source Timeline Studio

Edit directly on a gap-free timeline: V select/move, C razor, B ripple trim, N rolling trim (out edge adjusts the following clip), Y slip; S splits at the playhead. Drag clip edges, reorder clips by dropping before/after their midpoint, or insert downloaded/imported library media at the playhead. Cuts close gaps automatically. Undo/redo and local project autosave preserve source references. Projects reference local job IDs and need the same media library; project JSON does not embed video files. Up to 100 clips per sequence.

A1 audio stays linked to each clip, with per-clip gain. Add an independent A2 music/voiceover bed, source in point, timeline offset and gain. Export mixes and limits audio, supplies silence for clips without audio, and uses black frames for audio-only clips. Soundtrack mixing and full fades are applied on export; the source monitor does not audition the final audio mix. Clip speeds preserve pitch during export. Waveforms represent the selected original source.

Export H.264/AAC MP4 or ProRes 422/24-bit PCM MOV, 24/25/30/50/60 FPS, first-video dimensions or 720p/1080p/2160p, and adjustable MP4 CRF quality. Sources with different sizes are fitted to a common canvas with letterboxing after global crop/rotation/color adjustments. Resolution choices can upscale; they do not recover source detail. Rendering always creates a new file.

This is a multi-source sequence editor with one soundtrack bed, not Premiere/Resolve parity: arbitrary stacked video/audio tracks, compositing, titles, keyframes, transitions, multicamera and speed ramps are not implemented. Preview switches sources at cuts and may briefly buffer; it is not a rendered frame-accurate sequence cache.

The online Windows desktop installation checks https://api.github.com/repos/yt-dlp/yt-dlp/releases/latest in the background at startup and hourly while open. It uses stable published releases, verifies the official package SHA-256, installs dependencies into a separate versioned runtime, validates the engine and atomically marks it ready. Restart DropDL to activate. Existing downloads keep their loaded engine. Offline/failed updates leave the current engine intact; use the header yt-dlp control to view errors or check now. The optional PyInstaller/frozen build does not support runtime engine updates.

Setup recreates direct executable desktop/Start-menu shortcuts with a release-specific icon filename and sends Explorer a shell refresh notification. Existing manually pinned taskbar shortcuts may require unpinning and pinning the new shortcut. Native Windows installation and icon-cache behavior require validation on Windows.


## 0.9.1 — editor usability rebuild

The editor uses a viewport-sized workspace: large preview, collapsible properties panel with Clip/Picture/Audio tabs, and a timeline whose height can be adjusted by dragging the divider. Export settings are in a separate dialog. The media picker includes search. Waveform and speed graph are optional under View.

Timeline movement uses pointer gestures with a visible insertion marker and a five-pixel drag threshold. Pull the visible grips inside the selected clip edges to trim; they do not overlap a neighboring clip's grips. Timeline scale stays fixed during a trim. Reordering changes selection and preview together, and each pointer gesture creates one undo step. Escape, pointer cancellation or losing window focus discards a pending drag. Keyboard Alt+Left/Right reorders a focused clip; grip arrow keys trim by frame. Fit shows the sequence; Selected zooms a short clip for precision.

V selects Move, C selects Cut, N selects Roll and Y selects Slip. Move also trims via the edge grips. Roll adjusts the next clip's start while preserving total sequence duration, within both sources' available handles. Slip changes source content while preserving clip length. S splits at the playhead, Space previews the edited sequence, I/O set source in/out, and Ctrl+Z / Ctrl+Shift+Z undo/redo. Preview cut boundaries are monitored every animation frame while playing. Mixed-source preview can still buffer; it is not a prerendered frame cache.

A separate six-step editor guide appears on first use, supports English/Arabic, can be skipped, and can be replayed from Guide. Its local completion key is independent of the downloader's existing tour.

Validation: timeline-model tests verify reorder, trim limits, speed handling, rolling duration and slip invariants; real Chromium pointer tests verify dragging, trimming, cancel, one-step undo, preview selection and playback across source cuts, tutorial, layouts at 900/1100/1440 pixels, soundtrack and export requests. Native Windows UI/installer testing remains pending.

Run `npm run test:timeline` for timeline-model checks. For browser checks, install Playwright 1.51.1 and Chromium headless shell, then set `DROPDL_PLAYWRIGHT` to its module path and run `npm run test:editor`. Browser tests use a synthetic FFmpeg video and mocked API; no remote media is downloaded.


## Desktop 0.10.0 — stable timeline and project tools

The larger timeline keeps its viewing scale when clips are trimmed or inserted. Shortened clips leave visible empty space; Fit is an explicit action. Use the zoom slider, Ctrl + wheel, horizontal scroll and the panel divider to change the view. Drag clip bodies to reorder and edge grips to trim.

Project → Titles, captions & recovery adds timed titles and captions, SRT import/export and the latest 30 durable project snapshots. Text has its own draggable/trimmed timeline lane and is burned into rendered video (SRT remains separately exportable). Text times are output timeline times: review them after moving, speeding up or trimming clips. English and Arabic are supported by the editor; libass uses the installed Arial-compatible font on Windows.

Soundtrack, clip gain, master gain and fades now play live in the preview, with a protective audio compressor. Light preview creates a cached 640-pixel-wide H.264 editing copy without redownloading; exports always use the original source media. Compatible preview encoding runs independently of the download queue.

Recovery is stored under the user profile, with a backup if the latest file becomes unreadable. Project JSON remains portable within the same media catalogue; source media must still exist. Original media and the custom desktop UI from the supplied version are preserved. Windows installation and native playback still require a Windows validation pass; the installer is unsigned.


## Desktop 0.11.0 — duplicate copies, download recovery and media drops

Repeated downloads are allowed by default. Output collisions are reserved exclusively across workers and receive ` (+1)`, ` (+2)` and so on before the extension; existing files are preserved. The completed queue title also shows the copy number. Skip duplicate outputs remains an optional advanced setting; the previous default is migrated to allow duplicates.

HTTP downloads request 8 MiB chunks where supported. Native HLS/DASH uses up to four concurrent fragments, with ten retries for chunks/fragments and no silent omission of unavailable segments. Partial files and fragment state survive retry/restart, with bounded automatic retry for temporary network failures. Recoverable failed/cancelled work folders are protected from cleanup until their tasks are removed. Server support for ranges/fragments, expiring access and changed source content can still limit resume; unsupported range servers may restart their downloads.

Drag files directly from Explorer onto the timeline to register references and insert them at the drop time, without using an import dialog or copying entire files. Dropping inside a clip splits it; multiple files retain their order. Drag items from the editor media library onto the same timeline. Existing clips retain pointer-based reorder, edge trimming, auto-scroll and undo. The Original media and Edited clips tabs organize the editor bin; All media remains available. Clip exports and trimmed results are classified as edited.

Tests include interrupted/resumed HTTP transfer with a byte-for-byte final check, concurrent collision naming, native file-reference event handling, speed-aware drop insertion, browser drag/drop and category checks. Windows Explorer/WebView2 integration still needs a native Windows test.


## Desktop 0.11.1 — FFmpeg export compatibility

Editor exports detect support for the current `-/filter_complex` file-loading syntax and use it when available. Older FFmpeg builds retain the legacy `-filter_complex_script` path. This fixes the immediate 0% export failure when newer FFmpeg builds reject the removed legacy flag. Graphs still load from a file to preserve long timeline support on Windows. No media or project changes are needed.

## Desktop 0.12.0 — independent tracks and visible media bin

Clips now have source in/out points plus independent timeline offsets and video tracks V1–V8. Snapping is off by default; trimming and deletion leave gaps, dragging changes placement without pushing neighbours, and cuts preserve both parts' positions. Higher tracks cover lower tracks, with mixed linked audio; empty timeline intervals render black with silence. Older sequence projects migrate to consecutive V1 positions when opened. Rendering supports old and new FFmpeg file-filter syntax.

A docked, searchable media bin opens with the editor, has original/edited categories, thumbnails, file import, and pointer drag into any track. Windows Explorer drops use WebView2's actual file objects rather than the generic name/path cache, run media probing away from the UI thread, and report errors. The Import files picker remains available. Downloader rows store remote thumbnails and use cached local frames for older completed videos.

macOS is planned for 1.0, with a separate app bundle, architecture-appropriate engines, native dialogs/opening/icons, and macOS validation. This release's installer is Windows only.

## Desktop 0.12.1 — editor startup crash repair

Windows native drop registration is dispatched with WinForms BeginInvoke to the owning UI thread. The WebView2 COM object is not accessed by pywebview's loaded worker. Synchronous JavaScript evaluation and file imports run on workers after the UI callback returns, with diagnostics and recoverable import-picker fallback on setup failure.

Opening the editor uses a still image, has no media-file video requests and no continuously running paused preview loop. Playback/seek explicitly activate preview. Only the top visible layer uses a video decoder; other overlapping clip audio uses audio elements. Source metadata loads with two requests at a time and does not restart after each result. Windows runtime verification remains necessary; mocked UI affinity checks and browser startup checks cover the regression.

### 0.12.2 editor layout correction

The media bin occupies its own editor grid column, with an independently scrolling clip list. It stays above the timeline when resizing the window or timeline, in English and Arabic. The floating panel positioning that caused overlap has been removed.

### 0.13.0 reliability and detachable player

- Durable queue checkpoints are flushed to disk and retain a readable backup. Invalid individual records are skipped with diagnostic evidence; a damaged primary queue falls back to its backup. Failed checkpoint writes appear in the interface and diagnostics.
- Interrupted tasks keep their identities, source settings, partial files and progress. Auto-recovery resumes interrupted downloads according to Settings. User-paused and cancelled work stays stopped; interrupted clip/conversion exports require an explicit retry. HTTP range/fragment resume depends on the hosting server. An interrupted conversion/export restarts from its source; it does not resume encoding midway.
- Download stages distinguish connecting/resuming, downloading, merging, remuxing, audio conversion and metadata. Categorized failure guidance supplements the original error.
- Bounded rotating desktop/backend logs, unexpected-exit markers and diagnostic reports include bounded failed-worker evidence. Native Export diagnostics still works when the backend has stopped. URLs and recognized credentials are redacted; media, cookies, settings and queue history are excluded. Review before sharing.
- Drag the mini-player header to reposition it. Resize from any edge or corner; focused resize handles support arrow keys. Detach opens a native resizable player window, and Attach returns it to the main window with its position and speed retained. Playback opens paused. The default Play action still opens the system player.

Validation: backend recovery, corruption fallback, shutdown intent, simulated disk-write failure, cancelled/paused preservation, native bridge and offline diagnostics tests; real browser pointer resizing, movement, small-window bounds, detach/attach and paused playback in English/Arabic. Native Windows runtime testing remains necessary.


### 0.14.0 editor workflow and export controls

- V1–V8 track buttons: **M** mutes linked audio, **H** hides video while retaining audio, **L** locks editing. Locked tracks reject clip movement, trimming, cutting, deletion, duplication and incoming media. Track states and added lanes survive project recovery. Hiding/muting does not shorten the timeline. The soundtrack has independent mute/lock controls in Audio properties.
- Roll uses a touching neighbour on the same track, supports either shared edge and keeps outer positions fixed. Gaps and ambiguous overlapping neighbours are not rolled. Move supports purely vertical dragging and preserves free placement. Edge snapping is optional and off initially: **Shift+S** toggles it, **Alt** bypasses snapping during a move. Frame snapping is independent and uses the project frame rate. The timeline remains fixed in scale until Fit/zoom is chosen.
- Arrow keys and the frame buttons step in timeline frames, including speed-adjusted clips and gaps. Shift+Arrow steps ten frames; Home/End seeks timeline boundaries. Ctrl+D duplicates an unlocked selected clip. Ctrl+Z undoes and Ctrl+Y or Ctrl+Shift+Z redoes. Undo retains the previous selection and playhead; one slider drag or held arrow adjustment is one undo step. Escape cancels an in-progress clip or slider drag. The header Shortcuts reference lists these controls.
- Clip properties include exact timeline placement and track selection. The media bin remains independently scrollable above the timeline; clip names have space alongside thumbnails, with soundtrack actions on a second row. Timeline labels follow vertical track scrolling.
- Export presets: high quality MP4, smaller MP4, vertical 1080×1920, ProRes editing master, MP3, M4A and 24-bit PCM WAV. Audio presets mix the edited timeline and soundtrack without rendering video. Export summary shows actual dimensions when metadata is available, frame rate, duration, audio settings and audio-size estimates; variable-quality video size depends on content. Presets can be customized. Source files are never overwritten.
- One preview audio mixer handles clip audio and the soundtrack, with master volume, fades and a protective compressor. Opening a paused editor still uses a still image and does not create eager video decoders. System-player defaults, detachable mini-player, native file drops, queue recovery, quiet executable shortcuts, repair/upgrade and the custom logo/interface are retained.

Validation covers real FFmpeg MP4/ProRes and MP3/M4A/WAV rendering, hidden-track black output with retained audio, muted audio, timeline gaps and overlaps, recovery validation, model lock/snap/Roll invariants and Chromium pointer/keyboard editing in English and Arabic. Browser API fixtures do not verify live video-host compatibility. Native Windows installation, WebView2 drops and audio-device behavior still require Windows testing. The installer is an online prerequisite installer, not an offline self-contained runtime, and remains unsigned.


### 0.15.0 organized library and everyday convenience

- Favorite media with the star on each card, or favorite/unfavorite a selection. Favorites persist independently of tasks and appear in the editor bin as a filter.
- Create, rename and remove collections. Each file can belong to one collection; bulk assignment retains selection across pages and filters. Collections organize references without moving files. Removing a collection leaves its media in the library. Existing 0.14 catalogues migrate by adding separate annotation tables; file IDs and task records remain intact.
- Grid and compact list views, search including collection names, source/site/type and available/missing filters, original/download/edited/conversion filters, newest/oldest/title/size/duration sorting, 36-item pagination and selected/filtered size totals. List view is remembered locally. Duration sorting uses available metadata; unknown durations sort last. Imported files already have duration metadata, and opening Details caches it for other files. The library does not scan every media stream on startup.
- Details reads codec, resolution, frame rate and duration on demand. Set a display title without renaming the physical file, and choose its favorite/collection state. A custom display title survives automatic task-catalogue refreshes. Show in folder uses the native file browser. Right-click adds Favorite, Media details & collection and Locate/Show in folder.
- Locate file is offered for missing media. Its native picker validates playable media, keeps the catalogue ID, title, favorites and collection, and rejects a file already registered elsewhere. The chosen replacement becomes a protected imported original; DropDL cannot delete it as an owned output. Playback and new conversions/edits use the new reference. Existing editor projects retain their job-source IDs, so source clips referring to an old missing job may still need replacement.
- The editor media bin also filters collections and favorites. Its clip list retains usable height in small windows. Existing timeline, export presets, system-player default, detachable mini-player, quiet executable launcher, icon, upgrade/repair, queue recovery and custom interface are preserved.

Validation: 168 backend tests, including real-media probing, legacy SQLite migration, durable annotations, transactional batch rejection, collection cleanup, lazy information reads, native relink authorization and protection of external originals. Real Chromium tests cover 45-file pagination, create/rename/remove collections, favorites, metadata/display titles, native-action fixtures, relinking, sorting, list layout, context menus and English/Arabic. Existing editor, timeline, main UI and player regressions are retained. Browser fixtures do not validate native Explorer/WebView2 behavior; Windows installation and native runtime still require an on-device test. The Windows installer remains an online prerequisite installer and unsigned.


### 1.0.0 — desktop release and editor export locations

- **Choose export folder** is available in the editor's Export dialog. It opens
  the operating system folder picker, displays the selected path, and remembers
  it for subsequent exports and launches. Cancel leaves the previous folder
  unchanged. English and Arabic layouts are supported. The editor's guide now
  mentions the folder control. The Start export action remains visible while
  scrolling the settings, and the dialog supports keyboard focus and Escape.
- Existing installations migrate the editor destination to an **Exports** folder
  beneath their current download folder. Changing the editor folder leaves the
  download/converter locations unchanged. An enqueued export retains its chosen
  destination even if the preference changes later. Export paths can only be
  changed through the native picker/private desktop bridge, not a public API field.
- Before enqueueing, the app checks the actual destination for writability and
  at least 100 MB of free space. Unavailable/full export drives reject the request
  before creating a task. Native validation errors show the useful backend message.
  This is a minimum-space check, not a guarantee that a large export will fit.
- All 0.15 functionality and the supplied custom logo/interface are retained:
  playlist batches, resumable downloads, duplicate copies, video+audio output,
  conversion, independent timeline tracks and original preservation, favorites,
  collections, media details, manual selection, paused-by-default preview,
  native mini-player detach/resize, Arabic, themes, tutorials, durable queue
  recovery, diagnostics, upgrade/repair and executable shortcuts.
- App, backend, compiled UI manifest, launcher, installer and uninstall registry
  identify **1.0.0**. Existing supported desktop installs can upgrade in place;
  newer versions remain protected from downgrades. Windows setup remains online
  and unsigned. Close all app windows before running the installer.
- An experimental macOS .app build target and build/validation guide are included
  in **MACOS.md**. It supports a platform-standard data folder and Finder's PATH
  for bundled/Homebrew tools. No Mac binary is supplied or certified as tested;
  build separately on Apple Silicon and Intel. Frozen Mac builds require an app
  rebuild for engine updates, while the online Windows/source updater is retained.

Verification: production TypeScript/Vite build, 175 backend tests including a
real FFmpeg export into a selected folder without altering the source, old-settings
migration, native path authorization, picker cancellation and destination-drive
failures. Existing model tests and Chromium editor, library, player and main UI
regressions pass in English/Arabic, including playlist queues and startup decoder
limits. The Windows installer is compiled and its payload/version/icon/quiet
launcher are checked. Native Windows/WebView2 installation and Mac bundle behavior
still require on-device testing; these fixtures do not establish compatibility with
every video site or eliminate signing/security warnings.


### 1.0.2 — Windows setup with Unicode account names

Python discovery previously printed its executable path directly into native
stdout. Windows PowerShell 5.1 can decode those bytes with a different code page,
corrupting Arabic or other non-ASCII profile names. The fallback path accepted
that text without checking the returned file and failed during environment creation.

Discovery now receives an ASCII-only JSON object from Python, decodes it in
PowerShell and verifies an absolute, existing executable path for both launcher
and direct-executable candidates. A final existence check runs before environment
creation. Account names, global Windows encoding, installed Python locations and
user data are not changed. The existing quiet launcher, Unicode setup-env file,
upgrade/repair, native icon, interface and all 1.0.0 features are retained.

Use this installer on top of the failed install and choose Upgrade/Repair as
shown; no account rename or fresh Windows installation is needed. Setup continues
checking existing prerequisites before installing missing ones. Close all DropDL
windows first. Native PowerShell path tests are included in tests/setup-unicode.ps1;
they exercise escaped path transport with Arabic, Chinese, accented, emoji,
apostrophe and space characters and validate rejected paths. Windows PowerShell
5.1 execution still needs a Windows machine.

Hotfix validation: 184 backend tests and the production frontend build passed;
main-interface regression checks passed in English/Arabic. Nine installer tests
exercise the actual Python discovery program and mismatched code-page decoding,
including the screenshot's Arabic-path corruption. The native PowerShell 5.1
script is supplied for on-device testing and was not run on this Linux host.
The rebuilt installer/source ZIP pass payload, version, original custom interface,
icon, quiet launcher and archive-integrity checks.

## Windows 1.0.2 — sidebar clipping and optional tray

The Add download sidebar keeps preview playback inline and preserves the chosen
start/finish. Both direct downloads and local-preview exports use those times;
sidebar exports appear in the download queue and completion popup. The source
may be downloaded in full into temporary storage first, then trimmed. The saved
output is the selected range. Completed clips are checked with ffprobe against
that range, and clipping requests with missing times fail instead of saving a
whole video silently.

Clip fields show HH:MM:SS.s (for example 00:12:54.6), accept HH:MM:SS.s, MM:SS.s
or plain seconds, and support Arabic digits. Invalid times disable submission.

Preferences → Keep in system tray when closing the window is optional and off
by default. Save preferences to enable it. Closing the main window then hides
it while downloads continue. Double-click its icon or choose Open DropDL to
restore the window; choose Exit to close all app windows and stop the app.
Windows logoff/shutdown bypasses hiding. English/Arabic tray menus use the app
icon. If tray initialization fails, normal window closing remains available.

Upgrade using DropDL-Setup.exe; choose Upgrade/Repair when offered. No new
system prerequisite is needed for the tray: it uses the existing WinForms host.
The installer remains unsigned. Native Windows/WebView2/tray validation is
pending; regression tests and installer compilation were performed on Linux.
