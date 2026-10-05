#!/usr/bin/env python3
"""从每天 07:00 的 Spotify 关注歌手 Top 歌单取新鲜候选歌，供播客片尾推荐歌用。

只读操作，不改任何歌单。
输出 JSON 到 stdout：[{"artist": "...", "title": "..."}, ...]，最多 --count 条。
"""
import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo
    LOCAL_TZ = ZoneInfo("Asia/Shanghai")
except Exception:
    LOCAL_TZ = timezone(timedelta(hours=8))

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# 每日刷新脚本的 state.json；用环境变量覆盖
STATE_PATH = os.environ.get(
    "SPOTIFY_REFRESH_STATE",
    os.path.expanduser("~/workspace/spotify/followed-top-refresh/state.json"),
)
CJK = re.compile(r"[\u4e00-\u9fff]")


def run_spotify(*args):
    p = subprocess.run(["spotify-api", *args], capture_output=True,
                       text=True, timeout=180)
    if p.returncode != 0:
        raise RuntimeError("spotify-api failed: " + (p.stderr or "")[:300])
    return p.stdout


def paged_items(first_json):
    """Yield items across experience/next-page responses, following `next`
    (same logic as followed-top-refresh/refresh.py)."""
    out = json.loads(first_json)
    while True:
        items = out.get("items")
        if items is not None:  # next-page shape: top-level items + next
            for it in items:
                yield it
            nxt = out.get("next")
            if not nxt:
                return
            out = json.loads(run_spotify("next-page", "--url", nxt))
            continue
        for s in out.get("sections", []):  # experience shape
            for it in s.get("items", []):
                yield it
            nxt = s.get("next")
            if nxt:
                out = json.loads(run_spotify("next-page", "--url", nxt))
                break
        else:
            return


def parse_log_line(line):
    """解析 youtube-songs.log 行。返回 (date, title, singer, url) 或 None。
    新格式: YYYY-MM-DD HH:MM - 标题 - 歌手 - https://...；旧格式无歌手字段。"""
    line = line.strip()
    m = re.match(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}) - (.*) - (https?://\S+)$", line)
    if not m:
        return None
    datepart, middle, url = m.groups()
    if " - " in middle:
        title, singer = middle.rsplit(" - ", 1)
    else:
        title, singer = middle, ""
    return datepart, title.strip(), singer.strip(), url


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--count", type=int, default=3)
    ap.add_argument("--log", default=os.path.expanduser(
        "~/workspace/goals/goal-2/hidden_files/youtube-songs.log"),
        help="youtube-songs.log：跳过已用过的 artist+title")
    args = ap.parse_args()

    today = datetime.now(LOCAL_TZ).strftime("%m-%d")
    try:
        state = json.load(open(STATE_PATH, encoding="utf-8"))
    except Exception as e:
        print(json.dumps({"error": "state.json unreadable: %s" % e},
                         ensure_ascii=False))
        return 1
    playlists = [p for p in state.get("playlists", []) if today in p.get("name", "")]
    if not playlists:
        # 今天的歌单缺失（如 07:00 刷新失败）时，回退到 7 天内最新的那期
        cands = []
        for p in state.get("playlists", []):
            m = re.search(r"(\d{2})-(\d{2})", p.get("name", ""))
            if not m:
                continue
            try:
                pdate = datetime(2026, int(m.group(1)), int(m.group(2)),
                                 tzinfo=LOCAL_TZ)
                age = (datetime.now(LOCAL_TZ).replace(
                    hour=0, minute=0, second=0, microsecond=0) - pdate).days
            except ValueError:
                continue
            if 0 <= age <= 7:
                cands.append((age, p["name"], p))
        if not cands:
            print(json.dumps({"error": "no refresh playlist for %s" % today},
                             ensure_ascii=False))
            return 1
        cands.sort()
        pl = cands[0][2]
    else:
        pl = playlists[-1]

    used = set()
    if os.path.exists(args.log):
        with open(args.log, encoding="utf-8") as f:
            for line in f:
                parsed = parse_log_line(line)
                if parsed:
                    used.add((parsed[2].lower(), parsed[1].lower()))

    try:
        items = list(paged_items(run_spotify("experience", "--id", pl["uri"])))
    except Exception as e:
        print(json.dumps({"error": "playlist read failed: %s" % e},
                         ensure_ascii=False))
        return 1

    def sortkey(it):
        title = (it.get("title") or "").split(" - ")[0]
        return (0 if CJK.search(title) else 1, title)

    out = []
    for it in sorted(items, key=sortkey):
        if it.get("is_explicit"):
            continue
        artist = (it.get("subtitle") or "").split(",")[0].strip()
        title = (it.get("title") or "").split(" - ")[0].strip()
        if not artist or not title:
            continue
        if (artist.lower(), title.lower()) in used:
            continue
        out.append({"artist": artist, "title": title})
        if len(out) >= args.count:
            break
    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
