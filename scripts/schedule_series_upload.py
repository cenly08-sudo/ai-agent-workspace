from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path


VIDEO_SUFFIXES = {".mp4", ".mov", ".mkv", ".webm", ".avi"}
EPISODE_PATTERN = re.compile(r"\u7b2c(\d+)\u96c6")
VERSION_ORDER = {
    "\u539f\u58f0\u9ad8\u5149\u7248": 0,
    "\u65c1\u767d\u89e3\u8bf4\u7248": 1,
}
PLATFORM_CHOICES = ("douyin", "xiaohongshu", "kuaishou")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Publish a video series at a fixed interval.")
    parser.add_argument("--source", required=True, type=Path, help="Directory containing videos")
    parser.add_argument("--platforms", default="douyin,xiaohongshu,kuaishou")
    parser.add_argument("--douyin-account", required=True)
    parser.add_argument("--xiaohongshu-account", required=True)
    parser.add_argument("--kuaishou-account", required=True)
    parser.add_argument("--interval-minutes", type=float, default=15)
    parser.add_argument(
        "--tags",
        default="".join(
            [
                "\u68ee\u7433\u732b\u8bb0,\u840c\u5ba0\u65e5\u5e38,\u6cbb\u6108\u7cfb\u732b\u54aa,",
                "AI\u5236\u4f5c\u5185\u5bb9,\u771f\u5b9e\u6545\u4e8b\u6539\u7f16,\u6211\u5bb6\u5ba0\u7269\u597d\u53ef\u7231,",
                "\u64b8\u732b,\u517b\u732b\u4eba\u7684\u5feb\u4e50",
            ]
        ),
    )
    parser.add_argument(
        "--description",
        default="".join(
            [
                "\u300a\u68ee\u7433\u732b\u8bb0\u300b\u2014\u2014\u94f6\u7070\u864e\u6591\u68ee\u68ee\u9ad8\u51b7\u50b2\u5a07\uff0c",
                "\u767d\u8138\u7f8e\u4eba\u5c16\u7433\u7433\u8f6f\u840c\u53ef\u6b3a\u3002",
                "AI\u5320\u5fc3\u590d\u523b\u771f\u5b9e\u517b\u732b\u65e5\u5e38\uff0c\u7ec6\u788e\u6e29\u67d4\u91cc\u85cf\u7740\u6cbb\u6108\u529b\u91cf\u3002",
                "\u771f\u5b9e\u6545\u4e8b\u6539\u7f16\uff0cAI\u5236\u4f5c\u5185\u5bb9\uff1a\u4e24\u53ea\u732b\u7684\u788e\u788e\u5ff5\uff0c",
                "\u966a\u4f60\u6162\u4e0b\u6765\u3002\U0001f431",
            ]
        ),
    )
    parser.add_argument("--state-file", type=Path, default=Path("logs/series_schedule_state.json"))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--headed", action="store_true")
    return parser.parse_args()


def episode_key(path: Path) -> tuple[int, int, str]:
    match = EPISODE_PATTERN.search(path.stem)
    episode = int(match.group(1)) if match else 10**9
    version = next((rank for label, rank in VERSION_ORDER.items() if label in path.stem), 99)
    return episode, version, path.name


def discover_videos(source: Path) -> list[Path]:
    if not source.is_dir():
        raise SystemExit(f"Source directory does not exist: {source}")
    return sorted(
        (path for path in source.iterdir() if path.is_file() and path.suffix.lower() in VIDEO_SUFFIXES),
        key=episode_key,
    )


def parse_platforms(raw: str) -> list[str]:
    platforms = [item.strip().lower() for item in raw.split(",") if item.strip()]
    invalid = sorted(set(platforms) - set(PLATFORM_CHOICES))
    if invalid:
        raise SystemExit(f"Unsupported platforms: {', '.join(invalid)}")
    if not platforms:
        raise SystemExit("At least one platform is required.")
    return platforms


def title_for(video: Path) -> str:
    title = re.sub(r"_\u4e8c\u521b$", "", video.stem)
    return title.replace("_", " ")


def load_state(path: Path) -> dict:
    if not path.exists():
        return {"completed": {}, "failed": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Cannot read state file {path}: {exc}")
    data.setdefault("completed", {})
    data.setdefault("failed", {})
    return data


def save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def account_for(platform: str, args: argparse.Namespace) -> str:
    return {
        "douyin": args.douyin_account,
        "xiaohongshu": args.xiaohongshu_account,
        "kuaishou": args.kuaishou_account,
    }[platform]


def build_command(platform: str, account: str, video: Path, args: argparse.Namespace) -> list[str]:
    command = [
        sys.executable,
        "sau_cli.py",
        platform,
        "upload-video",
        "--account",
        account,
        "--file",
        str(video),
        "--title",
        title_for(video),
        "--desc",
        args.description,
        "--tags",
        args.tags,
        "--headed" if args.headed else "--headless",
    ]
    if platform == "douyin":
        command.extend(["--declaration", "\u542bAI\u751f\u6210\u5185\u5bb9"])
    return command


def run_upload(platform: str, account: str, video: Path, args: argparse.Namespace) -> tuple[bool, str]:
    command = build_command(platform, account, video, args)
    if args.dry_run:
        return True, "DRY RUN: " + subprocess.list2cmdline(command)

    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace")
    output = (result.stdout or result.stderr or "").strip()
    return result.returncode == 0, output


def main() -> int:
    args = parse_args()
    platforms = parse_platforms(args.platforms)
    if args.interval_minutes <= 0:
        raise SystemExit("--interval-minutes must be greater than zero.")

    videos = discover_videos(args.source)
    state = load_state(args.state_file)
    completed = state["completed"]

    print(f"Found {len(videos)} videos. Platforms: {', '.join(platforms)}.")
    for video in videos:
        video_key = str(video.resolve())
        finished = set(completed.get(video_key, []))
        pending = [platform for platform in platforms if platform not in finished]
        if not pending:
            continue

        for platform in pending:
            started_at = datetime.now().isoformat(timespec="seconds")
            print(f"[{started_at}] Publishing {video.name} to {platform}...")
            ok, message = run_upload(platform, account_for(platform, args), video, args)
            record = {
                "video": video_key,
                "platform": platform,
                "time": datetime.now().isoformat(timespec="seconds"),
                "message": message[-2000:],
            }
            if ok:
                completed.setdefault(video_key, []).append(platform)
                state["failed"].pop(f"{video_key}|{platform}", None)
                print(f"  success: {message}")
            else:
                state["failed"][f"{video_key}|{platform}"] = record
                print(f"  failed: {message}", file=sys.stderr)
            if not args.dry_run:
                save_state(args.state_file, state)

        if not args.dry_run:
            next_video = any(
                set(platforms) - set(completed.get(str(candidate.resolve()), []))
                for candidate in videos
            )
            if next_video:
                print(f"Waiting {args.interval_minutes:g} minutes before the next video...")
                time.sleep(args.interval_minutes * 60)

    print("Schedule complete: no pending videos.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
