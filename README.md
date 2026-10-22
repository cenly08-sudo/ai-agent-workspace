# social-auto-upload — Multi-Platform Content Publishing Automation

[![License](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![Vue 3](https://img.shields.io/badge/Frontend-Vue%203-42b883.svg)](https://vuejs.org/)
[![Flask](https://img.shields.io/badge/Backend-Flask-black.svg)](https://flask.palletsprojects.com/)

An open-source **browser-automation toolkit that publishes videos and image posts to major social platforms** with a unified CLI, scheduling, and agent-friendly skills. Designed for creators, operators, and small teams that need a repeatable local publishing workflow across Douyin, Bilibili, Xiaohongshu, Kuaishou, WeChat Channels, TikTok, YouTube, and more.

---

## Why this project

This is a practical demonstration of **browser automation engineering** at product level:

- **Real browser automation** built on Patchright (playwright-based), handling login flows, cookies/session persistence, and platform-specific uploaders.
- **One CLI, many platforms** — a unified `sau` command line for login, account health checks, upload, and scheduling.
- **Agent-native** — ships ready-to-use *skills* (prompt/instructions packs) so Codex, Claude Code, and similar agents can drive publishing directly.
- **Optional web console** — Flask backend + Vue 3 frontend for managing accounts, files, and publishing at scale, with SSE live updates.

---

## Supported platforms

| Platform | Login | Video | Image post | CLI | Agent skill |
| --- | --- | --- | --- | --- | --- |
| Douyin | ✅ | ✅ | ✅ | ✅ | ✅ |
| Kuaishou | ✅ | ✅ | ✅ | ✅ | ✅ |
| Xiaohongshu | ✅ | ✅ | ✅ | ✅ | ✅ |
| Bilibili | ✅ | ✅ | Limited | ✅ | ✅ |
| WeChat Channels | ✅ | ✅ | Limited | ✅ | Planned |
| TikTok | ✅ | ✅ | — | Example | Planned |
| YouTube | ✅ | ✅ | — | ✅ | Planned |
| Baijiahao | ✅ | ✅ | — | Example | Planned |

Support varies by platform and workflow — check the platform-specific docs before use.

---

## Quick start

Requirements: Python 3.10–3.12, a supported Chromium installation, and an account for each platform you use.

```bash
# Install
python -m venv .venv
.venv\Scripts\activate          # Windows
source .venv/bin/activate       # macOS / Linux
pip install -e .

# Install browser binaries
patchright install chromium

# Configure
copy conf.example.py conf.py   # then edit local settings

# Log in and verify a session
sau douyin login --account default
sau douyin check --account default

# Upload a video
sau douyin upload-video --account default --file media/demo.mp4 \
     --title "Demo" --desc "Uploaded with sau"
```

Scheduling:

```bash
sau douyin upload --account default --file media/video.mp4 \
     --title "Title" --tags tag1,tag2 --schedule "2026-01-01 10:00"
```

See [`docs/CLI.md`](docs/CLI.md) and [`docs/install.md`](docs/install.md) for the full command set.

---

## Web console (optional)

The `sau_frontend` directory contains a Flask + Vue 3 management UI:

```bash
# Backend
pip install -r requirements.txt
playwright install chromium
python db/createTable.py
python sau_backend.py            # http://localhost:5409

# Frontend
cd sau_frontend
npm install
npm run dev                      # http://localhost:5173
```

The backend exposes a RESTful API and streams progress to the frontend via Server-Sent Events (SSE) during logins and uploads.

---

## Agent skills

The `skills/` directory ships concise instructions for agent clients (Codex, Claude Code, OpenClaw, etc.):

- [`douyin-upload`](skills/douyin-upload/SKILL.md)
- [`kuaishou-upload`](skills/kuaishou-upload/SKILL.md)
- [`xiaohongshu-upload`](skills/xiaohongshu-upload/SKILL.md)
- [`bilibili-upload`](skills/bilibili-upload/SKILL.md)

Each skill documents when to use the CLI, how to validate login state, and how to report failures without exposing account data.

---

## Repository layout

```text
.
├── sau_cli.py              # Unified command-line entry point
├── uploader/               # Platform integrations (login + upload)
├── skills/                 # Agent-facing workflows
├── examples/               # Small integration examples
├── scripts/                # Scheduling and maintenance helpers
├── docs/                   # Installation and usage documentation
├── tests/                  # Automated tests
└── sau_frontend/           # Optional web console (Flask + Vue 3)
```

---

## Privacy & account safety

This project manages real browser sessions and local account state. **Never commit cookies, storage-state JSON files, local config, tokens, passwords, or private media.** Review `git diff` and `git status` before pushing.

Only automate accounts and content that you own or are authorized to manage. Follow each platform's terms, rate limits, content rules, and authentication requirements.

---

## Development

```bash
python -m pytest
```

The project accepts focused bug fixes, documentation improvements, platform compatibility fixes, and new tests. See [`CONTRIBUTING.md`](CONTRIBUTING.md) for the workflow. Published under the **MIT License**.

