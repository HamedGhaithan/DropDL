# DropDL Studio user guide

## Install / update

Close DropDL and run **DropDL-Setup.exe**. It installs or updates the app in `%LOCALAPPDATA%\Programs\DropDLStudio`, prepares Python, Node.js, FFmpeg/ffprobe, WebView2 and Python packages, and creates Desktop/Start Menu shortcuts. It is an **online prerequisite installer**: first-time setup needs internet. Some prerequisites may request administrator permission. Windows 10 1809+ or Windows 11, x64, is required.

Alternatively, extract **DropDL-Studio-3.0.0.zip**, run **Setup-DropDL.bat**, then **Start-Desktop.bat**. Run setup once after upgrading the source package; normal launches do not reinstall dependencies. Download locations and user data remain outside the installation directory.

Shortcuts now point to the included **DropDL.exe launcher inside the app directory**, so “Open file location” opens the application folder. The native window uses the DropDL icon and Windows AppUserModelID. Apps & Features contains **DropDL Studio** with an uninstaller; uninstalling retains personal downloads and the app's user-data folder.

The installer and launcher are unsigned. Windows can still show Unknown publisher/SmartScreen. Verified publisher trust requires a real signing certificate and may also require reputation; this release does not disable Windows security. `scripts/sign-release.ps1` supports a certificate you own.

## Downloads

Single links, pasted URL batches, playlist selection, pagination and entire-playlist loading remain available. Choose video, audio or both; both produces a video with sound plus a separate audio file. Download formats: MP4, WebM, MKV, MP3 and M4A.

The queue includes HH:MM:SS ETA, search/filtering, 100-row pagination, explicit Cancel, same-row Retry, priority sorting, drag-to-reorder waiting tasks, scheduled start time, Pause/Resume for queued/downloading media, Pause queue/Resume queue, and completion notifications. Click a task title to set priority or a start time. Scheduled downloads run only while the app is open.

Pause retains partial work. Resume support depends on the hosting site and protocol. FFmpeg processing and conversions use Cancel rather than pausing. Restart recovery is enabled by default and can be disabled in Preferences: interrupted tasks resume/retry on launch; intentionally paused tasks stay paused. Temporary network errors receive up to two delayed task-level retries in addition to yt-dlp's own request retries. Permanent errors stay failed for review.

Every download runs in a separate worker process. A crashed extractor/worker reports a failure without killing the GUI or backend. The queue dispatcher starts at most two tasks at once by default and does not create one process/thread per queued playlist item. Duplicate detection normalizes common YouTube URLs and remembers output format, quality and clip range; it remains effective after queue clearing. Uncheck **Skip duplicate outputs** to intentionally download again. Missing/deleted files are eligible to download again.

Quick download presets include mobile video, best quality, audio only and video+audio. Advanced download options include a start schedule, subtitle languages (for example `ar,en`), and embedded metadata/chapters. Available subtitles are saved alongside the output. Selecting a language does not create subtitles a site does not provide. No subtitle translation or speech transcription is included. **Also save each chapter as its own file** (in Smart extras) writes one file per chapter into a folder beside the full download, for videos that have chapters. Subtitles saved with a video become its transcript in Clip Studio.

## Convert

Select **Convert**, then **Import local files** or select files already in the library. No upload is required: local files are referenced on disk. Select a preset and convert one or many files.

Presets: universal H.264 MP4, compact mobile MP4, high-quality MP4, VP9 WebM, MP3, AAC/M4A, WAV, FLAC, ProRes 422 and DNxHR HQ. Fast container change copies compatible streams to MKV/MP4/MOV/WebM without re-encoding. Incompatible codecs produce an explanatory failure and leave the original intact.

Advanced video options: maximum height, frame rate, 90/180/270-degree rotation, crop rectangle (width,height,X,Y), approximate target file size and trim range. Audio normalization is available for encoded presets. Approximate size targets are single-pass video bitrate estimates, not exact size guarantees. WAV/FLAC and editing formats can be much larger than the source. Lossless output cannot restore quality already lost in a source file.

**Create 10-second sample** uses the same options with a short range and produces a browser-compatible preview before you commit to a long conversion. Save named custom presets for reuse. Output files appear in the selected download folder's **Converted** subfolder. Originals are always preserved; every output has a unique task suffix. CPU encoding is used; GPU acceleration is not implemented in this release.

