import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import pkg from './package.json'
const version = pkg.version

export default defineConfig({
  define: {'__DROPDL_VERSION__': JSON.stringify(version)},
  plugins: [react(), {name:'desktop-build-version',generateBundle(){this.emitFile({type:'asset',fileName:'build.json',source:JSON.stringify({version,features:['converter','clip-studio','media-library','queue-tools','selection','mini-player','diagnostics','organization','clip-editor','context-menus','resizable-player','multi-source-timeline','engine-auto-update','editor-layout-v2','editor-tutorial','pointer-timeline','persistent-timeline-scale','text-tracks','srt-captions','project-recovery','live-audio-mix','editing-proxies','duplicate-copy-names','resumable-chunks','native-file-drops','library-timeline-drops','edited-media-bin','absolute-timeline-positions','eight-video-tracks','non-ripple-trimming','overlap-compositor','docked-media-bin','download-thumbnails','webview2-direct-file-drops','durable-queue-backups','interrupted-task-recovery','offline-diagnostics','detachable-player','eight-edge-player-resize','track-mute-hide-lock','same-track-roll','optional-edge-snapping','timeline-frame-stepping','selection-playhead-undo','grouped-slider-history','editor-export-presets','timeline-audio-exports','output-settings-summary','persistent-favorites','media-collections','batch-library-organization','missing-file-relink','protected-external-replacements','lazy-media-details','library-list-view','library-source-filters','library-sort','editor-bin-collections','native-editor-export-folder','persistent-export-destination','export-target-storage-validation','macos-build-target','unicode-windows-python-discovery','sidebar-clip-timestamps','sidebar-preview-range-preservation','optional-windows-tray','format-sort-fallbacks','h264-compatibility-mode','sponsorblock','cover-art-embedding','embedded-subtitles','lossless-audio-formats','audio-bitrates','size-estimates','self-healing-downloads','stall-watchdog','exponential-auto-retry','adjustable-parallel-downloads','proxy-ipv4-browser-cookies','browser-impersonation','merged-progress','revision-queue-sync','shutdown-safe-resume','aurora-design-system','drop-arrow-logo','bundled-inter-plex-arabic','representative-posters','audio-cover-art-thumbnails','filmstrip-timeline-clips','source-fps-export-default','aligned-timeline-lanes','floating-editor-notices','command-center-shell','icon-rail','smart-bar','task-cards','task-inspector','live-status-bar','centered-download-sheet','pro-editing-workspace','smpte-timecode','program-scrub-transport','jkl-shuttle','safe-margins','live-stereo-meters','clip-waveforms','vertical-tool-palette','project-icon-view']})})}}],
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:17321',
        changeOrigin: true,
        ws: true,
      },
    },
  },
  clearScreen: false,
})
