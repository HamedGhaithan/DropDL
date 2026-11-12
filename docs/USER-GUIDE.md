# DropDL Studio user guide

## Install / update

Close DropDL and run **DropDL-Setup.exe**. It installs or updates the app in `%LOCALAPPDATA%\Programs\DropDLStudio`, prepares Python, Node.js, FFmpeg/ffprobe, WebView2 and Python packages, and creates Desktop/Start Menu shortcuts. It is an **online prerequisite installer**: first-time setup needs internet. Some prerequisites may request administrator permission. Windows 10 1809+ or Windows 11, x64, is required.

Alternatively, extract **DropDL-Studio-2.3.0.zip**, run **Setup-DropDL.bat**, then **Start-Desktop.bat**. Run setup once after upgrading the source package; normal launches do not reinstall dependencies. Download locations and user data remain outside the installation directory.

Shortcuts now point to the included **DropDL.exe launcher inside the app directory**, so “Open file location” opens the application folder. The native window uses the DropDL icon and Windows AppUserModelID. Apps & Features contains **DropDL Studio** with an uninstaller; uninstalling retains personal downloads and the app's user-data folder.

The installer and launcher are unsigned. Windows can still show Unknown publisher/SmartScreen. Verified publisher trust requires a real signing certificate and may also require reputation; this release does not disable Windows security. `scripts/sign-release.ps1` supports a certificate you own.

## Downloads

Single links, pasted URL batches, playlist selection, pagination and entire-playlist loading remain available. Choose video, audio or both; both produces a video with sound plus a separate audio file. Download formats: MP4, WebM, MKV, MP3 and M4A.

The queue includes HH:MM:SS ETA, search/filtering, 100-row pagination, explicit Cancel, same-row Retry, priority sorting, drag-to-reorder waiting tasks, scheduled start time, Pause/Resume for queued/downloading media, Pause queue/Resume queue, and completion notifications. Click a task title to set priority or a start time. Scheduled downloads run only while the app is open.

Pause retains partial work. Resume support depends on the hosting site and protocol. FFmpeg processing and conversions use Cancel rather than pausing. Restart recovery is enabled by default and can be disabled in Preferences: interrupted tasks resume/retry on launch; intentionally paused tasks stay paused. Temporary network errors receive up to two delayed task-level retries in addition to yt-dlp's own request retries. Permanent errors stay failed for review.

Every download runs in a separate worker process. A crashed extractor/worker reports a failure without killing the GUI or backend. The queue dispatcher starts at most two tasks at once by default and does not create one process/thread per queued playlist item. Duplicate detection normalizes common YouTube URLs and remembers output format, quality and clip range; it remains effective after queue clearing. Uncheck **Skip duplicate outputs** to intentionally download again. Missing/deleted files are eligible to download again.

Quick download presets include mobile video, best quality, audio only and video+audio. Advanced download options include a start schedule, subtitle languages (for example `ar,en`), and embedded metadata/chapters. Available subtitles are saved alongside the output. Selecting a language does not create subtitles a site does not provide. No subtitle translation or speech transcription is included.

## Convert

Select **Convert**, then **Import local files** or select files already in the library. No upload is required: local files are referenced on disk. Select a preset and convert one or many files.

Presets: universal H.264 MP4, compact mobile MP4, high-quality MP4, VP9 WebM, MP3, AAC/M4A, WAV, FLAC, ProRes 422 and DNxHR HQ. Fast container change copies compatible streams to MKV/MP4/MOV/WebM without re-encoding. Incompatible codecs produce an explanatory failure and leave the original intact.

Advanced video options: maximum height, frame rate, 90/180/270-degree rotation, crop rectangle (width,height,X,Y), approximate target file size and trim range. Audio normalization is available for encoded presets. Approximate size targets are single-pass video bitrate estimates, not exact size guarantees. WAV/FLAC and editing formats can be much larger than the source. Lossless output cannot restore quality already lost in a source file.

**Create 10-second sample** uses the same options with a short range and produces a browser-compatible preview before you commit to a long conversion. Save named custom presets for reuse. Output files appear in the selected download folder's **Converted** subfolder. Originals are always preserved; every output has a unique task suffix. CPU encoding is used; GPU acceleration is not implemented in this release.

## Clip Studio

Local originals and completed downloads are supported. Choose a library file and **Preview & clip**, or enable clipping in Add download. Clipping is off by default. Preview preparation stays in a small corner indicator rather than the main download list; Arabic reverses its corner placement.

The existing start/finish sliders and numeric indicators remain. Frame stepping uses the source frame rate when available. Optional thumbnail filmstrip and audio waveform are generated on demand. Add several ranges with **Add this range**, then export them as separate tasks/files. Export re-encodes for accurate trimming and preserves the original. Preview playback copies use H.264/AAC where necessary, while clip export reads the original-quality file. Large-source previews can take time.