## Clip Studio

### Projects (new in 3.0)

Click **New project** in the header (or press **Ctrl+Shift+N**). An empty project opens in its own window. The **Studio** tab is the Clip Studio home:
- **New project** in Landscape (16:9), Vertical (9:16), Square (1:1) or Portrait (4:5).
- **Start from files on this PC**: the files become the first clips.
- **Download & edit**: paste a link. The project opens when the download finishes.
- **Recent projects**: click a poster to open; Rename, Duplicate or Delete (deleting a project never deletes media files).
- **Search inside your videos**: type words that were spoken; click a result to open the video at that moment (needs a transcript, see below).

In the editor, use **Import files**, the media bin's **Add** button, or drag files onto the timeline. Click the project name in the header to rename it. Projects save as you edit. If a file's task record was cleared, the project re-links it; moved or deleted files are reported.

### Smart tools

Select a clip and open **Smart tools** (beside Effect Controls):
- **Remove silences**: set how quiet (dB), how long a pause must be, and the breathing room kept around words. **Find pauses** shows them and the time saved; **Cut** removes them in one step (Ctrl+Z undoes it). Later clips on the same track and captions move up.
- **Split at scene changes**: **Find scene changes**, then split the clip into shots.
- **One-click formats**:
  - Shorts / Reels / TikTok (9:16, blurred background);
  - Instagram feed (4:5);
  - Square;
  - YouTube (16:9);
  - Original.
- **Transitions**: **Cross dissolve** (overlaps the clip with the one before it on the same track), **Dip to black**, or per-clip fades in the Clip tab. A fade on V1 goes to black; on a higher track it dissolves into what is below.
- **Even loudness**: Streaming −14, Podcast −16 or TV −23 LUFS, applied at export.

### Music, motion, titles and markers

In **Smart tools**:
- **Music**: **Find the beat** measures the tempo of the soundtrack (or of the selected clip when there is no soundtrack) and draws every beat on the timeline. Edge snap catches beats. Choose **Every beat**, **2 beats**, **4 beats** or **Nearest beat**, then **Cut V1 clips to the beat**. **Duck the music while clips speak** lowers the soundtrack under voices.
- **Animated titles**:
  1. Type the text.
  2. Choose an entrance (Pop, Slide, Fade, Typewriter or Still) and a place (Top, Centre, Bottom or Lower third).
  3. Click **Add at playhead**.
- **Markers & chapters**: press **M** (or the button) to add a marker; rename or remove markers in the list. MP4, MOV and M4A exports carry them as chapters. **Copy YouTube chapters** copies a list for your video description.

In Effect Controls:
- **Clip → Motion**: zoom in, zoom out, pan left or pan right, with a strength slider.
- **Frame → Keep in frame**: when a wide clip is cropped to a narrower frame, choose which part stays.

The Studio home's **Start from a template** opens a project already set for a podcast clip, captioned short, music video or tutorial.

### Transcript

Open **Transcript** with a clip selected:
- **Get captions from the video page** (YouTube and many sites; uses your YouTube sign-in; only the caption text is downloaded), or **Import .srt / .vtt**. Subtitles saved with a download are picked up automatically.
- Click a timestamp to jump there; the spoken line is highlighted during playback. Search the words; **This clip only** hides lines outside the clip.
- Tick lines (Shift-click for a range) and choose **Cut these lines** or **Keep only these**.
- **Add captions to this clip** writes timed captions; **Short phrases** splits them into 4-word chunks for vertical video. Pick a style: Classic, Bold, Highlight, Boxed, **Karaoke** (words fill as they are said) or **Pop** (the spoken word grows). YouTube's automatic captions keep their real word timings.
- **Save .srt** or **Save text** exports the transcript.

### Looks, frame and audio

