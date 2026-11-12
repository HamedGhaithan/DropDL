# Security policy

## Supported versions

Security fixes go into the latest release. Please update before reporting.

| Version | Supported |
| --- | --- |
| 2.3.x | ✅ |
| older | ❌ |

## Reporting a vulnerability

**Please don't open a public issue for security problems.** Use GitHub's private reporting instead: open the [Security tab](https://github.com/HamedGhaithan/DropDL/security) and choose **Report a vulnerability**.

Include what you found, how to reproduce it, and what an attacker could do with it. You should get a reply within a week. Once a fix is released you'll be credited in the release notes, unless you'd rather stay anonymous.

## What's in scope

DropDL runs a local web server on `127.0.0.1` (port 17321 by default) that the app window and the paired browser extension talk to. Of particular interest:

- anything that lets a website, another local user or another process reach that server, read files or run commands;
- the browser-extension pairing and token checks;
- handling of imported cookie files;
- the installer, launcher and engine-update paths.

Problems in yt-dlp or FFmpeg themselves should be reported to those projects.