For fast container changes, trimmed boundaries may follow codec/keyframe constraints; use an encoded preset for accurate trimming. The built-in player cannot play every editing codec directly; **Preview & clip** generates a compatible playback copy.

## Library and storage

The media catalogue survives clearing task history. Browse thumbnails, play files, search by title/site/filename, filter video/audio/site, and select items for conversion. The catalogue records imported originals and completed outputs separately.

**Remove reference** removes the catalogue entry without deleting its file. **Delete output file** requires explicit confirmation and is available only for outputs created by DropDL. Imported originals cannot be deleted by the app. Removed references are not resurrected from old queue history on restart; reimport a file to add it again.

Choose a native destination folder as before. Website subfolders are optional. User settings, task history, the library database, private cookies, subscriptions and temporary work live under `%LOCALAPPDATA%\DropDL`. `DROPDL_DATA_ROOT` can override that folder. Queue clearing does not delete media. Storage shows free space and temporary work usage; new downloads/conversions are blocked below 100 MB free space.

**Clean temporary files** removes unneeded work folders while preserving active/paused tasks, registered files, referenced retry sources, and retryable partial downloads. Preferences can enable cleanup of unused work folders older than seven days at startup. Completed preview caches may be removed and can be regenerated. Clearing a queue removes references to partial work, so subsequent cleanup may delete that abandoned work. The automatic cleanup option can be disabled.

Per-task speed limits and a global bandwidth budget are available in Preferences. Global bandwidth is conservatively divided across download slots when each task starts; changes apply to subsequently started tasks. It is not a live bandwidth allocator for existing downloads. Global queue pause blocks new tasks while current conversions continue to finish.

## Subscriptions

The Library/Convert workspace has optional playlist/channel subscriptions. Use the site's playlist URL or channel videos listing URL. Choose output mode, check interval, title keyword and optional maximum duration. Checks inspect up to the latest 100 entries and skip matching outputs already in the queue/library. Initial checks can queue existing matching entries; this is not a full historical archive or a guaranteed catch-up for more than 100 new uploads between checks. The app must remain open. Disable or remove a subscription at any time.

## Browser integration

Load the included `browser-extension` folder in Chrome/Edge: Extensions → Developer mode → Load unpacked. Keep DropDL running on its default local port 17321. Open **Browser integration & inbox** in Library, generate a six-digit pairing code, and enter it in the extension within five minutes.

**Send current tab** adds the link to the app's inbox; choose download options before queueing. The extension requests active-tab access, local storage and access to the local DropDL port only. Pairing tokens grant link submission, not media-file access. **Disconnect all extensions** revokes existing tokens. The extension is supplied as unpacked source and is not published in a browser store. Its code and pairing endpoints are tested; installation inside Chrome/Edge is not end-to-end tested here.

This desktop release does not include a mobile PWA or multiple web-user accounts. Those belong to the separate web edition; importing that Docker project was deliberately avoided.

## Optional private cookies

Import a Netscape-format cookie export through the native file picker in Library/Convert for media your own account can access. Cookies remain in the local user-data folder and are not packaged with releases. Remove the cookie file from the same panel when finished. Existing tasks snapshot its path; removing the file prevents subsequent use. Site login, availability, geography, rate limits and DRM can still prevent downloads. Cookie support does not bypass DRM.

## Interface and diagnostics

English/Arabic, RTL layout, light/dark modes, five accents, reduced-motion support and the skippable six-step download tour remain. New workspaces use the same theme and language. Technical errors and website titles retain their source language.

Logs: `%LOCALAPPDATA%\DropDL\diagnostics.log`, `backend-console.log`, `crash.log` and `playlist-worker-crash.log`. Each download's work folder also has `worker.log` and worker-state diagnostics. A worker failure identifies its log path. No automatic remote error reporting is used.

## Verification / development

Production frontend is prebuilt in `frontend/dist`. Development: install `backend/requirements.txt`, install frontend packages with `npm ci`, build with `npm run build`, then run `python backend/desktop.py` with FFmpeg/ffprobe and Node on PATH. Native Windows builds are supported by `scripts/build-native-windows.ps1`; run the generated whole folder, not its EXE alone. NSIS builds the online setup and small local launcher with `scripts/build-installer.py`.

Verification includes backend/API tests, real FFmpeg conversions and clipping, original preservation, isolated worker success/crash behavior, duplicate identity, queue persistence/priority/scheduling, library byte ranges and deletion safeguards, thumbnail/waveform generation, storage cleanup, private cookie authorization, subscriptions, extension pairing, and English/Arabic UI flows including a 198-task playlist queue and converter/library controls.

The Windows installer is compiled and structurally checked. Native Windows/WebView execution, prerequisite installation, GPU hardware, real third-party download availability and Chrome/Edge extension installation are not end-to-end verified in this Linux environment. The app cannot guarantee support for every website.

