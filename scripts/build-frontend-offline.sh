#!/bin/bash
# Offline production build (esbuild) producing the same dist layout as the Vite build.
set -e
cd "$(dirname "$0")/../frontend"
ES=${ESBUILD:-node_modules/.bin/esbuild}
VER=$(node -p "require('./package.json').version")
[ -f dist/assets/tauri-shell.js ] && cp dist/assets/tauri-shell.js /tmp/tauri-shell.js || true
rm -rf /tmp/distout && mkdir -p /tmp/distout/assets
$ES src/main.tsx --bundle --minify --format=esm --target=es2022 --jsx=automatic \
  --external:@tauri-apps/plugin-shell --define:__DROPDL_VERSION__="\"$VER\"" --define:import.meta.env.VITE_API_BASE=undefined \
  --define:process.env.NODE_ENV='"production"' --entry-names='index-[hash]' --outdir=/tmp/distout/assets --log-level=warning
JS=$(cd /tmp/distout/assets && ls index-*.js); CSS=$(cd /tmp/distout/assets && ls index-*.css)
cp /tmp/tauri-shell.js /tmp/distout/assets/tauri-shell.js
sed -i 's#"@tauri-apps/plugin-shell"#"./tauri-shell.js"#g' /tmp/distout/assets/$JS
cp public/dropdl.svg /tmp/distout/dropdl.svg
echo "{\"version\":\"$VER\",\"features\":[\"converter\",\"clip-studio\",\"media-library\",\"queue-tools\",\"selection\",\"mini-player\",\"diagnostics\",\"organization\"]}" > /tmp/distout/build.json
cat > /tmp/distout/index.html <<HTML
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <link rel="icon" type="image/svg+xml" href="/dropdl.svg" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <meta name="theme-color" content="#0a0d14" />
    <title>DropDL Studio — Desktop Downloader &amp; Clip Maker</title>
    <script type="module" crossorigin src="/assets/$JS"></script>
    <link rel="stylesheet" crossorigin href="/assets/$CSS">
  </head>
  <body>
    <div id="root"></div>
  </body>
</html>
HTML
rm -rf dist && mv /tmp/distout dist
ls -la dist/assets
