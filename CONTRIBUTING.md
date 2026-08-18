# Contributing

## Before opening a pull request

1. Keep changes focused on one behavior or documentation topic.
2. Add or update tests for behavior changes.
3. Run `python -m pytest` for the affected area.
4. Remove cookies, storage-state files, logs, local configuration, and private media from the change.
5. Describe the platform, workflow, and environment used to verify the change.

## Account data

Do not include real login sessions, cookies, QR codes, passwords, access tokens, or private creator data in issues, pull requests, screenshots, or test fixtures.

## Platform changes

Platform pages and login flows change frequently. Keep selectors and platform-specific behavior inside the corresponding `uploader/` module, and document known limitations in `docs/`.