In Effect Controls:
- **Look**: ten colour looks previewed on the clip's own frame, with **Use this look on every clip**.
- **Frame**: aspect ratio and **Fill the frame** (crop, blurred background, or bars). For picture in picture, place the clip on V2 or higher and use **Size**, the corner buttons, **Horizontal**/**Vertical** and **Opacity**.
- **Audio**: **Reduce background noise** and **Voice clarity** per clip.

**Snapshot** (below the program monitor) saves the visible frame as a PNG.

### Export

Pick a destination (YouTube 1080p/4K, Shorts/Reels/TikTok, Instagram feed, Square, under 25 MB, under 10 MB, animated GIF, ProRes master, MP3, M4A, WAV), or adjust:
- **Encoder**: graphics card (when one is found) or processor. DropDL tests your graphics encoders once and remembers the result. If the graphics card refuses a job, the export finishes on the processor.
- **Video codec**: H.264 (plays everywhere) or H.265/HEVC (smaller files).
- **Fit under a file size** sets an exact size budget; **Loudness** and **Caption style** apply to the whole export.

### Quick edits of one file

Local originals and completed downloads are supported. Choose a library file and **Preview & clip**, or enable clipping in Add download. Clipping is off by default. Preview preparation stays in a small corner indicator rather than the main download list; Arabic reverses its corner placement.

The existing start/finish sliders and numeric indicators remain. Frame stepping uses the source frame rate when available. Optional thumbnail filmstrip and audio waveform are generated on demand. Add several ranges with **Add this range**, then export them as separate tasks/files. Export re-encodes for accurate trimming and preserves the original. Preview playback copies use H.264/AAC where necessary, while clip export reads the original-quality file. Large-source previews can take time.

For fast container changes, trimmed boundaries may follow codec/keyframe constraints; use an encoded preset for accurate trimming. The built-in player cannot play every editing codec directly; **Preview & clip** generates a compatible playback copy.

## Library and storage

The media catalogue survives clearing task history. Browse thumbnails, play files, search by title/site/filename, filter video/audio/site, and select items for conversion. The catalogue records imported originals and completed outputs separately.

**Remove reference** removes the catalogue entry without deleting its file. **Delete output file** requires explicit confirmation and is available only for outputs created by DropDL. Imported originals cannot be deleted by the app. Removed references are not resurrected from old queue history on restart; reimport a file to add it again.

Choose a native destination folder as before. Website subfolders are optional. User settings, task history, the library database, private cookies, subscriptions and temporary work live under `%LOCALAPPDATA%\DropDL`. `DROPDL_DATA_ROOT` can override that folder. Queue clearing does not delete media. Storage shows free space and temporary work usage; new downloads/conversions are blocked below 100 MB free space.

**Clean temporary files** removes unneeded work folders while preserving active/paused tasks, registered files, referenced retry sources, and retryable partial downloads. Preferences can enable cleanup of unused work folders older than seven days at startup. Completed preview caches may be removed and can be regenerated. Clearing a queue removes references to partial work, so subsequent cleanup may delete that abandoned work. The automatic cleanup option can be disabled.

Per-task speed limits and a global bandwidth budget are available in Preferences. Global bandwidth is conservatively divided across download slots when each task starts; changes apply to subsequently started tasks. It is not a live bandwidth allocator for existing downloads. Global queue pause blocks new tasks while current conversions continue to finish.

## Connect (new in 3.0)

Open **Connect** in the sidebar (or type *Connect* in the command palette).

### Phone Link
1. Turn on **Phone Link**. If Windows asks about the firewall, allow DropDL on **private networks**.
2. Connect your phone to the same Wi-Fi as the PC and point its camera at the QR code. Or open the address shown under the code in the phone's browser and type the 8-character code.
3. On the phone, paste or share a link and tap **Download on PC**. Progress appears on the phone and in the PC's Downloads list (marked *From a phone*).
4. When it is ready, tap **Save to phone** or **Play**. The **Library** tab on the phone searches everything on the PC.

From the PC, open a finished download and choose **Send to phone**; it waits on the phone under **Activity**.

- **Address:** DropDL puts the Wi-Fi or Ethernet adapter that has the internet connection first. If the phone cannot connect, pick another address under the code (VPN adapters only work when the phone is on the same VPN).
- **Away from home:** install [Tailscale](https://tailscale.com) on the PC and the phone; its address appears under the code.
- **Security:** Phone Link is off until you switch it on, answers only devices on private networks, needs a one-time code (valid 10 minutes, rate limited) to pair, and gives each phone its own key. Remove a phone under **Paired phones**. Turning Phone Link off stops the phone server completely.
- **Share sheet:** browsers only let a web page join the phone's share sheet over HTTPS. On plain Wi-Fi, copy the link in the YouTube app and paste it into DropDL; add the page to your home screen for one-tap access. On iPhone you can also make a Shortcut that opens `http://<pc address>/?url=` followed by the shared link.

### YouTube account
YouTube asks downloaders to sign in. Choose **Connect YouTube**, sign in in the window that opens, and DropDL saves the session and closes the window. Only youtube.com cookies are kept, in your DropDL profile on this PC. **Refresh session** re-reads it; **Disconnect** removes it (and signs the sign-in window out). If Google says the browser is not supported, export cookies.txt from your browser and use **Import cookies.txt** instead. A spare Google account is the safest choice for downloading.

### Smart helpers
- **Offer copied links:** copy a video link anywhere; DropDL offers to download it (a notification for known video and music sites when DropDL is in the background).
- **Notify when downloads finish:** a Windows notification when DropDL is not the focused window. Click it to open the task.

## Subscriptions

The Library/Convert workspace has optional playlist/channel subscriptions. Use the site's playlist URL or channel videos listing URL. Choose output mode, check interval, title keyword and optional maximum duration. Checks inspect up to the latest 100 entries and skip matching outputs already in the queue/library. Initial checks can queue existing matching entries; this is not a full historical archive or a guaranteed catch-up for more than 100 new uploads between checks. The app must remain open. Disable or remove a subscription at any time.

## Browser integration

Load the included `browser-extension` folder in Chrome/Edge: Extensions → Developer mode → Load unpacked. Keep DropDL running on its default local port 17321. Open **Browser integration & inbox** in Library, generate a six-digit pairing code, and enter it in the extension within five minutes.

**Send current tab** adds the link to the app's inbox; choose download options before queueing. The extension requests active-tab access, local storage and access to the local DropDL port only. Pairing tokens grant link submission, not media-file access. **Disconnect all extensions** revokes existing tokens. The extension is supplied as unpacked source and is not published in a browser store. Its code and pairing endpoints are tested; installation inside Chrome/Edge is not end-to-end tested here.

This desktop release does not include a mobile PWA or multiple web-user accounts. Those belong to the separate web edition; importing that Docker project was deliberately avoided.

## Optional private cookies

Since 3.0 the easiest way is **Connect → Connect YouTube** (above). Importing a cookies file still works:

Import a Netscape-format cookie export through the native file picker in Library/Convert for media your own account can access. Cookies remain in the local user-data folder and are not packaged with releases. Remove the cookie file from the same panel when finished. Existing tasks snapshot its path; removing the file prevents subsequent use. Site login, availability, geography, rate limits and DRM can still prevent downloads. Cookie support does not bypass DRM.

## Interface and diagnostics

English/Arabic, RTL layout, light/dark modes, five accents, reduced-motion support and the skippable six-step download tour remain. New workspaces use the same theme and language. Technical errors and website titles retain their source language.

Logs: `%LOCALAPPDATA%\DropDL\diagnostics.log`, `backend-console.log`, `crash.log` and `playlist-worker-crash.log`. Each download's work folder also has `worker.log` and worker-state diagnostics. A worker failure identifies its log path. No automatic remote error reporting is used.

## Verification / development

Production frontend is prebuilt in `frontend/dist`. Development: install `backend/requirements.txt`, install frontend packages with `npm ci`, build with `npm run build`, then run `python backend/desktop.py` with FFmpeg/ffprobe and Node on PATH. Native Windows builds are supported by `scripts/build-native-windows.ps1`; run the generated whole folder, not its EXE alone. NSIS builds the online setup and small local launcher with `scripts/build-installer.py`.

Verification includes backend/API tests, real FFmpeg conversions and clipping, original preservation, isolated worker success/crash behavior, duplicate identity, queue persistence/priority/scheduling, library byte ranges and deletion safeguards, thumbnail/waveform generation, storage cleanup, private cookie authorization, subscriptions, extension pairing, and English/Arabic UI flows including a 198-task playlist queue and converter/library controls.

The Windows installer is compiled and structurally checked. Native Windows/WebView execution, prerequisite installation, GPU hardware, real third-party download availability and Chrome/Edge extension installation are not end-to-end verified in this Linux environment. The app cannot guarantee support for every website.

