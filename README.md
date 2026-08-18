# social-auto-upload

Open-source browser automation toolkit for publishing videos and image posts to multiple social platforms.

The project provides a unified CLI, reusable uploader modules, browser-based login flows, scheduling helpers, and agent-facing skills. It is designed for creators and small teams that need a repeatable local publishing workflow.

## Highlights

- Unified `sau` CLI for login, account checks, upload, and scheduling
- Browser automation based on Patchright
- Video and image-post workflows
- Reusable platform uploader modules
- Agent skills for Codex, Claude Code, OpenClaw, and similar tools
- Optional Flask backend and Vue frontend

## Supported platforms

Support varies by platform and workflow. Check the platform-specific documentation before use.

| Platform | Login | Video | Image post | CLI | Agent skill |
| --- | --- | --- | --- | --- | --- |
| Douyin | Yes | Yes | Yes | Yes | Yes |
| Kuaishou | Yes | Yes | Yes | Yes | Yes |
| Xiaohongshu | Yes | Yes | Yes | Yes | Yes |
| Bilibili | Yes | Yes | Limited | Yes | Yes |
| WeChat Channels | Yes | Yes | Limited | Yes | Planned |
| TikTok | Yes | Yes | No | Example | Planned |
| YouTube | Yes | Yes | No | Yes | Planned |
| Baijiahao | Yes | Yes | No | Example | Planned |

## Quick start

Requirements:

- Python 3.10 - 3.12
- A supported Chromium installation
- An account for the platform you want to use

Install the package:

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -e .
```

Install browser binaries if needed:

```bash
patchright install chromium
```

Copy the example configuration and adjust local settings:

```bash
copy conf.example.py conf.py
```

Log in to an account and check its session:

```bash
sau douyin login --account default
sau douyin check --account default
```

Upload a video:

```bash
sau douyin upload-video --account default --file media/demo.mp4 --title "Demo" --desc "Uploaded with sau"
```

See [`docs/CLI.md`](docs/CLI.md) and [`docs/install.md`](docs/install.md) for the full command set.

## Agent skills

The `skills/` directory contains concise instructions for agent clients:

- [`douyin-upload`](skills/douyin-upload/SKILL.md)
- [`kuaishou-upload`](skills/kuaishou-upload/SKILL.md)
- [`xiaohongshu-upload`](skills/xiaohongshu-upload/SKILL.md)
- [`bilibili-upload`](skills/bilibili-upload/SKILL.md)

The skills describe when to use the CLI, how to validate login state, and how to report failures without exposing account data.

## Repository layout

```text
.
├── sau_cli.py              # Unified command-line entry point
├── uploader/               # Platform integrations
├── skills/                 # Agent-facing workflows
├── examples/               # Small integration examples
├── scripts/                # Scheduling and maintenance helpers
├── docs/                   # Installation and usage documentation
├── tests/                  # Automated tests
└── sau_frontend/           # Optional web interface
```

## Privacy and account safety

This project uses browser sessions and local account state. Never commit cookies, storage-state JSON files, local configuration, tokens, passwords, or private media. The repository ignores common runtime directories, but always inspect `git diff` and `git status` before pushing.

Only automate accounts and content that you own or are authorized to manage. Follow each platform's terms, rate limits, content rules, and authentication requirements.

## Development

Run the test suite with:

```bash
python -m pytest
```

The project accepts focused bug fixes, documentation improvements, platform compatibility fixes, and new tests. See [`CONTRIBUTING.md`](CONTRIBUTING.md) for the contribution workflow.

## License

This repository is published under the MIT License.
