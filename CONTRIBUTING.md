# Contributing to DropDL Studio

Thanks for helping make DropDL better! Every kind of contribution counts: reporting a bug, improving a translation, fixing a typo in the docs, designing an icon or writing code.

## Ways to help

- **Report a bug** with the [bug report form](https://github.com/HamedGhaithan/DropDL/issues/new?template=bug_report.yml). Include your DropDL and Windows versions, the steps, and the relevant lines from `%LOCALAPPDATA%\DropDL\diagnostics.log` (remove anything private first).
- **Suggest a feature** with the [feature request form](https://github.com/HamedGhaithan/DropDL/issues/new?template=feature_request.yml). Describe the problem first, then your idea.
- **Ask a question or share an idea** in [Discussions](https://github.com/HamedGhaithan/DropDL/discussions).
- **Translate.** All interface text lives in [`frontend/src/i18n.ts`](frontend/src/i18n.ts). Improving the Arabic strings or adding a new language is a great first contribution.
- **Pick up an issue** labelled [`good first issue`](https://github.com/HamedGhaithan/DropDL/labels/good%20first%20issue) or [`help wanted`](https://github.com/HamedGhaithan/DropDL/labels/help%20wanted). Leave a comment so nobody duplicates your work.

A website that stopped downloading is usually a [yt-dlp](https://github.com/yt-dlp/yt-dlp/issues) problem rather than a DropDL one. DropDL can update its yt-dlp engine from Preferences; try that first.

## Development setup

You need Python 3.12+, Node.js 22+, FFmpeg/ffprobe on your `PATH`, and Git.

```bash
git clone https://github.com/<your-username>/DropDL.git
cd DropDL
python -m venv .venv
.venv\Scripts\activate                 # macOS/Linux: source .venv/bin/activate
pip install -r backend/requirements.txt pytest
cd frontend && npm ci && cd ..
```

Run it:

- **Whole app:** `cd frontend && npm run build && cd .. && python backend/desktop.py`
- **Interface with hot reload:** `python backend/run.py` in one terminal and `npm run dev` inside `frontend` in another, then open http://localhost:5173.

Your real DropDL data lives in `%LOCALAPPDATA%\DropDL`. To keep development separate from it, set `DROPDL_DATA_ROOT` and `DOWNLOAD_ROOT` to scratch folders before starting the backend. The test suite does this automatically.

## Tests

Run these before you open a pull request. CI runs the same checks on Windows.

```bash
python -m pytest tests -q
cd frontend
npm run build                   # includes the TypeScript type check
npm run test:ui
npm run test:timeline
npm run test:fps
npm run test:pro
node ../tests/clip-time.cjs
```

The real-browser suites (`npm run test:editor`, `test:library`, `test:player`) drive Microsoft Edge through Playwright. Point the `DROPDL_PLAYWRIGHT` environment variable at a module that exports a Playwright `chromium` launching `channel: 'msedge'`. They are optional for most changes; say in your pull request if you could not run them.

Add or update tests for what you change. Backend tests go in `tests/test_*.py`; interface behaviour goes in `tests/ui-preview.cjs`.

## Making a change

1. **Fork** the repository and create a branch from `main`, for example `git checkout -b fix/short-description`.
2. **Keep it focused.** One fix or feature per pull request is much easier to review. For a large change, open an issue first so we can agree on the approach.
3. **Follow the existing style.** Match the surrounding code. Interface text goes through `i18n.ts` in both English and Arabic, and layouts must work right-to-left. Respect reduced motion. Tests must never touch a real user profile.
4. **Write clear commit messages**, for example `fix(queue): keep paused tasks paused after restart`. [Conventional Commits](https://www.conventionalcommits.org) prefixes (`feat`, `fix`, `docs`, `refactor`, `test`, `build`, `ci`) are encouraged.
5. **Open a pull request** against `main`, fill in the template, and add screenshots for anything visible. CI must pass.

A maintainer will review it, usually within a few days. Being asked for changes is normal and not a rejection.

## Ground rules

- Be kind. Everyone here follows the [code of conduct](CODE_OF_CONDUCT.md).
- No features whose purpose is to bypass DRM, paywalls or access controls.
- No telemetry, and no network calls that aren't needed for something the user started.
- Report security problems privately, as described in [SECURITY.md](SECURITY.md).

By contributing, you agree that your contributions are licensed under the project's [MIT License](LICENSE).
