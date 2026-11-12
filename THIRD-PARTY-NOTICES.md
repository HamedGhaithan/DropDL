# Third-party notices

DropDL Studio's own code is under the [MIT License](LICENSE). It uses the following projects, each under its own licence.

| Project | Used for | Licence | How it reaches users |
| --- | --- | --- | --- |
| [yt-dlp](https://github.com/yt-dlp/yt-dlp) | downloading and site extraction | Unlicense | installed by setup from PyPI |
| [FFmpeg / ffprobe](https://ffmpeg.org) | conversion, clipping, export, waveforms | LGPL 2.1+ / GPL 2+, depending on the build | installed separately by setup |
| [FastAPI](https://github.com/fastapi/fastapi), [Uvicorn](https://github.com/encode/uvicorn), [Pydantic](https://github.com/pydantic/pydantic) | local backend | MIT / BSD-3-Clause / MIT | installed by setup from PyPI |
| [curl_cffi](https://github.com/lexiforest/curl_cffi) | browser impersonation for downloads | MIT | installed by setup from PyPI |
| [pywebview](https://github.com/r0x0r/pywebview) | native desktop window | BSD-3-Clause | installed by setup from PyPI |
| [React](https://github.com/facebook/react) | interface | MIT | bundled in the built interface |
| [Inter](https://github.com/rsms/inter) | interface font | SIL Open Font License 1.1 | bundled in the built interface |
| [IBM Plex Sans Arabic](https://github.com/IBM/plex) | Arabic interface font | SIL Open Font License 1.1 | bundled in the built interface |
| [Microsoft Edge WebView2](https://developer.microsoft.com/microsoft-edge/webview2/) | rendering the window on Windows | Microsoft software licence | installed by setup if missing |

Development-only tools (Vite, TypeScript, esbuild, jsdom, Tauri CLI, PyInstaller, NSIS, pytest) are not shipped to users.

Screenshots in `docs/media` show *Big Buck Bunny* (© Blender Foundation, CC BY 3.0, peach.blender.org) and *Popeye for President* (public domain, via archive.org) as sample media.
